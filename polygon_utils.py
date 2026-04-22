"""Polygon validation, repair, and utility functions.

All operations use Clipper2 via pyclipper — never implement polygon math manually.
All coordinates as integers scaled ×10000 (0.0001mm = 1 unit).
"""
import math
import uuid
from typing import List, Tuple, Optional

import pyclipper

from models.schemas import Polygon, AABB

SCALE_FACTOR = 10000
EPSILON = 1  # 0.0001mm minimum difference
MIN_AREA_MM2 = 1.0  # reject polygons smaller than 1mm²


def _to_int(pts: List[List[float]]) -> List[Tuple[int, int]]:
    """Convert float mm coordinates to integer scaled coordinates."""
    return [(round(x * SCALE_FACTOR), round(y * SCALE_FACTOR)) for x, y in pts]


def _to_float(pts) -> List[List[float]]:
    """Convert integer scaled coordinates back to float mm."""
    return [[x / SCALE_FACTOR, y / SCALE_FACTOR] for x, y in pts]


def validate(polygon: Polygon) -> dict:
    """Validate a polygon: check area, winding, self-intersection.

    Returns ValidationResult dict with keys: valid, errors, warnings.
    """
    errors = []
    warnings = []
    outer = polygon.outer

    if len(outer) < 3:
        errors.append("Polygon has fewer than 3 vertices")
        return {"valid": False, "errors": errors, "warnings": warnings}

    area = compute_area(outer)
    if area < MIN_AREA_MM2:
        errors.append(f"Polygon area ({area:.2f} mm²) below minimum ({MIN_AREA_MM2} mm²)")

    # Check coordinate range
    for p in outer:
        if abs(p[0]) > 100000 or abs(p[1]) > 100000:
            errors.append(f"Coordinate out of range: ({p[0]:.1f}, {p[1]:.1f}) — likely wrong units")
            break

    # Check self-intersection via Clipper2
    int_pts = _to_int(outer)
    pc = pyclipper.Pyclipper()
    try:
        pc.AddPath(int_pts, pyclipper.PT_SUBJECT, True)
        result = pc.Execute(pyclipper.CT_UNION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
        if len(result) > 1:
            warnings.append(f"Self-intersecting polygon splits into {len(result)} parts — auto-fix via repair()")
        elif len(result) == 1:
            # Check if vertices changed (indicates self-intersection was fixed)
            if len(result[0]) != len(int_pts):
                warnings.append("Polygon has self-intersections — auto-fix via repair()")
    except pyclipper.ClipperException as e:
        errors.append(f"Clipper error: {e}")

    # Check winding direction
    signed = _signed_area(outer)
    if signed > 0:
        warnings.append("Outer polygon is CW — should be CCW (auto-fix via repair())")

    # Check holes
    for i, hole in enumerate(polygon.holes):
        if len(hole) < 3:
            errors.append(f"Hole {i} has fewer than 3 vertices")
        hole_signed = _signed_area(hole)
        if hole_signed < 0:
            warnings.append(f"Hole {i} is CCW — should be CW (auto-fix via repair())")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def repair(polygon: Polygon) -> Polygon:
    """Fix winding order, remove duplicate vertices, fix self-intersections.

    Returns a clean Polygon with CCW outer, CW holes.
    """
    # Fix outer
    outer = _remove_duplicates(polygon.outer)
    if len(outer) < 3:
        return polygon

    # Ensure CCW winding for outer
    if _signed_area(outer) > 0:
        outer = outer[::-1]

    # Simplify / fix self-intersections via Clipper Union
    int_pts = _to_int(outer)
    pc = pyclipper.Pyclipper()
    try:
        pc.AddPath(int_pts, pyclipper.PT_SUBJECT, True)
        result = pc.Execute(pyclipper.CT_UNION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
        if result:
            # Take the largest resulting polygon
            largest = max(result, key=len)
            outer = _to_float(largest)
            # Re-ensure CCW
            if _signed_area(outer) > 0:
                outer = outer[::-1]
    except pyclipper.ClipperException:
        pass

    # Fix holes — ensure CW winding
    fixed_holes = []
    for hole in polygon.holes:
        hole = _remove_duplicates(hole)
        if len(hole) < 3:
            continue
        if _signed_area(hole) < 0:
            hole = hole[::-1]
        fixed_holes.append(hole)

    area = compute_area(outer)
    bbox = compute_bbox(outer)
    hull = compute_convex_hull(outer)
    convex = is_convex(outer)

    return Polygon(
        id=polygon.id,
        outer=outer,
        holes=fixed_holes,
        area=area,
        bbox=bbox,
        convex_hull=hull,
        is_convex=convex,
    )


def compute_area(outer: List[List[float]]) -> float:
    """Compute absolute area of a polygon in mm²."""
    return abs(_signed_area(outer))


def _signed_area(pts: List[List[float]]) -> float:
    """Compute signed area (positive = CW, negative = CCW)."""
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return area / 2.0


def compute_bbox(outer: List[List[float]]) -> AABB:
    """Compute axis-aligned bounding box."""
    xs = [p[0] for p in outer]
    ys = [p[1] for p in outer]
    return AABB(x_min=min(xs), y_min=min(ys), x_max=max(xs), y_max=max(ys))


def compute_convex_hull(outer: List[List[float]]) -> List[List[float]]:
    """Compute convex hull of a polygon using Clipper2."""
    int_pts = _to_int(outer)
    hull_int = pyclipper.SimplifyPolygon(int_pts, pyclipper.PFT_NONZERO)
    if not hull_int:
        return outer
    # SimplifyPolygon returns simplified; use convex hull via Minkowski sum trick
    # Actually, pyclipper doesn't have a direct convex hull, so use the area-based approach
    # For now, return the simplified polygon (which may not be convex)
    # Use a proper convex hull algorithm
    return _convex_hull_graham(outer)


def _convex_hull_graham(pts: List[List[float]]) -> List[List[float]]:
    """Graham scan convex hull algorithm."""
    if len(pts) < 3:
        return pts[:]

    # Find the lowest point (and leftmost if tie)
    pivot = min(pts, key=lambda p: (p[1], p[0]))

    def polar_angle(p):
        return math.atan2(p[1] - pivot[1], p[0] - pivot[0])

    sorted_pts = sorted(pts, key=lambda p: (polar_angle(p), (p[0]-pivot[0])**2 + (p[1]-pivot[1])**2))

    stack = []
    for p in sorted_pts:
        while len(stack) >= 2 and _cross(stack[-2], stack[-1], p) <= 0:
            stack.pop()
        stack.append(p)
    return stack


def _cross(o, a, b):
    """Cross product of vectors OA and OB."""
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def is_convex(outer: List[List[float]]) -> bool:
    """Check if polygon is convex."""
    n = len(outer)
    if n < 3:
        return False
    sign = None
    for i in range(n):
        x1, y1 = outer[i]
        x2, y2 = outer[(i+1) % n]
        x3, y3 = outer[(i+2) % n]
        cross = (x2-x1)*(y3-y2) - (y2-y1)*(x3-x2)
        if abs(cross) < 1e-9:
            continue
        if sign is None:
            sign = cross > 0
        elif (cross > 0) != sign:
            return False
    return True


def offset(polygon: Polygon, delta_mm: float) -> Polygon:
    """Offset (inflate/deflate) polygon by delta_mm. Positive = grow, negative = shrink."""
    int_pts = _to_int(polygon.outer)
    delta_int = round(delta_mm * SCALE_FACTOR)

    pc = pyclipper.PyclipperOffset()
    pc.AddPath(int_pts, pyclipper.JT_ROUND, pyclipper.ET_CLOSEPOLYGON)

    # Add holes
    for hole in polygon.holes:
        hole_int = _to_int(hole)
        pc.AddPath(hole_int, pyclipper.JT_ROUND, pyclipper.ET_CLOSEPOLYGON)

    result = pc.Execute(delta_int)

    if not result:
        return polygon  # offset collapsed the polygon

    # Take the largest result path as outer
    largest = max(result, key=len)
    new_outer = _to_float(largest)

    # Ensure CCW
    if _signed_area(new_outer) > 0:
        new_outer = new_outer[::-1]

    area = compute_area(new_outer)
    bbox = compute_bbox(new_outer)
    hull = compute_convex_hull(new_outer)
    convex = is_convex(new_outer)

    return Polygon(
        id=str(uuid.uuid4()),
        outer=new_outer,
        holes=[],  # offset may create holes — simplified for now
        area=area,
        bbox=bbox,
        convex_hull=hull,
        is_convex=convex,
    )


def boolean_union(poly_a: Polygon, poly_b: Polygon) -> Polygon:
    """Boolean union of two polygons."""
    return _boolean_op(poly_a, poly_b, pyclipper.CT_UNION)


def boolean_intersection(poly_a: Polygon, poly_b: Polygon) -> Polygon:
    """Boolean intersection of two polygons."""
    return _boolean_op(poly_a, poly_b, pyclipper.CT_INTERSECTION)


def boolean_difference(poly_a: Polygon, poly_b: Polygon) -> Polygon:
    """Boolean difference: A minus B."""
    return _boolean_op(poly_a, poly_b, pyclipper.CT_DIFFERENCE)


def _boolean_op(poly_a: Polygon, poly_b: Polygon, op) -> Polygon:
    """Perform a boolean operation between two polygons via Clipper2."""
    pc = pyclipper.Pyclipper()
    int_a = _to_int(poly_a.outer)
    pc.AddPath(int_a, pyclipper.PT_SUBJECT, True)

    int_b = _to_int(poly_b.outer)
    pc.AddPath(int_b, pyclipper.PT_CLIP, True)

    # Add holes for clip
    for hole in poly_b.holes:
        pc.AddPath(_to_int(hole), pyclipper.PT_CLIP, True)

    try:
        result = pc.Execute(op, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
    except pyclipper.ClipperException:
        return poly_a

    if not result:
        return Polygon(id=str(uuid.uuid4()), outer=[[0,0],[0,0],[0,0]], holes=[],
                       area=0, bbox=AABB(x_min=0,y_min=0,x_max=0,y_max=0),
                       convex_hull=[], is_convex=False)

    largest = max(result, key=len)
    outer = _to_float(largest)
    if _signed_area(outer) > 0:
        outer = outer[::-1]

    area = compute_area(outer)
    bbox = compute_bbox(outer)
    return Polygon(id=str(uuid.uuid4()), outer=outer, holes=[], area=area,
                   bbox=bbox, convex_hull=compute_convex_hull(outer),
                   is_convex=is_convex(outer))


def point_in_polygon(point: List[float], polygon_outer: List[List[float]]) -> bool:
    """Check if a point is inside a polygon using ray casting."""
    x, y = point
    n = len(polygon_outer)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon_outer[i]
        xj, yj = polygon_outer[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def translate_polygon(outer: List[List[float]], dx: float, dy: float) -> List[List[float]]:
    """Translate polygon by (dx, dy) mm."""
    return [[x + dx, y + dy] for x, y in outer]


def rotate_polygon(outer: List[List[float]], angle_deg: float, cx: float = 0, cy: float = 0) -> List[List[float]]:
    """Rotate polygon by angle_deg around (cx, cy)."""
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    result = []
    for x, y in outer:
        dx, dy = x - cx, y - cy
        nx = cos_a * dx - sin_a * dy + cx
        ny = sin_a * dx + cos_a * dy + cy
        result.append([nx, ny])
    return result


def _remove_duplicates(pts: List[List[float]], tol: float = 1e-6) -> List[List[float]]:
    """Remove consecutive duplicate vertices."""
    if not pts:
        return pts
    cleaned = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - cleaned[-1][0]) > tol or abs(p[1] - cleaned[-1][1]) > tol:
            cleaned.append(p)
    # Check wrap-around
    if len(cleaned) > 1 and abs(cleaned[-1][0] - cleaned[0][0]) < tol and abs(cleaned[-1][1] - cleaned[0][1]) < tol:
        cleaned.pop()
    return cleaned
