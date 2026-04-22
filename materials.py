"""Material library routes."""
from fastapi import APIRouter

from database.material_db import list_materials as db_list, add_material as db_add, delete_material as db_delete
from database.project_db import init_db

router = APIRouter()


@router.get("/list")
async def list_materials():
    """List all materials in the library."""
    await init_db()
    materials = await db_list()
    return {"materials": materials}


@router.post("/add")
async def add_material(data: dict):
    """Add a new material to the library."""
    await init_db()
    material_id = await db_add(data)
    return {"material_id": material_id}


@router.delete("/{material_id}")
async def delete_material(material_id: str):
    """Delete a material from the library."""
    await init_db()
    deleted = await db_delete(material_id)
    return {"deleted": deleted, "material_id": material_id}
