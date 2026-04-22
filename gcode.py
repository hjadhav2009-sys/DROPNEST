"""G-code output generator — CNC router / laser / plasma."""
import math
from typing import List, Dict, Optional
from models.schemas import Placement, Sheet, Part, Polygon
from engine.geometry.polygon_utils import (
    translate_polygon, rotate_polygon, offset, compute_bbox,
)


# Machine profile presets
PROFILES = {
    "cnc_router": {
        "rapid_height": 5.0,      # mm above work
        "cut_depth": 3.0,         # mm per pass
        "total_depth": 6.0,       # mm final depth
        "feed_rate": 1200,        # mm/min
        "plunge_rate": 300,       # mm/min
        "spindle_speed": 18000,   # RPM
        "units": "mm",
    },
    "laser": {
        "power": 80,              # % laser power
        "feed_rate": 3000,        # mm/min
        "passes": 1,
        "units": "mm",
    },
    "plasma": {
        "amperage": 45,           # A
        "feed_rate": 2500,        # mm/min
        "pierce_delay": 0.5,     # seconds
        "units": "mm",
    },
}


def generate_gcode(placements: List[Placement], sheet: Sheet, parts: List[Part],
                   kerf: float = 0.0, lead_in: float = 0.0, lead_out: float = 0.0,
                   profile: str = "cnc_router") -> str:
    """Generate G-code for all placed parts on a sheet.

    Includes kerf compensation, lead-in/out, machine profile settings.
    """
    lines = []
    cfg = PROFILES.get(profile, PROFILES["cnc_router"])

    # Build part lookup
    part_map = {p.id: p for p in parts}

    # Header
    lines.append(f"; DropNest G-code — {profile} profile")
    lines.append(f"; Sheet: {sheet.width:.1f} x {sheet.height:.1f} mm")
    lines.append(f"; Parts: {len(placements)}, Kerf: {kerf:.2f} mm")
    lines.append(f"; Lead-in: {lead_in:.1f} mm, Lead-out: {lead_out:.1f} mm")
    lines.append("")

    # Startup sequence
    if profile == "cnc_router":
        lines.extend(_cnc_startup(cfg))
    elif profile == "laser":
        lines.extend(_laser_startup(cfg))
    elif profile == "plasma":
        lines.extend(_plasma_startup(cfg))

    # Cut each part
    for i, pl in enumerate(placements):
        part = part_map.get(pl.part_id)
        if not part:
            continue

        lines.append(f"; --- Part {i+1}: {part.name} ---")

        # Get the polygon at its placed position and rotation
        outer = part.polygon.outer
        if abs(pl.rotation) > 1e-6:
            bbox = compute_bbox(outer)
            cx = (bbox.x_min + bbox.x_max) / 2
            cy = (bbox.y_min + bbox.y_max) / 2
            outer = rotate_polygon(outer, pl.rotation, cx, cy)
        outer = translate_polygon(outer, pl.x, pl.y)

        # Apply kerf compensation (offset polygon outward by kerf/2)
        if kerf > 0:
            kerf_poly = Polygon(
                id=part.polygon.id, outer=outer, holes=part.polygon.holes,
                area=0, bbox=compute_bbox(outer), convex_hull=[], is_convex=False,
            )
            offset_poly = offset(kerf_poly, kerf / 2)
            outer = offset_poly.outer

        # Add lead-in/out
        if lead_in > 0 or lead_out > 0:
            outer = _add_leads(outer, lead_in, lead_out)

        # Generate cut path
        if profile == "cnc_router":
            lines.extend(_cnc_cut_path(outer, cfg))
        elif profile == "laser":
            lines.extend(_laser_cut_path(outer, cfg))
        elif profile == "plasma":
            lines.extend(_plasma_cut_path(outer, cfg))

    # Shutdown sequence
    if profile == "cnc_router":
        lines.extend(_cnc_shutdown(cfg))
    elif profile == "laser":
        lines.extend(_laser_shutdown(cfg))
    elif profile == "plasma":
        lines.extend(_plasma_shutdown(cfg))

    return "\n".join(lines)


def _add_leads(outer: List[List[float]], lead_in: float, lead_out: float) -> List[List[float]]:
    """Add lead-in and lead-out segments to the polygon path."""
    if len(outer) < 2:
        return outer
    # Lead-in: extend from a point before the first vertex
    p0 = outer[0]
    p1 = outer[1] if len(outer) > 1 else outer[0]
    dx = p0[0] - p1[0]
    dy = p0[1] - p1[1]
    length = math.sqrt(dx*dx + dy*dy)
    if length > 1e-6:
        dx /= length
        dy /= length
    else:
        dx, dy = 1.0, 0.0

    lead_in_pt = [p0[0] + dx * lead_in, p0[1] + dy * lead_in]

    # Lead-out: extend from the last vertex
    pn = outer[-1]
    pn1 = outer[-2] if len(outer) > 1 else outer[-1]
    dx2 = pn[0] - pn1[0]
    dy2 = pn[1] - pn1[1]
    length2 = math.sqrt(dx2*dx2 + dy2*dy2)
    if length2 > 1e-6:
        dx2 /= length2
        dy2 /= length2
    else:
        dx2, dy2 = 1.0, 0.0

    lead_out_pt = [pn[0] + dx2 * lead_out, pn[1] + dy2 * lead_out]

    return [lead_in_pt] + outer + [lead_out_pt]


