"""DropNest FastAPI backend — main application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import files, nest, export, projects, materials
from api.websocket import router as ws_router
from models.schemas import HealthResponse

app = FastAPI(title="DropNest", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(nest.router, prefix="/api/nest", tags=["nest"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(materials.router, prefix="/api/materials", tags=["materials"])
app.include_router(ws_router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", version=1.0)
