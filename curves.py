"""Curve flattening — Bezier curves and arcs to polylines.

All flattening uses adaptive recursive subdivision to guarantee
max deviation from the true curve is below tolerance (mm).
"""
import math
from typing import List, Tuple


def flatten_bezier(points: List[List[float]], tolerance: float = 0.05) -> List[List[float]]:
    """Flatten a cubic Bezier curve to a polyline within tolerance (mm).

    Args:
        points: Control points [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] for cubic,
                or [[x0,y0],[x1,y1],[x2,y2]] for quadratic.
        tolerance: Maximum allowed deviation from true curve in mm.

    Returns:
        List of [x, y] points approximating the curve.
    """
    if len(points) == 3:
        return _flatten_quadratic_bezier(points, tolerance)
    elif len(points) == 4:
        return _flatten_cubic_bezier(points, tolerance)
    else:
        raise ValueError(f"Expected 3 (quadratic) or 4 (cubic) control points, got {len(points)}")


def _flatten_quadratic_bezier(points: List[List[float]], tolerance: float) -> List[List[float]]:
    """Flatten a quadratic Bezier via recursive subdivision."""
    p0, p1, p2 = points

    flatness = _quadratic_flatness(p0, p1, p2)
    if flatness <= tolerance:
        return [p0, p2]

    mid01 = _lerp(p0, p1, 0.5)
    mid12 = _lerp(p1, p2, 0.5)
    mid = _lerp(mid01, mid12, 0.5)

    left = _flatten_quadratic_bezier([p0, mid01, mid], tolerance)
    right = _flatten_quadratic_bezier([mid, mid12, p2], tolerance)

    return left + right[1:]


def _flatten_cubic_bezier(points: List[List[float]], tolerance: float) -> List[List[float]]:
    """Flatten a cubic Bezier via recursive subdivision (de Casteljau)."""
    p0, p1, p2, p3 = points

    flatness = _cubic_flatness(p0, p1, p2, p3)
    if flatness <= tolerance:
        return [p0, p3]

    mid01 = _lerp(p0, p1, 0.5)
    mid12 = _lerp(p1, p2, 0.5)
    mid23 = _lerp(p2, p3, 0.5)

    mid012 = _lerp(mid01, mid12, 0.5)
    mid123 = _lerp(mid12, mid23, 0.5)

    mid = _lerp(mid012, mid123, 0.5)

    left = _flatten_cubic_bezier([p0, mid01, mid012, mid], tolerance)
    right = _flatten_cubic_bezier([mid, mid123, mid23, p3], tolerance)

    return left + right[1:]


def _lerp(a: List[float], b: List[float], t: float) -> List[float]:
    """Linear interpolation between two points."""
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]


def _quadratic_flatness(p0: List[float], p1: List[float], p2: List[float]) -> float:
    """Measure how flat a quadratic Bezier is (max deviation from chord)."""
    ux = 2.0 * p1[0] - p0[0] - p2[0]
    uy = 2.0 * p1[1] - p0[1] - p2[1]
    return math.sqrt(ux * ux + uy * uy) / 2.0


def _cubic_flatness(p0: List[float], p1: List[float], p2: List[float], p3: List[float]) -> float:
    """Measure how flat a cubic Bezier is (max deviation from chord)."""
    ux = 3.0 * p1[0] - 2.0 * p0[0] - p3[0]
    uy = 3.0 * p1[1] - 2.0 * p0[1] - p3[1]
    vx = 3.0 * p2[0] - 2.0 * p3[0] - p0[0]
    vy = 3.0 * p2[1] - 2.0 * p3[1] - p0[1]
    return max(math.sqrt(ux * ux + uy * uy), math.sqrt(vx * vx + vy * vy)) / 3.0


def flatten_arc(cx: float, cy: float, r: float,
                start_angle: float, end_angle: float,
                tolerance: float = 0.05) -> List[List[float]]:
    """Flatten a circular arc to a polyline within tolerance (mm).

    Args:
        cx, cy: Center of the arc.
        r: Radius of the arc.
        start_angle: Start angle in radians.
        end_angle: End angle in radians.
        tolerance: Maximum deviation in mm.

    Returns:
        List of [x, y] points approximating the arc.
    """
    if r < 1e-9:
        return [[cx, cy]]

    sweep = abs(end_angle - start_angle)
    if sweep < 1e-9:
        return [[cx + r * math.cos(start_angle), cy + r * math.sin(start_angle)]]

    # Compute number of segments needed for tolerance
    # Max deviation for arc of angle da on radius r: r * (1 - cos(da/2))
    # Solve for da: da = 2 * acos(1 - tolerance/r)
    if tolerance >= r:
        num_segments = 4
    else:
        da = 2.0 * math.acos(1.0 - tolerance / r)
        num_segments = max(4, int(math.ceil(sweep / da)))

    step = (end_angle - start_angle) / num_segments
    points = []
    for i in range(num_segments + 1):
        angle = start_angle + step * i
        points.append([cx + r * math.cos(angle), cy + r * math.sin(angle)])

    return points


def flatten_ellipse(cx: float, cy: float, rx: float, ry: float,
                    start_angle: float, end_angle: float,
                    tolerance: float = 0.05) -> List[List[float]]:
    """Flatten an elliptical arc to a polyline within tolerance (mm).

    Args:
        cx, cy: Center of the ellipse.
        rx, ry: Semi-axes of the ellipse.
        start_angle: Start angle in radians.
        end_angle: End angle in radians.
        tolerance: Maximum deviation in mm.

    Returns:
        List of [x, y] points approximating the elliptical arc.
    """
    if rx < 1e-9 or ry < 1e-9:
        return [[cx, cy]]

    sweep = abs(end_angle - start_angle)
    if sweep < 1e-9:
        return [[cx + rx * math.cos(start_angle), cy + ry * math.sin(start_angle)]]

    # Use the smaller radius for conservative segment count
    r_min = min(rx, ry)
    if tolerance >= r_min:
        num_segments = 8
    else:
        da = 2.0 * math.acos(1.0 - tolerance / r_min)
        num_segments = max(8, int(math.ceil(sweep / da)))

    step = (end_angle - start_angle) / num_segments
    points = []
    for i in range(num_segments + 1):
        angle = start_angle + step * i
        points.append([cx + rx * math.cos(angle), cy + ry * math.sin(angle)])

    return points
