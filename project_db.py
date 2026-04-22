"""Project database — SQLite save/load for projects, parts, placements."""
import aiosqlite
import json
import time
import uuid
from pathlib import Path
from typing import Optional, List

DB_PATH = Path(__file__).parent.parent / "dropnest.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def get_db() -> aiosqlite.Connection:
    """Get a database connection, initializing schema if needed."""
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def init_db() -> None:
    """Initialize database schema from schema.sql."""
    db = await get_db()
    try:
        with open(SCHEMA_PATH, "r") as f:
            await db.executescript(f.read())
        await db.commit()
    finally:
        await db.close()


async def save_project(project_data: dict) -> str:
    """Save or update a project and all its parts/sheets/placements."""
    db = await get_db()
    try:
        now = int(time.time())
        project_id = project_data.get("id") or str(uuid.uuid4())

        # Upsert project
        existing = await db.execute_fetchall(
            "SELECT id FROM projects WHERE id = ?", (project_id,)
        )
        if existing:
            await db.execute(
                "UPDATE projects SET name=?, updated_at=?, config_json=?, status=? WHERE id=?",
                (project_data.get("name", "Untitled"), now,
                 json.dumps(project_data.get("config", {})),
                 project_data.get("status", "draft"), project_id),
            )
        else:
            await db.execute(
                "INSERT INTO projects (id, name, created_at, updated_at, config_json, status) VALUES (?,?,?,?,?,?)",
                (project_id, project_data.get("name", "Untitled"), now, now,
                 json.dumps(project_data.get("config", {})),
                 project_data.get("status", "draft")),
            )

        # Delete existing parts/sheets/placements for this project (replace)
        await db.execute("DELETE FROM placements WHERE project_id=?", (project_id,))
        await db.execute("DELETE FROM parts WHERE project_id=?", (project_id,))
        await db.execute("DELETE FROM sheets WHERE project_id=?", (project_id,))

        # Insert parts
        for part in project_data.get("parts", []):
            poly = part.get("polygon", part)
            await db.execute(
                "INSERT INTO parts (id, project_id, name, quantity, polygon_json, area_mm2, grain_angle, rotation_step, allow_flip) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (part.get("id", str(uuid.uuid4())), project_id,
                 part.get("name", "part"), part.get("quantity", 1),
                 json.dumps(poly), poly.get("area", 0),
                 part.get("grain_dir"), part.get("rotation_step", 90.0),
                 1 if part.get("allow_flip") else 0),
            )

        # Insert sheets
        for sheet in project_data.get("sheets", []):
            await db.execute(
                "INSERT INTO sheets (id, project_id, width, height, material, cost, defect_json) VALUES (?,?,?,?,?,?,?)",
                (sheet.get("id", str(uuid.uuid4())), project_id,
                 sheet.get("width", 1000), sheet.get("height", 500),
                 sheet.get("material", ""), sheet.get("cost", 0),
                 json.dumps(sheet.get("defect_zones", []))),
            )

        # Insert placements
        for pl in project_data.get("placements", []):
            await db.execute(
                "INSERT INTO placements (id, project_id, part_id, sheet_id, x, y, rotation, flipped) VALUES (?,?,?,?,?,?,?,?)",
                (pl.get("id", str(uuid.uuid4())), project_id,
                 pl.get("part_id"), pl.get("sheet_id"),
                 pl.get("x", 0), pl.get("y", 0),
                 pl.get("rotation", 0), 1 if pl.get("flipped") else 0),
            )

        await db.commit()
        return project_id
    finally:
        await db.close()


async def load_project(project_id: str) -> Optional[dict]:
    """Load a complete project with parts, sheets, and placements."""
    db = await get_db()
    try:
        # Project
        row = await db.execute_fetchall("SELECT * FROM projects WHERE id=?", (project_id,))
        if not row:
            return None
        p = dict(row[0])

        # Parts
        parts_rows = await db.execute_fetchall("SELECT * FROM parts WHERE project_id=?", (project_id,))
        parts = []
        for r in parts_rows:
            d = dict(r)
            d["polygon"] = json.loads(d.pop("polygon_json", "{}"))
            d["allow_flip"] = bool(d.pop("allow_flip", 0))
            d["grain_dir"] = d.pop("grain_angle", None)
            parts.append(d)

        # Sheets
        sheets_rows = await db.execute_fetchall("SELECT * FROM sheets WHERE project_id=?", (project_id,))
        sheets = []
        for r in sheets_rows:
            d = dict(r)
            d["defect_zones"] = json.loads(d.pop("defect_json", "[]"))
            sheets.append(d)

        # Placements
        pl_rows = await db.execute_fetchall("SELECT * FROM placements WHERE project_id=?", (project_id,))
        placements = []
        for r in pl_rows:
            d = dict(r)
            d["flipped"] = bool(d.pop("flipped", 0))
            placements.append(d)

        return {
            "id": p["id"], "name": p["name"],
            "created_at": p["created_at"], "updated_at": p["updated_at"],
            "config": json.loads(p.get("config_json", "{}")),
            "status": p["status"],
            "parts": parts, "sheets": sheets, "placements": placements,
        }
    finally:
        await db.close()


async def delete_project(project_id: str) -> bool:
    """Delete a project and all related data (CASCADE)."""
    db = await get_db()
    try:
        cursor = await db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def list_projects() -> List[dict]:
    """List all projects (id, name, created_at, status)."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT id, name, created_at, updated_at, status FROM projects ORDER BY updated_at DESC"
        )
        return [dict(r) for r in rows]
    finally:
        await db.close()
