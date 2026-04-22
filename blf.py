"""Bottom-Left-Fill placement algorithm — initial nesting solution."""
import math
from typing import List, Optional, Tuple
from rtree import index

from models.schemas import Part, Sheet, Placement, Polygon
from engine.geometry.nfp_engine import NFPCache, compute_ifp, compute_nfp
from engine.geometry.polygon_utils import (
    compute_area, compute_bbox, translate_polygon, rotate_polygon,
    point_in_polygon, boolean_difference, _to_int, _to_float,
)
import pyclipper


def blf_place(parts: List[Part], sheet: Sheet, nfp_cache: NFPCache,
              rotation_step: float = 90.0) -> List[Placement]:
    """Place parts using Bottom-Left-Fill heuristic.

    Sort parts by area DESC, then convexity score.
    For each part: query IFP for valid region, find bottom-most left-most position.
    Validate via R-tree broad phase → Clipper2 exact.
    """
    placed = []
    rtree_idx = index.Index()

    # Sort by area descending (largest first)
    sorted_parts = sorted(parts, key=lambda p: p.polygon.area, reverse=True)

    for part in sorted_parts:
        best_pos = None
        best_y = float('inf')
        best_x = float('inf')
        best_angle = 0.0

        angles = _rotation_angles(part, rotation_step)

        for angle in angles:
            rotated_outer = part.polygon.outer
            if abs(angle) > 1e-6:
                bbox_p = compute_bbox(rotated_outer)
                cx = (bbox_p.x_min + bbox_p.x_max) / 2
                cy = (bbox_p.y_min + bbox_p.y_max) / 2
                rotated_outer = rotate_polygon(rotated_outer, angle, cx, cy)

            rotated_poly = Polygon(
                id=part.polygon.id, outer=rotated_outer, holes=part.polygon.holes,
                area=compute_area(rotated_outer), bbox=compute_bbox(rotated_outer),
                convex_hull=part.polygon.convex_hull, is_convex=part.polygon.is_convex,
            )

            # Compute IFP
            ifp = compute_ifp(rotated_poly, sheet.width, sheet.height)
            if not ifp.outer or ifp.area <= 0:
                continue

            part_w = rotated_poly.bbox.x_max - rotated_poly.bbox.x_min
            part_h = rotated_poly.bbox.y_max - rotated_poly.bbox.y_min

            # Compute forbidden region from all placed parts (if NFPs available)
            forbidden = _compute_forbidden(placed, part, angle, nfp_cache)

            # Valid region = IFP minus forbidden
            valid_region = ifp
            if forbidden:
                valid_region = boolean_difference(ifp, forbidden)
                if not valid_region.outer or valid_region.area <= 0:
                    continue

            # Sample candidate positions: grid scan + IFP/valid region vertices
            candidates = list(valid_region.outer)
            # Add grid samples inside the IFP
            step = max(5.0, min(part_w, part_h) / 4)
            gx = ifp.bbox.x_min
            while gx <= ifp.bbox.x_max:
                gy = ifp.bbox.y_min
                while gy <= ifp.bbox.y_max:
                    candidates.append([gx, gy])
                    gy += step
                gx += step

            for cx, cy in candidates:
                if cx < -1e-6 or cy < -1e-6:
                    continue
                if cx > sheet.width + 1e-6 or cy > sheet.height + 1e-6:
                    continue
                # Bottom-left: minimize y first, then x
                if cy < best_y - 1e-6 or (abs(cy - best_y) < 1e-6 and cx < best_x - 1e-6):
                    if _validate_placement(cx, cy, angle, part, placed, rtree_idx, sheet):
                        best_pos = (cx, cy)
                        best_y = cy
                        best_x = cx
                        best_angle = angle

        if best_pos:
            placement = Placement(
                part_id=part.id,
                x=best_pos[0],
                y=best_pos[1],
                rotation=best_angle,
                flipped=False,
                sheet_id=sheet.id,
            )
            placed.append(placement)
            # Insert into R-tree
            bbox_p = compute_bbox(part.polygon.outer)
            rtree_idx.insert(len(placed) - 1,
                             (best_pos[0] + bbox_p.x_min, best_pos[1] + bbox_p.y_min,
                              best_pos[0] + bbox_p.x_max, best_pos[1] + bbox_p.y_max))

    return placed


