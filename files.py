"""File import routes — SVG and DXF parsing."""
import os
import uuid
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File, HTTPException

from models.schemas import ImportResult, Part
from api.routes.state import set_imported_parts

router = APIRouter()


@router.post("/import", response_model=ImportResult)
async def import_file(file: UploadFile = File(...)):
    """Import an SVG or DXF file and return parsed parts."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".svg", ".dxf"):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await file.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()

        if suffix == ".svg":
            from parsers.svg_parser import parse as parse_svg
            parts = parse_svg(Path(tmp.name))
        else:
            from parsers.dxf_parser import parse as parse_dxf
            parts = parse_dxf(Path(tmp.name))
    finally:
        os.unlink(tmp.name)

    set_imported_parts(parts)

    return ImportResult(
        parts=parts,
        warnings=[],
        part_count=len(parts),
    )
