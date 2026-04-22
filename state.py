"""Shared state between routes — breaks circular import between nest and export."""
from typing import Dict, List, Optional

# Parts imported via /api/files/import
_imported_parts: Dict[str, list] = {"parts": []}

# Last nesting result for export
_last_result: Dict = {"placements": [], "sheet": None, "parts": []}


def set_imported_parts(parts: list):
    _imported_parts["parts"] = parts


def get_imported_parts() -> list:
    return _imported_parts["parts"]


def set_last_result(placements, sheet, parts):
    _last_result["placements"] = placements
    _last_result["sheet"] = sheet
    _last_result["parts"] = parts


def get_last_result() -> dict:
    return _last_result
