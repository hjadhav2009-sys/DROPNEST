"""Simulated Annealing optimizer — multi-worker parallel SA."""
import math
import random
import copy
from typing import List, Optional, Callable
from rtree import index

from models.schemas import Part, Sheet, Placement, NestConfig, NestResult, Polygon, AABB
from engine.geometry.polygon_utils import (
    compute_area, compute_bbox, translate_polygon, rotate_polygon,
    _to_int, _signed_area,
)
from engine.geometry.nfp_engine import NFPCache, compute_ifp, compute_nfp
from engine.placement.blf import blf_place
import pyclipper


# Mode presets: (T_max, T_min, cooling_rate, max_iterations)
MODE_PRESETS = {
    "speed": (100.0, 1.0, 0.98, 2000),
    "balanced": (200.0, 0.1, 0.995, 20000),
    "quality": (500.0, 0.001, 0.9995, 100000),
}


def run_sa(initial_placements: List[Placement], parts: List[Part], sheet: Sheet,
           config: NestConfig, nfp_cache: Optional[NFPCache] = None,
           progress_cb: Optional[Callable] = None) -> NestResult:
    """Run Simulated Annealing optimization.

    Args:
        initial_placements: BLF initial solution.
        parts: List of parts to nest.
        sheet: Sheet to place on.
        config: Nesting configuration.
        nfp_cache: Optional NFP cache.
        progress_cb: Optional callback(iteration, waste_pct) for progress.

    Returns:
        NestResult with optimized placements.
    """
    if nfp_cache is None:
        nfp_cache = NFPCache()

    # Get SA parameters from mode or config
    mode = getattr(config, 'mode', 'balanced') if config else 'balanced'
    if mode in MODE_PRESETS:
        T_max, T_min, cooling_rate, max_iterations = MODE_PRESETS[mode]
    else:
        T_max, T_min, cooling_rate, max_iterations = MODE_PRESETS["balanced"]

    # Override with config values if provided
    if config:
        if hasattr(config, 'max_iterations') and config.max_iterations:
            max_iterations = config.max_iterations

    rotation_step = getattr(config, 'rotation_step', 90.0) if config else 90.0

    # If no initial placements, run BLF first
    if not initial_placements:
        initial_placements = blf_place(parts, sheet, nfp_cache, rotation_step)

    if not initial_placements:
        return NestResult(
            placements=[], sheets_used=1, waste_pct=100.0,
            total_area=0, placed_area=0, efficiency=0.0,
        )

    # Run SA
    best_placements, best_waste = _sa_single(
        initial_placements, parts, sheet, nfp_cache,
        T_max, T_min, cooling_rate, max_iterations, rotation_step,
        progress_cb,
    )

    sheet_area = sheet.width * sheet.height
    placed_area = sum(p.polygon.area for p in parts if any(pl.part_id == p.id for pl in best_placements))
    efficiency = (placed_area / sheet_area * 100) if sheet_area > 0 else 0

    return NestResult(
        placements=best_placements,
        sheets_used=1,
        waste_pct=best_waste,
        total_area=sheet_area,
        placed_area=placed_area,
        efficiency=efficiency,
    )


