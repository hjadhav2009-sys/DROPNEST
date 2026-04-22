"""DropNest Pydantic data models."""
from typing import List, Optional
from pydantic import BaseModel


class Point(BaseModel):
    x: float
    y: float


class AABB(BaseModel):
    x_min: float
    y_min: float
    x_max: float
    y_max: float


class Polygon(BaseModel):
    id: str
    outer: List[List[float]]
    holes: List[List[List[float]]]
    area: float
    bbox: AABB
    convex_hull: List[List[float]]
    is_convex: bool


class Part(BaseModel):
    id: str
    name: str
    polygon: Polygon
    quantity: int = 1
    grain_dir: Optional[float] = None
    rotation_step: float = 90.0
    allow_flip: bool = False


class Sheet(BaseModel):
    id: str
    width: float
    height: float
    material: str = ""
    cost: float = 0.0
    defect_zones: List[Polygon] = []


class Placement(BaseModel):
    part_id: str
    sheet_id: str = "default"
    x: float
    y: float
    rotation: float
    flipped: bool = False


class NestConfig(BaseModel):
    mode: str = "quality"
    rotation_step: float = 90.0
    max_iterations: int = 5000
    num_workers: int = 8
    spacing: float = 0.0
    kerf: float = 0.0
    sheet_width: float = 1000.0
    sheet_height: float = 500.0


class NestResult(BaseModel):
    job_id: str = ""
    placements: List[Placement]
    sheets_used: int
    waste_pct: float
    total_area: float = 0.0
    placed_area: float = 0.0
    efficiency: float = 0.0
    total_cost: float = 0.0
    cut_time_sec: float = 0.0
    iterations: int = 0


class ImportResult(BaseModel):
    parts: List[Part]
    warnings: List[str]
    part_count: int


class HealthResponse(BaseModel):
    status: str
    version: float
