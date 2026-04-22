"""Polygon normalization — center, orient, and prepare parts for nesting."""
from models.schemas import Part, Polygon, AABB
from engine.geometry.polygon_utils import (
    compute_area, compute_bbox, compute_convex_hull, is_convex,
    translate_polygon, _signed_area,
)


def normalize_part(part: Part) -> Part:
    """Center polygon at origin, ensure CCW outer / CW holes, compute derived fields."""
    poly = part.polygon
    outer = poly.outer
    if len(outer) < 3:
        return part

    # Center at origin (move centroid to 0,0)
    cx = sum(p[0] for p in outer) / len(outer)
    cy = sum(p[1] for p in outer) / len(outer)
    outer = translate_polygon(outer, -cx, -cy)

    # Ensure CCW winding for outer
    if _signed_area(outer) > 0:
        outer = outer[::-1]

    # Fix holes: ensure CW winding, translate
    holes = []
    for hole in poly.holes:
        if len(hole) < 3:
            continue
        h = translate_polygon(hole, -cx, -cy)
        if _signed_area(h) < 0:
            h = h[::-1]
        holes.append(h)

    area = compute_area(outer)
    bbox = compute_bbox(outer)
    hull = compute_convex_hull(outer)
    convex = is_convex(outer)

    normalized_poly = Polygon(
        id=poly.id, outer=outer, holes=holes,
        area=area, bbox=bbox, convex_hull=hull, is_convex=convex,
    )

    return Part(
        id=part.id, name=part.name, polygon=normalized_poly,
        quantity=part.quantity, grain_dir=part.grain_dir,
        rotation_step=part.rotation_step, allow_flip=part.allow_flip,
    )