def _sa_single(placements: List[Placement], parts: List[Part], sheet: Sheet,
               nfp_cache: NFPCache, T_max: float, T_min: float,
               cooling_rate: float, max_iterations: int, rotation_step: float,
               progress_cb: Optional[Callable] = None) -> tuple:
    """Single-threaded SA run."""
    current = copy.deepcopy(placements)
    current_score = _waste_pct(current, parts, sheet)
    best = copy.deepcopy(current)
    best_score = current_score

    T = T_max
    rng = random.Random()

    for iteration in range(max_iterations):
        # Pick a random move
        move_type = rng.choice(["translate", "rotate", "swap", "reinsert"])

        if move_type == "translate" and current:
            idx = rng.randint(0, len(current) - 1)
            pl = current[idx]
            dx = rng.uniform(-50, 50)
            dy = rng.uniform(-50, 50)
            new_pl = Placement(
                part_id=pl.part_id, x=pl.x + dx, y=pl.y + dy,
                rotation=pl.rotation, flipped=pl.flipped, sheet_id=pl.sheet_id,
            )
            neighbor = current[:idx] + [new_pl] + current[idx+1:]

        elif move_type == "rotate" and current:
            idx = rng.randint(0, len(current) - 1)
            pl = current[idx]
            angles = []
            a = 0.0
            while a < 360.0 - 1e-6:
                angles.append(a)
                a += rotation_step
            new_angle = rng.choice(angles)
            new_pl = Placement(
                part_id=pl.part_id, x=pl.x, y=pl.y,
                rotation=new_angle, flipped=pl.flipped, sheet_id=pl.sheet_id,
            )
            neighbor = current[:idx] + [new_pl] + current[idx+1:]

        elif move_type == "swap" and len(current) >= 2:
            i, j = rng.sample(range(len(current)), 2)
            neighbor = current[:]
            # Swap positions
            neighbor[i] = Placement(
                part_id=neighbor[i].part_id, x=neighbor[j].x, y=neighbor[j].y,
                rotation=neighbor[i].rotation, flipped=neighbor[i].flipped,
                sheet_id=neighbor[i].sheet_id,
            )
            neighbor[j] = Placement(
                part_id=neighbor[j].part_id, x=neighbor[i].x, y=neighbor[i].y,
                rotation=neighbor[j].rotation, flipped=neighbor[j].flipped,
                sheet_id=neighbor[j].sheet_id,
            )

        elif move_type == "reinsert" and current:
            idx = rng.randint(0, len(current) - 1)
            removed = current[idx]
            remaining = current[:idx] + current[idx+1:]
            # Reinsert at a random valid position
            part = next((p for p in parts if p.id == removed.part_id), None)
            if part:
                bbox_p = compute_bbox(part.polygon.outer)
                new_x = rng.uniform(0, max(0, sheet.width - (bbox_p.x_max - bbox_p.x_min)))
                new_y = rng.uniform(0, max(0, sheet.height - (bbox_p.y_max - bbox_p.y_min)))
                new_pl = Placement(
                    part_id=removed.part_id, x=new_x, y=new_y,
                    rotation=removed.rotation, flipped=removed.flipped,
                    sheet_id=removed.sheet_id,
                )
                neighbor = remaining + [new_pl]
            else:
                neighbor = current
        else:
            neighbor = current

        # Evaluate neighbor
        if _is_valid_solution(neighbor, parts, sheet):
            neighbor_score = _waste_pct(neighbor, parts, sheet)
            delta = neighbor_score - current_score

            if delta < 0:  # Better — always accept
                current = neighbor
                current_score = neighbor_score
                if current_score < best_score:
                    best = copy.deepcopy(current)
                    best_score = current_score
            else:  # Worse — accept with probability
                if rng.random() < math.exp(-delta / max(T, 1e-10)):
                    current = neighbor
                    current_score = neighbor_score

        # Cool down
        T *= cooling_rate
        if T < T_min:
            break

        # Progress callback
        if progress_cb and iteration % 100 == 0:
            progress_cb(iteration, best_score)

    return best, best_score


def _waste_pct(placements: List[Placement], parts: List[Part], sheet: Sheet) -> float:
    """Compute waste percentage for a placement solution."""
    if not placements:
        return 100.0
    sheet_area = sheet.width * sheet.height
    if sheet_area <= 0:
        return 100.0
    placed_area = 0.0
    placed_ids = {pl.part_id for pl in placements}
    for part in parts:
        if part.id in placed_ids:
            placed_area += part.polygon.area
    # Waste = (sheet - placed) / sheet * 100
    waste = (sheet_area - placed_area) / sheet_area * 100.0
    return max(0.0, waste)


def _is_valid_solution(placements: List[Placement], parts: List[Part], sheet: Sheet) -> bool:
    """Quick validity check: all parts within sheet bounds, no major overlaps."""
    for pl in placements:
        part = next((p for p in parts if p.id == pl.part_id), None)
        if not part:
            return False
        bbox_p = compute_bbox(part.polygon.outer)
        if pl.x + bbox_p.x_max > sheet.width + 1 or pl.y + bbox_p.y_max > sheet.height + 1:
            return False
        if pl.x + bbox_p.x_min < -1 or pl.y + bbox_p.y_min < -1:
            return False

    # Check pairwise overlaps (simplified: just check bbox overlap + exact for pairs)
    for i in range(len(placements)):
        for j in range(i + 1, len(placements)):
            pi = placements[i]
            pj = placements[j]
            part_i = next((p for p in parts if p.id == pi.part_id), None)
            part_j = next((p for p in parts if p.id == pj.part_id), None)
            if not part_i or not part_j:
                continue
            bbox_i = compute_bbox(part_i.polygon.outer)
            bbox_j = compute_bbox(part_j.polygon.outer)
            # Bbox overlap check
            if (pi.x + bbox_i.x_max < pj.x + bbox_j.x_min or
                pj.x + bbox_j.x_max < pi.x + bbox_i.x_min or
                pi.y + bbox_i.y_max < pj.y + bbox_j.y_min or
                pj.y + bbox_j.y_max < pi.y + bbox_i.y_min):
                continue  # No bbox overlap — safe
            # Exact overlap check via Clipper2
            trans_i = translate_polygon(part_i.polygon.outer, pi.x, pi.y)
            trans_j = translate_polygon(part_j.polygon.outer, pj.x, pj.y)
            int_i = _to_int(trans_i)
            int_j = _to_int(trans_j)
            pc = pyclipper.Pyclipper()
            try:
                pc.AddPath(int_i, pyclipper.PT_SUBJECT, True)
                pc.AddPath(int_j, pyclipper.PT_CLIP, True)
                result = pc.Execute(pyclipper.CT_INTERSECTION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)
                for path in result:
                    if len(path) >= 3 and abs(pyclipper.Area(path)) > 100:
                        return False
            except pyclipper.ClipperException:
                continue
    return True
