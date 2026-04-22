"""Polygon healer — fix CAD errors before nesting."""
import math
from typing import List
from models.schemas import Polygon, AABB
from engine.geometry.polygon_utils import (
    repair, validate, compute_area, compute_bbox, compute_convex_hull,
    is_convex, _signed_area, _remove_duplicates,
)

COLLINEAR_TOL = 1e-4  # mm — minimum cross product to be considered non-colinear
MIN_EDGE_LEN = 0.01   # mm — minimum edge length


def heal(polygon: Polygon) -> Polygon:
    """Fix common CAD errors: near-colinear vertices, tiny segments, self-touching edges.

    Pipeline: validate → remove tiny edges → remove colinear vertices → repair → re-validate
    """
    outer = polygon.outer
    if len(outer) < 3:
        return polygon

    # Step 1: Remove duplicate and near-duplicate vertices
    outer = _remove_duplicates(outer)

    # Step 2: Remove tiny edges (shorter than MIN_EDGE_LEN)
    outer = _remove_tiny_edges(outer)

    # Step 3: Remove near-colinear vertices
    outer = _remove_colinear_vertices(outer)

    if len(outer) < 3:
        return polygon

    # Step 4: Run full repair (fix winding, self-intersections)
    healed = repair(Polygon(
        id=polygon.id, outer=outer, holes=polygon.holes,
        area=compute_area(outer), bbox=compute_bbox(outer),
        convex_hull=compute_convex_hull(outer), is_convex=is_convex(outer),
    ))

    return healed


def _remove_tiny_edges(pts: List[List[float]]) -> List[List[float]]:
    """Remove vertices that create edges shorter than MIN_EDGE_LEN."""
    if len(pts) < 3:
        return pts
    result = [pts[0]]
    for i in range(1, len(pts)):
        dx = pts[i][0] - result[-1][0]
        dy = pts[i][1] - result[-1][1]
        if math.sqrt(dx*dx + dy*dy) >= MIN_EDGE_LEN:
            result.append(pts[i])
    # Check wrap-around
    if len(result) > 1:
        dx = result[0][0] - result[-1][0]
        dy = result[0][1] - result[-1][1]
        if math.sqrt(dx*dx + dy*dy) < MIN_EDGE_LEN:
            result.pop()
    return result if len(result) >= 3 else pts


def _remove_colinear_vertices(pts: List[List[float]]) -> List[List[float]]:
    """Remove vertices where the cross product of adjacent edges is near-zero."""
    if len(pts) < 3:
        return pts
    result = []
    n = len(pts)
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        cross = (p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0])
        if abs(cross) > COLLINEAR_TOL:
            result.append(p1)
    return result if len(result) >= 3 else pts
