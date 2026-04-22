"""No-Fit Polygon (NFP) computation engine.

Computes NFP(A, B, angle) for all unique (part_A, part_B, angle) triplets.
Uses Clipper2 for all polygon operations.
"""
import math
import pickle
import uuid
from pathlib import Path
from typing import List, Optional

import pyclipper

from models.schemas import Polygon, Part, AABB
from engine.geometry.polygon_utils import (
    _to_int, _to_float, _signed_area, compute_area, compute_bbox,
    compute_convex_hull, is_convex, rotate_polygon,
)


def compute_nfp(a: Polygon, b: Polygon, angle: float = 0.0) -> Polygon:
    """Compute the No-Fit Polygon of B relative to A at a given rotation angle."""
    b_outer = b.outer
    if abs(angle) > 1e-6:
        bbox_b = compute_bbox(b_outer)
        cx = (bbox_b.x_min + bbox_b.x_max) / 2
        cy = (bbox_b.y_min + bbox_b.y_max) / 2
        b_outer = rotate_polygon(b_outer, angle, cx, cy)
    if a.is_convex and is_convex(b_outer):
        return _nfp_convex(a.outer, b_outer)
    return _nfp_sliding(a.outer, b_outer)


def _nfp_convex(a_outer, b_outer):
    """NFP for two convex polygons via Minkowski sum of A and -B."""
    b_reflected = [[-x, -y] for x, y in b_outer]
    int_a = _to_int(a_outer)
    int_b_ref = _to_int(b_reflected)
    try:
        result = pyclipper.MinkowskiSum(int_a, int_b_ref, True)
    except Exception:
        return _nfp_sliding(a_outer, b_outer)
    if not result:
        return _nfp_sliding(a_outer, b_outer)
    largest = max(result, key=len)
    nfp_outer = _to_float(largest)
    if _signed_area(nfp_outer) > 0:
        nfp_outer = nfp_outer[::-1]
    return Polygon(id=str(uuid.uuid4()), outer=nfp_outer, holes=[],
                   area=compute_area(nfp_outer), bbox=compute_bbox(nfp_outer),
                   convex_hull=compute_convex_hull(nfp_outer), is_convex=True)


def _nfp_sliding(a_outer, b_outer):
    """NFP via Minkowski sum for non-convex polygons with union fallback."""
    b_reflected = [[-x, -y] for x, y in b_outer]
    int_a = _to_int(a_outer)
    int_b_ref = _to_int(b_reflected)
    try:
        result_paths = pyclipper.MinkowskiSum(int_a, int_b_ref, True)
    except Exception:
        return _nfp_bbox_fallback(a_outer, b_outer)
    if not result_paths:
        return _nfp_bbox_fallback(a_outer, b_outer)
    pc = pyclipper.Pyclipper()
    for path in result_paths:
        try:
            pc.AddPath(path, pyclipper.PT_SUBJECT, True)
        except pyclipper.ClipperException:
            continue
    try:
        union_result = pc.Execute(pyclipper.CT_UNION, pyclipper.PFT_NONZERO, pyclipper.PFT_NONZERO)
    except pyclipper.ClipperException:
        union_result = [max(result_paths, key=len)]
    if not union_result:
        return _nfp_bbox_fallback(a_outer, b_outer)
    largest = max(union_result, key=len)
    nfp_outer = _to_float(largest)
    if _signed_area(nfp_outer) > 0:
        nfp_outer = nfp_outer[::-1]
    return Polygon(id=str(uuid.uuid4()), outer=nfp_outer, holes=[],
                   area=compute_area(nfp_outer), bbox=compute_bbox(nfp_outer),
                   convex_hull=compute_convex_hull(nfp_outer), is_convex=is_convex(nfp_outer))


def _nfp_bbox_fallback(a_outer, b_outer):
    """Fallback NFP: bounding box based approximation."""
    bbox_a = compute_bbox(a_outer)
    bbox_b = compute_bbox(b_outer)
    nfp_outer = [
        [bbox_a.x_min - bbox_b.x_max, bbox_a.y_min - bbox_b.y_max],
        [bbox_a.x_max - bbox_b.x_min, bbox_a.y_min - bbox_b.y_max],
        [bbox_a.x_max - bbox_b.x_min, bbox_a.y_max - bbox_b.y_min],
        [bbox_a.x_min - bbox_b.x_max, bbox_a.y_max - bbox_b.y_min],
    ]
    return Polygon(id=str(uuid.uuid4()), outer=nfp_outer, holes=[],
                   area=compute_area(nfp_outer), bbox=compute_bbox(nfp_outer),
                   convex_hull=nfp_outer[:], is_convex=True)


def compute_ifp(part: Polygon, sheet_width: float, sheet_height: float) -> Polygon:
    """Compute the Inner Fit Polygon — valid placement region inside a sheet."""
    bbox = compute_bbox(part.outer)
    part_w = bbox.x_max - bbox.x_min
    part_h = bbox.y_max - bbox.y_min
    ifp_x_max = sheet_width - part_w
    ifp_y_max = sheet_height - part_h
    if ifp_x_max < 0 or ifp_y_max < 0:
        return Polygon(id=str(uuid.uuid4()), outer=[], holes=[], area=0,
                       bbox=AABB(x_min=0,y_min=0,x_max=0,y_max=0),
                       convex_hull=[], is_convex=False)
    ifp_outer = [[0,0],[ifp_x_max,0],[ifp_x_max,ifp_y_max],[0,ifp_y_max]]
    return Polygon(id=str(uuid.uuid4()), outer=ifp_outer, holes=[],
                   area=compute_area(ifp_outer),
                   bbox=AABB(x_min=0,y_min=0,x_max=ifp_x_max,y_max=ifp_y_max),
                   convex_hull=ifp_outer[:], is_convex=True)


class NFPCache:
    """In-memory + disk cache for NFP computations."""

    def __init__(self, cache_dir: Optional[str] = None):
        self._ram = {}
        self._disk = Path(cache_dir) if cache_dir else None
        if self._disk:
            self._disk.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> Optional[Polygon]:
        if key in self._ram:
            return self._ram[key]
        if self._disk:
            f = self._disk / f"{key}.pkl"
            if f.exists():
                try:
                    nfp = pickle.loads(f.read_bytes())
                    self._ram[key] = nfp
                    return nfp
                except Exception:
                    pass
        return None

    def set(self, key: str, nfp: Polygon) -> None:
        self._ram[key] = nfp
        if self._disk:
            try:
                (self._disk / f"{key}.pkl").write_bytes(pickle.dumps(nfp))
            except Exception:
                pass

    def has(self, key: str) -> bool:
        if key in self._ram:
            return True
        if self._disk:
            return (self._disk / f"{key}.pkl").exists()
        return False

    @staticmethod
    def make_key(a_id: str, b_id: str, angle: float) -> str:
        return f"{a_id}|{b_id}|{angle:.2f}"
