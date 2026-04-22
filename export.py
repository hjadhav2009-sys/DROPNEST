"""Export routes — G-code, DXF, SVG, PDF output."""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, Response

from api.routes.state import get_imported_parts, get_last_result
from engine.output.gcode import generate_gcode
from engine.output.dxf_export import export_dxf
from engine.output.svg_export import export_svg
from engine.output.pdf_export import export_pdf
from models.schemas import Sheet

router = APIRouter()


def _get_export_data():
    result = get_last_result()
    placements = result["placements"]
    sheet = result["sheet"] or Sheet(id="default", width=1000, height=500)
    parts = result["parts"] or get_imported_parts()
    return placements, sheet, parts


@router.post("/gcode/{job_id}")
async def export_gcode(job_id: str, profile: str = "cnc_router", kerf: float = 0.0,
                       lead_in: float = 0.0, lead_out: float = 0.0):
    """Export nesting result as G-code."""
    placements, sheet, parts = _get_export_data()
    if not placements:
        return {"error": "No nesting result available — run /api/nest/start first"}
    gcode = generate_gcode(placements, sheet, parts, kerf=kerf,
                           lead_in=lead_in, lead_out=lead_out, profile=profile)
    return PlainTextResponse(gcode, media_type="text/plain",
                             headers={"Content-Disposition": f"attachment; filename=nest_{job_id}.nc"})


@router.post("/dxf/{job_id}")
async def export_dxf_route(job_id: str):
    """Export nesting result as DXF."""
    placements, sheet, parts = _get_export_data()
    if not placements:
        return {"error": "No nesting result available"}
    dxf = export_dxf(placements, sheet, parts)
    return PlainTextResponse(dxf, media_type="application/dxf",
                             headers={"Content-Disposition": f"attachment; filename=nest_{job_id}.dxf"})


@router.post("/svg/{job_id}")
async def export_svg_route(job_id: str):
    """Export nesting result as SVG."""
    placements, sheet, parts = _get_export_data()
    if not placements:
        return {"error": "No nesting result available"}
    svg = export_svg(placements, sheet, parts)
    return PlainTextResponse(svg, media_type="image/svg+xml",
                             headers={"Content-Disposition": f"attachment; filename=nest_{job_id}.svg"})


@router.post("/pdf/{job_id}")
async def export_pdf_route(job_id: str):
    """Export nesting result as PDF."""
    placements, sheet, parts = _get_export_data()
    if not placements:
        return {"error": "No nesting result available"}
    pdf_bytes = export_pdf(placements, sheet, parts)
    return Response(pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=nest_{job_id}.pdf"})