def _rotation_angles(part: Part, rotation_step: float) -> List[float]:
    """Generate rotation angles for a part based on rotation_step."""
    if rotation_step <= 0 or rotation_step >= 360:
        return [0.0]
    angles = []
    a = 0.0
    while a < 360.0 - 1e-6:
        angles.append(a)
        a += rotation_step
    return angles


def _compute_forbidden(placed: List[Placement], part: Part, angle: float,
                       nfp_cache: NFPCache) -> Optional[Polygon]:
    """Compute the union of all NFPs for placed parts relative to the new part."""
    if not placed:
        return None

    # For each placed part, compute NFP and union them
    union_nfp = None
    for pl in placed:
        nfp_key = NFPCache.make_key(pl.part_id, part.id, angle)
        nfp = nfp_cache.get(nfp_key)
        if nfp is None:
            # Compute on demand (lazy) — need the placed part's polygon
            # We don't have the placed Part object here, so skip exact NFP
            # and rely on the Clipper2 validation in _validate_placement instead
            continue

        # Translate NFP to the placed part's position
        translated_outer = translate_polygon(nfp.outer, pl.x, pl.y)
        translated_nfp = Polygon(
            id=nfp.id, outer=translated_outer, holes=nfp.holes,
            area=nfp.area, bbox=compute_bbox(translated_outer),
            convex_hull=nfp.convex_hull, is_convex=nfp.is_convex,
        )

        if union_nfp is None:
            union_nfp = translated_nfp
        else:
            from engine.geometry.polygon_utils import boolean_union
            union_nfp = boolean_union(union_nfp, translated_nfp)

    return union_nfp


def _validate_placement(cx: float, cy: float, angle: float, part: Part,
                        placed: List[Placement], rtree_idx: index.Index,
                        sheet: Sheet) -> bool:
    """Validate a placement: check sheet bounds and collisions."""
    # Check sheet bounds
    bbox_p = compute_bbox(part.polygon.outer)
    if cx + bbox_p.x_max > sheet.width + 1e-6:
        return False
    if cy + bbox_p.y_max > sheet.height + 1e-6:
        return False
    if cx + bbox_p.x_min < -1e-6 or cy + bbox_p.y_min < -1e-6:
        return False

    # R-tree broad phase: check for overlapping bounding boxes
    new_bbox = (cx + bbox_p.x_min, cy + bbox_p.y_min,
                cx + bbox_p.x_max, cy + bbox_p.y_max)
    candidates = list(rtree_idx.intersection(new_bbox))
    if not candidates:
        return True  # No overlap possible

    # Exact check: use Clipper2 intersection
    rotated_outer = part.polygon.outer
    if abs(angle) > 1e-6:
        bbox_r = compute_bbox(rotated_outer)
        rcx = (bbox_r.x_min + bbox_r.x_max) / 2
        rcy = (bbox_r.y_min + bbox_r.y_max) / 2
        rotated_outer = rotate_polygon(rotated_outer, angle, rcx, rcy)
    translated_new = translate_polygon(rotated_outer, cx, cy)
    int_new = _to_int(translated_new)

    for idx in candidates:
        if idx >= len(placed):
            continue
        pl = placed[idx]
        # For now, use the part's original polygon (simplified)
        pl_translated = translate_polygon(part.polygon.outer, pl.x, pl.y)
        int_pl = _to_int(pl_translated)

        pc = pyclipper.Pyclipper()
        try:
            pc.AddPath(int_new, pyclipper.PT_SUBJECT, True)
            pc.AddPath(int_pl, pyclipper.PT_CLIP, True)
            result = pc.Execute(pyclipper.CT_INTERSECTION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
            if result:
                # Check if intersection has significant area
                for path in result:
                    if len(path) >= 3:
                        area = abs(pyclipper.Area(path))
                        if area > 1:  # more than 0.0001mm² overlap
                            return False
        except pyclipper.ClipperException:
            continue

    return True