# --- CNC Router ---

def _cnc_startup(cfg: dict) -> List[str]:
    return [
        "G21 ; Set units to mm",
        "G90 ; Absolute positioning",
        f"G0 Z{cfg['rapid_height']:.1f} ; Raise to safe height",
        f"M3 S{cfg['spindle_speed']} ; Start spindle",
        "G4 P2 ; Wait for spindle to reach speed",
        "",
    ]


def _cnc_cut_path(outer: List[List[float]], cfg: dict) -> List[str]:
    lines = []
    n_passes = max(1, int(math.ceil(cfg["total_depth"] / cfg["cut_depth"])))

    for pass_num in range(n_passes):
        depth = min(cfg["cut_depth"] * (pass_num + 1), cfg["total_depth"])
        # Rapid to lead-in position
        lines.append(f"G0 X{outer[0][0]:.3f} Y{outer[0][1]:.3f}")
        # Plunge
        lines.append(f"G1 Z-{depth:.2f} F{cfg['plunge_rate']}")
        # Cut along path
        for pt in outer[1:]:
            lines.append(f"G1 X{pt[0]:.3f} Y{pt[1]:.3f} F{cfg['feed_rate']}")
        # Close path
        lines.append(f"G1 X{outer[0][0]:.3f} Y{outer[0][1]:.3f} F{cfg['feed_rate']}")
        # Retract
        lines.append(f"G0 Z{cfg['rapid_height']:.1f}")

    return lines


def _cnc_shutdown(cfg: dict) -> List[str]:
    return [
        f"G0 Z{cfg['rapid_height']:.1f} ; Raise to safe height",
        "M5 ; Stop spindle",
        "G0 X0 Y0 ; Return to origin",
        "M2 ; End program",
        "",
    ]


# --- Laser ---

def _laser_startup(cfg: dict) -> List[str]:
    return [
        "G21 ; Set units to mm",
        "G90 ; Absolute positioning",
        "G0 X0 Y0 ; Home position",
        "",
    ]


def _laser_cut_path(outer: List[List[float]], cfg: dict) -> List[str]:
    lines = []
    for pass_num in range(cfg.get("passes", 1)):
        # Rapid to start
        lines.append(f"G0 X{outer[0][0]:.3f} Y{outer[0][1]:.3f}")
        # Laser on
        lines.append(f"M3 S{cfg['power']} ; Laser on at {cfg['power']}%")
        # Cut
        for pt in outer[1:]:
            lines.append(f"G1 X{pt[0]:.3f} Y{pt[1]:.3f} F{cfg['feed_rate']}")
        # Close
        lines.append(f"G1 X{outer[0][0]:.3f} Y{outer[0][1]:.3f} F{cfg['feed_rate']}")
        # Laser off
        lines.append("M5 ; Laser off")
    return lines


def _laser_shutdown(cfg: dict) -> List[str]:
    return [
        "M5 ; Laser off",
        "G0 X0 Y0 ; Return to origin",
        "M2 ; End program",
        "",
    ]


# --- Plasma ---

def _plasma_startup(cfg: dict) -> List[str]:
    return [
        "G21 ; Set units to mm",
        "G90 ; Absolute positioning",
        "G0 X0 Y0 ; Home position",
        "",
    ]


def _plasma_cut_path(outer: List[List[float]], cfg: dict) -> List[str]:
    lines = []
    # Rapid to start
    lines.append(f"G0 X{outer[0][0]:.3f} Y{outer[0][1]:.3f}")
    # Pierce
    lines.append(f"M3 ; Torch on")
    lines.append(f"G4 P{cfg['pierce_delay']:.1f} ; Pierce delay")
    # Cut
    for pt in outer[1:]:
        lines.append(f"G1 X{pt[0]:.3f} Y{pt[1]:.3f} F{cfg['feed_rate']}")
    # Close
    lines.append(f"G1 X{outer[0][0]:.3f} Y{outer[0][1]:.3f} F{cfg['feed_rate']}")
    # Torch off
    lines.append("M5 ; Torch off")
    return lines


def _plasma_shutdown(cfg: dict) -> List[str]:
    return [
        "M5 ; Torch off",
        "G0 X0 Y0 ; Return to origin",
        "M2 ; End program",
        "",
    ]
