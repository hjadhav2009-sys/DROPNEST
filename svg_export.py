"""SVG export — write nesting result as SVG."""
from typing import List
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from models.schemas import Placement, Sheet, Part
from engine.geometry.polygon_utils import translate_polygon, rotate_polygon, compute_bbox

COLORS = [
    "#3B82F6", "#22C55E", "#F59E0B", "#EF4444", "#8B5CF6",
    "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16",
]


def export_svg(placements: List[Placement], sheet: Sheet, parts: List[Part]) -> str:
    """Export nesting result as an SVG file string."""
    margin = 10
    svg_width = sheet.width + 2 * margin
    svg_height = sheet.height + 2 * margin

    root = Element("svg",
        xmlns="http://www.w3.org/2000/svg",
        width=f"{svg_width:.1f}",
        height=f"{svg_height:.1f}",
        viewBox=f"0 0 {svg_width:.1f} {svg_height:.1f}",
    )

    # Background
    SubElement(root, "rect",
        x="0", y="0",
        width=f"{svg_width:.1f}", height=f"{svg_height:.1f}",
        fill="#0D1520",
    )

    # Sheet border
    g_sheet = SubElement(root, "g", transform=f"translate({margin},{margin})")
    SubElement(g_sheet, "rect",
        x="0", y="0",
        width=f"{sheet.width:.1f}", height=f"{sheet.height:.1f}",
        fill="#1E2A3A", stroke="#3A4A5E", stroke_width="0.5",
    )

    # Grid
    for x in range(0, int(sheet.width) + 1, 50):
        SubElement(g_sheet, "line",
            x1=f"{x}", y1="0", x2=f"{x}", y2=f"{sheet.height:.1f}",
            stroke="#2A3A4E", stroke_width="0.2",
        )
    for y in range(0, int(sheet.height) + 1, 50):
        SubElement(g_sheet, "line",
            x1="0", y1=f"{y}", x2=f"{sheet.width:.1f}", y2=f"{y}",
            stroke="#2A3A4E", stroke_width="0.2",
        )

    # Sheet label
    SubElement(g_sheet, "text",
        x="5", y="15",
        fill="#7A8A9E", **{"font-size": "12", "font-family": "sans-serif"},
    ).text = f"{sheet.width:.0f}×{sheet.height:.0f} mm"

    # Parts
    part_map = {p.id: p for p in parts}
    for i, pl in enumerate(placements):
        part = part_map.get(pl.part_id)
        if not part:
            continue

        color = COLORS[i % len(COLORS)]
        g_part = SubElement(g_sheet, "g")

        outer = part.polygon.outer
        if abs(pl.rotation) > 1e-6:
            bbox = compute_bbox(outer)
            cx = (bbox.x_min + bbox.x_max) / 2
            cy = (bbox.y_min + bbox.y_max) / 2
            outer = rotate_polygon(outer, pl.rotation, cx, cy)
        outer = translate_polygon(outer, pl.x, pl.y)

        # Build polygon points string
        points = " ".join(f"{x:.2f},{y:.2f}" for x, y in outer)
        SubElement(g_part, "polygon",
            points=points,
            fill=color + "44", stroke=color, stroke_width="0.3",
        )

        # Holes
        for hole in part.polygon.holes:
            h = hole
            if abs(pl.rotation) > 1e-6:
                h = rotate_polygon(h, pl.rotation, cx, cy)
            h = translate_polygon(h, pl.x, pl.y)
            h_points = " ".join(f"{x:.2f},{y:.2f}" for x, y in h)
            SubElement(g_part, "polygon",
                points=h_points,
                fill="#0D1520", stroke=color, stroke_width="0.2",
            )

        # Label
        centroid_x = sum(p[0] for p in outer) / len(outer)
        centroid_y = sum(p[1] for p in outer) / len(outer)
        SubElement(g_part, "text",
            x=f"{centroid_x:.1f}", y=f"{centroid_y:.1f}",
            fill="white", **{"font-size": "6", "font-family": "sans-serif", "text-anchor": "middle"},
        ).text = part.name

    # Pretty print
    rough = tostring(root, encoding="unicode")
    return minidom.parseString(rough).toprettyxml(indent="  ")
