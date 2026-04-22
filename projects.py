"""Project save/load routes."""
from fastapi import APIRouter

from database.project_db import save_project as db_save, load_project as db_load, delete_project as db_delete, list_projects as db_list, init_db

router = APIRouter()


@router.get("/list")
async def list_projects():
    """List all saved projects."""
    await init_db()
    projects = await db_list()
    return {"projects": projects}


@router.post("/save")
async def save_project(data: dict):
    """Save a project to the database."""
    await init_db()
    project_id = await db_save(data)
    return {"project_id": project_id}


@router.get("/load/{project_id}")
async def load_project(project_id: str):
    """Load a project from the database."""
    await init_db()
    project = await db_load(project_id)
    if not project:
        return {"error": "Project not found", "project_id": project_id}
    return project


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    """Delete a project from the database."""
    await init_db()
    deleted = await db_delete(project_id)
    return {"deleted": deleted, "project_id": project_id}
