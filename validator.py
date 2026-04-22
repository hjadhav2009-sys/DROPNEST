"""Overlap validation — R-tree broad phase + Clipper2 exact check."""
from typing import List, Dict
from rtree import index

from models.schemas import Placement, Part
from engine.geometry.polygon_utils import (
    compute_bbox, translate_polygon, rotate_polygon, _to_int,
)
import pyclipper


def validate_placements(placements: List[Placement], parts: List[Part],
                        sheet_width: float = None, sheet_height: float = None) -> dict:
    """Check that no placed parts overlap and all are within sheet bounds.

    Returns ValidationResult: {valid, overlaps: [{i,j,area}], oob: [indices]}
    """
    part_map = {p.id: p for p in parts}
    overlaps = []
    oob = []

    # Build R-tree
    rtree_idx = index.Index()
    for i, pl in enumerate(placements):
        part = part_map.get(pl.part_id)
        if not part:
            continue
        bbox = compute_bbox(part.polygon.outer)
        x_min = pl.x + bbox.x_min
        y_min = pl.y + bbox.y_min
        x_max = pl.x + bbox.x_max
        y_max = pl.y + bbox.y_max
        rtree_idx.insert(i, (x_min, y_min, x_max, y_max))

        # Check sheet bounds
        if sheet_width and sheet_height:
            if x_max > sheet_width + 0.1 or y_max > sheet_height + 0.1:
                oob.append(i)
            if x_min < -0.1 or y_min < -0.1:
                oob.append(i)

    # Pairwise overlap check (broad phase via R-tree, exact via Clipper2)
    for i, pl_i in enumerate(placements):
        part_i = part_map.get(pl_i.part_id)
        if not part_i:
            continue
        bbox_i = compute_bbox(part_i.polygon.outer)

        # Get translated polygon for part i
        outer_i = part_i.polygon.outer
        if abs(pl_i.rotation) > 1e-6:
            cx = (bbox_i.x_min + bbox_i.x_max) / 2
            cy = (bbox_i.y_min + bbox_i.y_max) / 2
            outer_i = rotate_polygon(outer_i, pl_i.rotation, cx, cy)
        trans_i = translate_polygon(outer_i, pl_i.x, pl_i.y)
        int_i = _to_int(trans_i)

        # Broad phase: query R-tree for overlapping bboxes
        search_bbox = (pl_i.x + bbox_i.x_min, pl_i.y + bbox_i.y_min,
                       pl_i.x + bbox_i.x_max, pl_i.y + bbox_i.y_max)
        candidates = list(rtree_idx.intersection(search_bbox))

        for j in candidates:
            if j <= i:
                continue
            pl_j = placements[j]
            part_j = part_map.get(pl_j.part_id)
            if not part_j:
                continue
            bbox_j = compute_bbox(part_j.polygon.outer)

            # Check bbox overlap
            if (pl_i.x + bbox_i.x_max < pl_j.x + bbox_j.x_min - 0.1 or
                pl_j.x + bbox_j.x_max < pl_i.x + bbox_i.x_min - 0.1 or
                pl_i.y + bbox_i.y_max < pl_j.y + bbox_j.y_min - 0.1 or
                pl_j.y + bbox_j.y_max < pl_i.y + bbox_i.y_min - 0.1):
                continue

            # Exact check via Clipper2
            outer_j = part_j.polygon.outer
            if abs(pl_j.rotation) > 1e-6:
                cx2 = (bbox_j.x_min + bbox_j.x_max) / 2
                cy2 = (bbox_j.y_min + bbox_j.y_max) / 2
                outer_j = rotate_polygon(outer_j, pl_j.rotation, cx2, cy2)
            trans_j = translate_polygon(outer_j, pl_j.x, pl_j.y)
            int_j = _to_int(trans_j)

            pc = pyclipper.Pyclipper()
            try:
                pc.AddPath(int_i, pyclipper.PT_SUBJECT, True)
                pc.AddPath(int_j, pyclipper.PT_CLIP, True)
                result = pc.Execute(pyclipper.CT_INTERSECTION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
                for path in result:
                    if len(path) >= 3:
                        area = abs(pyclipper.Area(path)) / 1e8  # Convert back to mm²
                        if area > 0.01:
                            overlaps.append({"i": i, "j": j, "overlap_area_mm2": round(area, 4)})
            except pyclipper.ClipperException:
                continue

    return {
        "valid": len(overlaps) == 0 and len(oob) == 0,
        "overlaps": overlaps,
        "out_of_bounds": list(set(oob)),
    }
