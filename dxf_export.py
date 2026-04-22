"""DXF export — write nesting result as DXF."""
import io
from typing import List
from models.schemas import Placement, Sheet, Part
from engine.geometry.polygon_utils import translate_polygon, rotate_polygon, compute_bbox
import ezdxf


def export_dxf(placements: List[Placement], sheet: Sheet, parts: List[Part]) -> str:
    """Export nesting result as a DXF file string."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    # Draw sheet border
    msp.add_lwpolyline(
        [(0, 0), (sheet.width, 0), (sheet.width, sheet.height), (0, sheet.height), (0, 0)],
        dxfattribs={"layer": "SHEET", "color": 8},
    )

    part_map = {p.id: p for p in parts}

    for i, pl in enumerate(placements):
        part = part_map.get(pl.part_id)
        if not part:
            continue

        layer_name = f"PART_{i+1}"
        doc.layers.add(layer_name, color=(i % 7) + 1)

        outer = part.polygon.outer
        if abs(pl.rotation) > 1e-6:
            bbox = compute_bbox(outer)
            cx = (bbox.x_min + bbox.x_max) / 2
            cy = (bbox.y_min + bbox.y_max) / 2
            outer = rotate_polygon(outer, pl.rotation, cx, cy)
        outer = translate_polygon(outer, pl.x, pl.y)

        # Draw outer polygon
        pts = [(x, y) for x, y in outer] + [(outer[0][0], outer[0][1])]
        msp.add_lwpolyline(pts, dxfattribs={"layer": layer_name})

        # Draw holes
        for hole in part.polygon.holes:
            h = hole
            if abs(pl.rotation) > 1e-6:
                h = rotate_polygon(h, pl.rotation, cx, cy)
            h = translate_polygon(h, pl.x, pl.y)
            h_pts = [(x, y) for x, y in h] + [(h[0][0], h[0][1])]
            msp.add_lwpolyline(h_pts, dxfattribs={"layer": layer_name, "color": 1})

        # Add label
        centroid_x = sum(p[0] for p in outer) / len(outer)
        centroid_y = sum(p[1] for p in outer) / len(outer)
        msp.add_text(
            part.name,
            dxfattribs={"layer": layer_name, "height": 3, "insert": (centroid_x, centroid_y)},
        )

    # Write to string
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue()
