"""Material library database — CRUD for material presets."""
import aiosqlite
import uuid
from pathlib import Path
from typing import List, Optional

DB_PATH = Path(__file__).parent.parent / "dropnest.db"


async def _get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db


async def list_materials() -> List[dict]:
    """List all materials in the library."""
    db = await _get_db()
    try:
        rows = await db.execute_fetchall("SELECT * FROM materials ORDER BY name")
        return [dict(r) for r in rows]
    finally:
        await db.close()


async def add_material(material_data: dict) -> str:
    """Add a new material. Returns material_id."""
    db = await _get_db()
    try:
        material_id = material_data.get("id") or str(uuid.uuid4())
        await db.execute(
            "INSERT INTO materials (id, name, thickness, width, height, cost_per_sheet, grain_dir) VALUES (?,?,?,?,?,?,?)",
            (material_id, material_data.get("name", "Unknown"),
             material_data.get("thickness", 0), material_data.get("width"),
             material_data.get("height"), material_data.get("cost_per_sheet", 0),
             material_data.get("grain_dir")),
        )
        await db.commit()
        return material_id
    finally:
        await db.close()


async def delete_material(material_id: str) -> bool:
    """Delete a material from the library."""
    db = await _get_db()
    try:
        cursor = await db.execute("DELETE FROM materials WHERE id=?", (material_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()
