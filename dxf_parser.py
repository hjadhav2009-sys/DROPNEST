"""DXF file parser — extracts polygons from DXF entities."""
import math
import uuid
from pathlib import Path
from typing import List, Optional, Tuple
from collections import defaultdict

import ezdxf

from models.schemas import Part, Polygon, AABB
from engine.geometry.curves import flatten_arc, flatten_ellipse

GAP_TOLERANCE = 0.1  # mm — for grouping LINE segments


def parse(filepath: Path) -> List[Part]:
    parser = DXFParser()
    return parser.parse(filepath)


class DXFParser:
    def __init__(self, tolerance: float = 0.05):
        self.tolerance = tolerance

    def parse(self, filepath: Path) -> List[Part]:
        doc = ezdxf.readfile(str(filepath))
        msp = doc.modelspace()
        parts = []
        for entity in msp:
            polygon_pts = self._entity_to_polygon(entity)
            if polygon_pts and len(polygon_pts) >= 3:
                layer = entity.dxf.layer if entity.dxf.hasattr("layer") else "0"
                poly = self._make_polygon(polygon_pts, str(uuid.uuid4()))
                parts.append(Part(
                    id=str(uuid.uuid4()),
                    name=f"{layer}_{entity.dxftype()}_{len(parts)+1}",
                    polygon=poly, quantity=1,
                ))
        # Group LINE segments into closed polygons
        parts += self._group_lines(msp)
        return parts

    def _entity_to_polygon(self, entity) -> Optional[List[List[float]]]:
        dxftype = entity.dxftype()

        if dxftype == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in entity.get_points("xy")]
            if entity.closed:
                return [[x, y] for x, y in pts]
            elif len(pts) >= 3:
                return [[x, y] for x, y in pts]
            return None

        elif dxftype == "POLYLINE":
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
            if entity.is_closed:
                pts.append(pts[0])
            if len(pts) >= 3:
                return [[x, y] for x, y in pts]
            return None

        elif dxftype == "LINE":
            # Lines are handled separately in _group_lines
            return None

        elif dxftype == "CIRCLE":
            cx = entity.dxf.center.x
            cy = entity.dxf.center.y
            r = entity.dxf.radius
            return flatten_arc(cx, cy, r, 0, 2*math.pi, self.tolerance)

        elif dxftype == "ARC":
            cx = entity.dxf.center.x
            cy = entity.dxf.center.y
            r = entity.dxf.radius
            start = math.radians(entity.dxf.start_angle)
            end = math.radians(entity.dxf.end_angle)
            return flatten_arc(cx, cy, r, start, end, self.tolerance)

        elif dxftype == "ELLIPSE":
            cx = entity.dxf.center.x
            cy = entity.dxf.center.y
            # ezdxf gives major_axis as Vec3, ratio for minor
            major = entity.dxf.major_axis
            rx = math.sqrt(major.x**2 + major.y**2)
            ry = rx * entity.dxf.ratio
            rotation = math.atan2(major.y, major.x)
            # Param range
            start_param = entity.dxf.start_param if entity.dxf.hasattr("start_param") else 0
            end_param = entity.dxf.end_param if entity.dxf.hasattr("end_param") else 2*math.pi
            pts = flatten_ellipse(0, 0, rx, ry, start_param, end_param, self.tolerance)
            # Rotate and translate
            cos_r, sin_r = math.cos(rotation), math.sin(rotation)
            result = []
            for px, py in pts:
                rx2 = cos_r*px - sin_r*py + cx
                ry2 = sin_r*px + cos_r*py + cy
                result.append([rx2, ry2])
            return result

        elif dxftype == "SPLINE":
            try:
                pts = list(entity.flattening(self.tolerance))
                return [[p.x, p.y] for p in pts]
            except Exception:
                return None

        elif dxftype == "HATCH":
            return self._parse_hatch(entity)

        elif dxftype == "INSERT":
            return self._expand_block(entity)

        return None

    def _parse_hatch(self, entity) -> Optional[List[List[float]]]:
        """Extract the outermost boundary path from a HATCH entity."""
        try:
            paths = entity.paths
            if not paths:
                return None
            # Use the first boundary path as the polygon
            for path in paths:
                if hasattr(path, "edges"):
                    pts = []
                    for edge in path.edges:
                        if edge.EDGE_TYPE == "LineEdge":
                            pts.append([edge.start[0], edge.start[1]])
                        elif edge.EDGE_TYPE == "ArcEdge":
                            arc_pts = flatten_arc(
                                edge.center[0], edge.center[1],
                                math.sqrt(edge.start_angle**2 + 1),  # approximate
                                0, 2*math.pi, self.tolerance
                            )
                            pts.extend(arc_pts)
                        elif edge.EDGE_TYPE == "EllipseEdge":
                            pts.append([edge.start[0], edge.start[1]])
                    if len(pts) >= 3:
                        return pts
                elif hasattr(path, "vertices"):
                    verts = list(path.vertices)
                    if len(verts) >= 3:
                        return [[v[0], v[1]] for v in verts]
        except Exception:
            pass
        return None

    def _expand_block(self, entity) -> Optional[List[List[float]]]:
        """Expand an INSERT (block reference) recursively."""
        try:
            block = entity.entitydb[entity.dxf.name]
            # Not fully expanding blocks — return None for now
            return None
        except Exception:
            return None

    def _group_lines(self, msp) -> List[Part]:
        """Group disconnected LINE entities into closed polygons (gap tolerance 0.1mm)."""
        lines = []
        for entity in msp:
            if entity.dxftype() == "LINE":
                x1, y1 = entity.dxf.start.x, entity.dxf.start.y
                x2, y2 = entity.dxf.end.x, entity.dxf.end.y
                lines.append(((x1, y1), (x2, y2), entity.dxf.layer if entity.dxf.hasattr("layer") else "0"))

        if not lines:
            return []

        # Build adjacency: endpoint -> list of line indices
        chains = []
        used = set()
        for i, (start, end, layer) in enumerate(lines):
            if i in used:
                continue
            chain = [start, end]
            used.add(i)
            # Try to extend chain from the end
            changed = True
            while changed:
                changed = False
                for j, (s, e, l) in enumerate(lines):
                    if j in used:
                        continue
                    # Check if end of chain matches start of this line
                    if self._points_close(chain[-1], s):
                        chain.append(e)
                        used.add(j)
                        changed = True
                    elif self._points_close(chain[-1], e):
                        chain.append(s)
                        used.add(j)
                        changed = True
                    # Check start of chain
                    elif self._points_close(chain[0], s):
                        chain.insert(0, e)
                        used.add(j)
                        changed = True
                    elif self._points_close(chain[0], e):
                        chain.insert(0, s)
                        used.add(j)
                        changed = True
            # Check if chain is closed
            if len(chain) >= 3 and self._points_close(chain[0], chain[-1]):
                polygon_pts = [[x, y] for x, y in chain[:-1]]
                poly = self._make_polygon(polygon_pts, str(uuid.uuid4()))
                chains.append(Part(
                    id=str(uuid.uuid4()),
                    name=f"{layer}_LINE_group_{len(chains)+1}",
                    polygon=poly, quantity=1,
                ))
        return chains

    def _points_close(self, p1, p2) -> bool:
        dx = p1[0] - p2[0]
        dy = p1[1] - p2[1]
        return math.sqrt(dx*dx + dy*dy) < GAP_TOLERANCE

    def _make_polygon(self, outer, poly_id):
        xs = [p[0] for p in outer]; ys = [p[1] for p in outer]
        bbox = AABB(x_min=min(xs), y_min=min(ys), x_max=max(xs), y_max=max(ys))
        area = 0.0
        n = len(outer)
        for i in range(n):
            j = (i+1) % n
            area += outer[i][0]*outer[j][1] - outer[j][0]*outer[i][1]
        area = abs(area) / 2.0
        is_convex = self._check_convex(outer)
        return Polygon(id=poly_id, outer=outer, holes=[], area=area,
                       bbox=bbox, convex_hull=outer, is_convex=is_convex)

    def _check_convex(self, pts):
        n = len(pts)
        if n < 3: return False
        sign = None
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i+1)%n]
            x3, y3 = pts[(i+2)%n]
            cross = (x2-x1)*(y3-y2) - (y2-y1)*(x3-x2)
            if abs(cross) < 1e-9: continue
            if sign is None: sign = cross > 0
            elif (cross > 0) != sign: return False
        return True
