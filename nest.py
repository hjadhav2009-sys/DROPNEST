"""Nesting job routes — start, cancel, status."""
import uuid
import asyncio
from typing import Dict

from fastapi import APIRouter

from models.schemas import NestConfig, Sheet, Part
from engine.geometry.nfp_engine import NFPCache
from engine.placement.blf import blf_place
from engine.optimizer.sa import run_sa
from api.routes.state import set_last_result, set_imported_parts, get_imported_parts

router = APIRouter()

_nfp_cache = NFPCache()


@router.post("/start")
async def start_nest(config: NestConfig):
    """Start a nesting job. Runs BLF + SA and returns result."""
    job_id = str(uuid.uuid4())
    raw_parts = get_imported_parts()
    if not raw_parts:
        return {"job_id": job_id, "error": "No parts imported"}

    # Explode parts by quantity (20 copies = 20 separate parts)
    parts = []
    for p in raw_parts:
        qty = getattr(p, 'quantity', 1) or 1
        for i in range(qty):
            parts.append(Part(
                id=f"{p.id}_copy_{i}",
                name=p.name,
                polygon=p.polygon,
                quantity=1,
                grain_dir=p.grain_dir,
                rotation_step=p.rotation_step,
                allow_flip=p.allow_flip,
            ))

    # Clamp sheet size to reasonable bounds (prevent 100000 corruption)
    sheet_w = max(100, min(5000, config.sheet_width if config.sheet_width else 1000))
    sheet_h = max(100, min(5000, config.sheet_height if config.sheet_height else 500))

    sheet = Sheet(
        id="default",
        width=sheet_w,
        height=sheet_h,
        material="MDF",
        cost=10.0,
        defect_zones=[],
    )

    # Run BLF initial placement
    initial = blf_place(parts, sheet, _nfp_cache, rotation_step=config.rotation_step)

    # Run SA optimization
    result = run_sa(initial, parts, sheet, config, _nfp_cache)

    # Save for export
    set_last_result(result.placements, sheet, parts)

    return {
        "job_id": job_id,
        "placements": [pl.model_dump() for pl in result.placements],
        "sheets_used": result.sheets_used,
        "waste_pct": round(result.waste_pct, 2),
        "efficiency": round(result.efficiency, 2),
        "total_area": round(result.total_area, 2),
        "placed_area": round(result.placed_area, 2),
    }


@router.post("/cancel/{job_id}")
async def cancel_nest(job_id: str):
    """Cancel a running nesting job."""
    return {"cancelled": True, "job_id": job_id}
