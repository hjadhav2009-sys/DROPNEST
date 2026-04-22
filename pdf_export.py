"""PDF export — write nesting result as PDF with reportlab."""
import io
from typing import List
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from models.schemas import Placement, Sheet, Part
from engine.geometry.polygon_utils import translate_polygon, rotate_polygon, compute_bbox

COLORS = [
    (0.23, 0.51, 0.96),  # blue
    (0.13, 0.77, 0.37),  # green
    (0.96, 0.62, 0.04),  # amber
    (0.94, 0.27, 0.27),  # red
    (0.55, 0.36, 0.96),  # purple
    (0.93, 0.29, 0.60),  # pink
    (0.08, 0.72, 0.65),  # teal
    (0.98, 0.47, 0.09),  # orange
]


def export_pdf(placements: List[Placement], sheet: Sheet, parts: List[Part]) -> bytes:
    """Export nesting result as a PDF file (bytes)."""
    buf = io.BytesIO()

    # Page size: sheet dimensions + margin
    margin = 10 * mm
    page_w = sheet.width * mm + 2 * margin
    page_h = sheet.height * mm + 2 * margin
    page_size = (page_w, page_h)

    c = pdfcanvas.Canvas(buf, pagesize=page_size)

    # Sheet border
    c.setStrokeColor((0.23, 0.29, 0.37))
    c.setLineWidth(0.5)
    c.setFillColor((0.12, 0.16, 0.23))
    c.rect(margin, margin, sheet.width * mm, sheet.height * mm, fill=1, stroke=1)

    # Grid
    c.setStrokeColor((0.16, 0.23, 0.31))
    c.setLineWidth(0.2)
    for x in range(0, int(sheet.width) + 1, 50):
        c.line(margin + x * mm, margin, margin + x * mm, margin + sheet.height * mm)
    for y in range(0, int(sheet.height) + 1, 50):
        c.line(margin, margin + y * mm, margin + sheet.width * mm, margin + y * mm)

    # Sheet label
    c.setFillColor((0.48, 0.54, 0.62))
    c.setFont("Helvetica", 8)
    c.drawString(margin + 3 * mm, margin + sheet.height * mm - 10 * mm,
                 f"{sheet.width:.0f}×{sheet.height:.0f} mm")

    # Draw parts
    part_map = {p.id: p for p in parts}
    for i, pl in enumerate(placements):
        part = part_map.get(pl.part_id)
        if not part:
            continue

        color = COLORS[i % len(COLORS)]
        c.setFillColorRGB(color[0], color[1], color[2], 0.25)
        c.setStrokeColorRGB(color[0], color[1], color[2])
        c.setLineWidth(0.3)

        outer = part.polygon.outer
        if abs(pl.rotation) > 1e-6:
            bbox = compute_bbox(outer)
            cx = (bbox.x_min + bbox.x_max) / 2
            cy = (bbox.y_min + bbox.y_max) / 2
            outer = rotate_polygon(outer, pl.rotation, cx, cy)
        outer = translate_polygon(outer, pl.x, pl.y)

        # Draw polygon path
        path = c.beginPath()
        path.moveTo(margin + outer[0][0] * mm, margin + outer[0][1] * mm)
        for pt in outer[1:]:
            path.lineTo(margin + pt[0] * mm, margin + pt[1] * mm)
        path.close()
        c.drawPath(path, fill=1, stroke=1)

        # Label
        centroid_x = sum(p[0] for p in outer) / len(outer)
        centroid_y = sum(p[1] for p in outer) / len(outer)
        c.setFillColor((1, 1, 1))
        c.setFont("Helvetica", 4)
        c.drawCentredString(margin + centroid_x * mm, margin + centroid_y * mm, part.name)

    c.showPage()
    c.save()
    return buf.getvalue()
