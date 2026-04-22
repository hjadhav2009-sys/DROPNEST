"""SVG file parser — extracts polygons from SVG shapes."""
import math
import re
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

from lxml import etree

from models.schemas import Part, Polygon, AABB
from engine.geometry.curves import flatten_bezier, flatten_arc, flatten_ellipse

SVG_NS = "http://www.w3.org/2000/svg"
DEFAULT_DPI = 96.0
DEFAULT_TOLERANCE = 0.05


def parse(filepath: Path) -> List[Part]:
    parser = SVGParser()
    return parser.parse(filepath)


class SVGParser:
    def __init__(self, tolerance: float = DEFAULT_TOLERANCE):
        self.tolerance = tolerance

    def parse(self, filepath: Path) -> List[Part]:
        tree = etree.parse(str(filepath))
        root = tree.getroot()
        viewbox = self._get_viewbox(root)
        mm_scale = self._compute_mm_scale(root, viewbox)
        shapes = []
        self._walk(root, mm_scale, shapes)
        parts = []
        for i, (outer, name) in enumerate(shapes):
            if len(outer) < 3:
                continue
            poly = self._make_polygon(outer, str(uuid.uuid4()))
            parts.append(Part(id=str(uuid.uuid4()), name=name or f"Part_{i+1}",
                              polygon=poly, quantity=1))
        return parts

    def _walk(self, element, mm_scale, shapes, parent_transform=None):
        tag = self._local_tag(element.tag)
        transform_str = element.get("transform", "")
        current_matrix = self._parse_transform(transform_str)
        if parent_transform is not None:
            current_matrix = self._compose_matrices(parent_transform, current_matrix)
        name = element.get("id", element.get("name", ""))
        polygon_pts = self._element_to_polygon(element, mm_scale, name)
        if polygon_pts is not None and len(polygon_pts) >= 3:
            if current_matrix is not None:
                polygon_pts = self._apply_matrix(polygon_pts, current_matrix)
            shapes.append((polygon_pts, name))
        for child in element:
            self._walk(child, mm_scale, shapes, current_matrix)

    def _element_to_polygon(self, element, mm_scale, name):
        tag = self._local_tag(element.tag)
        if tag == "path":
            d = element.get("d", "")
            return self._parse_path_d(d, mm_scale)
        elif tag == "rect":
            return self._parse_rect(element, mm_scale)
        elif tag == "circle":
            return self._parse_circle(element, mm_scale)
        elif tag == "ellipse":
            return self._parse_ellipse(element, mm_scale)
        elif tag == "polygon":
            return self._parse_polygon(element, mm_scale)
        elif tag == "polyline":
            return self._parse_polyline(element, mm_scale)
        return None

    def _parse_rect(self, el, scale):
        x = float(el.get("x", 0)) * scale
        y = float(el.get("y", 0)) * scale
        w = float(el.get("width", 0)) * scale
        h = float(el.get("height", 0)) * scale
        rx = float(el.get("rx", 0)) * scale
        ry = float(el.get("ry", 0)) * scale
        if rx < 1e-9 or ry < 1e-9:
            return [[x, y], [x+w, y], [x+w, y+h], [x, y+h]]
        pts = []
        corners = [
            (x+rx, y, x, y+ry, math.pi, 1.5*math.pi),
            (x+w-rx, y, x+w, y+ry, 1.5*math.pi, 2*math.pi),
            (x+w-rx, y+h, x+w, y+h-ry, 0, 0.5*math.pi),
            (x+rx, y+h, x, y+h-ry, 0.5*math.pi, math.pi),
        ]
        for cx, cy, _, _, sa, ea in corners:
            arc_pts = flatten_ellipse(cx, cy, rx, ry, sa, ea, self.tolerance)
            pts.extend(arc_pts[:-1])
        return pts

    def _parse_circle(self, el, scale):
        cx = float(el.get("cx", 0)) * scale
        cy = float(el.get("cy", 0)) * scale
        r = float(el.get("r", 0)) * scale
        if r < 1e-9:
            return []
        return flatten_arc(cx, cy, r, 0, 2*math.pi, self.tolerance)

    def _parse_ellipse(self, el, scale):
        cx = float(el.get("cx", 0)) * scale
        cy = float(el.get("cy", 0)) * scale
        rx = float(el.get("rx", 0)) * scale
        ry = float(el.get("ry", 0)) * scale
        if rx < 1e-9 or ry < 1e-9:
            return []
        return flatten_ellipse(cx, cy, rx, ry, 0, 2*math.pi, self.tolerance)

    def _parse_polygon(self, el, scale):
        return self._parse_points_attr(el.get("points", ""), scale)

    def _parse_polyline(self, el, scale):
        pts = self._parse_points_attr(el.get("points", ""), scale)
        if len(pts) >= 2:
            dx = pts[-1][0] - pts[0][0]
            dy = pts[-1][1] - pts[0][1]
            if math.sqrt(dx*dx + dy*dy) > self.tolerance:
                pts.append(pts[0][:])
        return pts

    def _parse_points_attr(self, points_str, scale):
        pts = []
        tokens = re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", points_str)
        for i in range(0, len(tokens)-1, 2):
            pts.append([float(tokens[i])*scale, float(tokens[i+1])*scale])
        return pts

    def _parse_path_d(self, d, scale):
        if not d.strip():
            return None
        commands = self._tokenize_path(d)
        if not commands:
            return None
        subpaths, current = [], []
        cx, cy, sx, sy, last_cmd = 0.0, 0.0, 0.0, 0.0, ""
        i = 0
        while i < len(commands):
            cmd = commands[i]
            if cmd in ("M", "m"):
                if current and len(current) >= 3:
                    subpaths.append(current)
                current = []; i += 1
                if cmd == "M":
                    cx = float(commands[i]) * scale; cy = float(commands[i+1]) * scale
                else:
                    cx += float(commands[i]) * scale; cy += float(commands[i+1]) * scale
                sx, sy = cx, cy; current.append([cx, cy]); i += 2; last_cmd = "L"; continue
            if cmd in ("Z", "z"):
                if current:
                    dx, dy = current[-1][0]-sx, current[-1][1]-sy
                    if math.sqrt(dx*dx+dy*dy) > self.tolerance:
                        current.append([sx, sy])
                    if len(current) >= 3:
                        subpaths.append(current)
                    current = []
                cx, cy = sx, sy; i += 1; last_cmd = "Z"; continue
            if cmd[0] in "0123456789.-+":
                cmd = last_cmd; i -= 1
            else:
                last_cmd = cmd; i += 1
            cx, cy, current, i = self._exec_path_cmd(cmd, commands, i, cx, cy, scale, current)
        if current and len(current) >= 3:
            subpaths.append(current)
        if not subpaths:
            return None
        return max(subpaths, key=len)

    def _exec_path_cmd(self, cmd, commands, i, cx, cy, scale, current):
        tol = self.tolerance
        if cmd in ("L", "l"):
            nx, ny = float(commands[i])*scale, float(commands[i+1])*scale
            if cmd == "l": nx += cx; ny += cy
            cx, cy = nx, ny; current.append([cx, cy]); i += 2
        elif cmd in ("H", "h"):
            nx = float(commands[i])*scale
            if cmd == "h": nx += cx
            cx = nx; current.append([cx, cy]); i += 1
        elif cmd in ("V", "v"):
            ny = float(commands[i])*scale
            if cmd == "v": ny += cy
            cy = ny; current.append([cx, cy]); i += 1
        elif cmd in ("C", "c"):
            x1, y1 = float(commands[i])*scale, float(commands[i+1])*scale
            x2, y2 = float(commands[i+2])*scale, float(commands[i+3])*scale
            x3, y3 = float(commands[i+4])*scale, float(commands[i+5])*scale
            if cmd == "c": x1+=cx;y1+=cy;x2+=cx;y2+=cy;x3+=cx;y3+=cy
            pts = flatten_bezier([[cx,cy],[x1,y1],[x2,y2],[x3,y3]], tol)
            current.extend(pts[1:]); cx, cy = x3, y3; i += 6
        elif cmd in ("S", "s"):
            x2, y2 = float(commands[i])*scale, float(commands[i+1])*scale
            x3, y3 = float(commands[i+2])*scale, float(commands[i+3])*scale
            if cmd == "s": x2+=cx;y2+=cy;x3+=cx;y3+=cy
            x1, y1 = 2*cx-x2, 2*cy-y2
            pts = flatten_bezier([[cx,cy],[x1,y1],[x2,y2],[x3,y3]], tol)
            current.extend(pts[1:]); cx, cy = x3, y3; i += 4
        elif cmd in ("Q", "q"):
            x1, y1 = float(commands[i])*scale, float(commands[i+1])*scale
            x2, y2 = float(commands[i+2])*scale, float(commands[i+3])*scale
            if cmd == "q": x1+=cx;y1+=cy;x2+=cx;y2+=cy
            pts = flatten_bezier([[cx,cy],[x1,y1],[x2,y2]], tol)
            current.extend(pts[1:]); cx, cy = x2, y2; i += 4
        elif cmd in ("T", "t"):
            x2, y2 = float(commands[i])*scale, float(commands[i+1])*scale
            if cmd == "t": x2+=cx;y2+=cy
            x1, y1 = 2*cx-x2, 2*cy-y2
            pts = flatten_bezier([[cx,cy],[x1,y1],[x2,y2]], tol)
            current.extend(pts[1:]); cx, cy = x2, y2; i += 2
        elif cmd in ("A", "a"):
            rx_v, ry_v = float(commands[i]), float(commands[i+1])
            x_rot, la, sw = float(commands[i+2]), int(commands[i+3]), int(commands[i+4])
            ex, ey = float(commands[i+5])*scale, float(commands[i+6])*scale
            if cmd == "a": ex+=cx;ey+=cy
            rx_v*=scale; ry_v*=scale
            arc_pts = self._svg_arc_to_polyline(cx,cy,rx_v,ry_v,x_rot,la,sw,ex,ey)
            current.extend(arc_pts[1:]); cx, cy = ex, ey; i += 7
        else:
            i += 1
        return cx, cy, current, i

    def _tokenize_path(self, d):
        d = re.sub(r"([MmZzLlHhVvCcSsQqTtAa])", r" \1 ", d)
        d = d.replace(",", " ")
        d = re.sub(r"([0-9])-(?=[0-9.])", r"\1 -", d)
        d = re.sub(r"(\.[0-9]+)(\.)", r"\1 \2", d)
        return [t for t in d.split() if t]

    def _svg_arc_to_polyline(self, x1, y1, rx, ry, phi_deg, large_arc, sweep, x2, y2):
        if rx < 1e-9 or ry < 1e-9:
            return [[x1, y1], [x2, y2]]
        phi = math.radians(phi_deg % 360)
        cos_phi, sin_phi = math.cos(phi), math.sin(phi)
        dx, dy = (x1-x2)/2.0, (y1-y2)/2.0
        x1p = cos_phi*dx + sin_phi*dy
        y1p = -sin_phi*dx + cos_phi*dy
        rx_sq, ry_sq = rx*rx, ry*ry
        x1p_sq, y1p_sq = x1p*x1p, y1p*y1p
        lam = x1p_sq/rx_sq + y1p_sq/ry_sq
        if lam > 1.0:
            s = math.sqrt(lam); rx *= s; ry *= s; rx_sq = rx*rx; ry_sq = ry*ry
        num = max(0, rx_sq*ry_sq - rx_sq*y1p_sq - ry_sq*x1p_sq)
        den = rx_sq*y1p_sq + ry_sq*x1p_sq
        if den < 1e-12:
            return [[x1, y1], [x2, y2]]
        sq = math.sqrt(num/den)
        if large_arc == sweep: sq = -sq
        cxp = sq*rx*y1p/ry; cyp = -sq*ry*x1p/rx
        cx = cos_phi*cxp - sin_phi*cyp + (x1+x2)/2.0
        cy = sin_phi*cxp + cos_phi*cyp + (y1+y2)/2.0
        def _angle(ux, uy, vx, vy):
            n = math.sqrt((ux*ux+uy*uy)*(vx*vx+vy*vy))
            if n < 1e-12: return 0.0
            c = max(-1.0, min(1.0, (ux*vx+uy*vy)/n))
            a = math.acos(c)
            return -a if ux*vy-uy*vx < 0 else a
        theta1 = _angle(1, 0, (x1p-cxp)/rx, (y1p-cyp)/ry)
        dtheta = _angle((x1p-cxp)/rx, (y1p-cyp)/ry, (-x1p-cxp)/rx, (-y1p-cyp)/ry)
        if sweep == 0 and dtheta > 0: dtheta -= 2*math.pi
        elif sweep == 1 and dtheta < 0: dtheta += 2*math.pi
        r_min = min(rx, ry)
        if self.tolerance >= r_min: num_seg = 8
        else:
            da = 2.0*math.acos(1.0-self.tolerance/r_min)
            num_seg = max(8, int(math.ceil(abs(dtheta)/da)))
        pts = []
        for k in range(num_seg+1):
            t = theta1 + dtheta*k/num_seg
            ct, st = math.cos(t), math.sin(t)
            pts.append([cos_phi*rx*ct - sin_phi*ry*st + cx,
                        sin_phi*rx*ct + cos_phi*ry*st + cy])
        return pts

    def _parse_transform(self, transform_str):
        if not transform_str or not transform_str.strip():
            return None
        result = [1, 0, 0, 1, 0, 0]
        pattern = r"(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]+)\)"
        for match in re.finditer(pattern, transform_str):
            func = match.group(1)
            args = [float(x) for x in re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", match.group(2))]
            if func == "matrix" and len(args) >= 6:
                result = self._compose_matrices(result, args[:6])
            elif func == "translate":
                tx = args[0] if len(args) >= 1 else 0
                ty = args[1] if len(args) >= 2 else 0
                result = self._compose_matrices(result, [1,0,0,1,tx,ty])
            elif func == "scale":
                sx = args[0] if len(args) >= 1 else 1
                sy = args[1] if len(args) >= 2 else sx
                result = self._compose_matrices(result, [sx,0,0,sy,0,0])
            elif func == "rotate":
                a = math.radians(args[0]); ca, sa = math.cos(a), math.sin(a)
                if len(args) >= 3:
                    cx_r, cy_r = args[1], args[2]
                    t1 = [1,0,0,1,cx_r,cy_r]
                    r = [ca,sa,-sa,ca,0,0]
                    t2 = [1,0,0,1,-cx_r,-cy_r]
                    result = self._compose_matrices(result, self._compose_matrices(t1, self._compose_matrices(r, t2)))
                else:
                    result = self._compose_matrices(result, [ca,sa,-sa,ca,0,0])
            elif func == "skewX":
                result = self._compose_matrices(result, [1,0,math.tan(math.radians(args[0])),1,0,0])
            elif func == "skewY":
                result = self._compose_matrices(result, [1,math.tan(math.radians(args[0])),0,1,0,0])
        return result

    def _compose_matrices(self, a, b):
        return [a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
                a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
                a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5]]

    def _apply_matrix(self, points, matrix):
        a, b, c, d, e, f = matrix
        return [[a*px+c*py+e, b*px+d*py+f] for px, py in points]

    def _get_viewbox(self, root):
        vb = root.get("viewBox")
        if vb:
            parts = re.findall(r"[-+]?[0-9]*\.?[0-9]+", vb)
            if len(parts) >= 4:
                return tuple(float(p) for p in parts[:4])
        return None

    def _compute_mm_scale(self, root, viewbox):
        def parse_dim(val):
            if val is None: return None
            val = val.strip()
            if val.endswith("mm"): return float(val[:-2])
            if val.endswith("cm"): return float(val[:-2]) * 10
            if val.endswith("in"): return float(val[:-2]) * 25.4
            if val.endswith("pt"): return float(re.match(r"[-+]?[0-9]*\.?[0-9]+", val).group()) * 25.4/72
            if val.endswith("pc"): return float(re.match(r"[-+]?[0-9]*\.?[0-9]+", val).group()) * 25.4/6
            try: return float(val)
            except ValueError: return None
        if viewbox is not None:
            vb_w, vb_h = viewbox[2], viewbox[3]
            w_mm = parse_dim(root.get("width"))
            h_mm = parse_dim(root.get("height"))
            if w_mm is not None and vb_w > 0: return w_mm / vb_w
            if h_mm is not None and vb_h > 0: return h_mm / vb_h
            return 25.4 / DEFAULT_DPI
        return 25.4 / DEFAULT_DPI

    def _local_tag(self, tag):
        try:
            tag = str(tag)
        except Exception:
            return ""
        if "}" in tag: return tag.split("}", 1)[1]
        return tag

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
