"""DWG to DXF converter using LibreOffice CLI or ODA File Converter."""
import subprocess
import shutil
from pathlib import Path


def convert(dwg_path: Path, output_dir: Path = None) -> Path:
    """Convert a DWG file to DXF using LibreOffice CLI or ODA File Converter.

    Args:
        dwg_path: Path to the .dwg file.
        output_dir: Optional output directory. Defaults to same as input.

    Returns:
        Path to the converted .dxf file.

    Raises:
        RuntimeError: If no converter is available.
    """
    if output_dir is None:
        output_dir = dwg_path.parent

    dxf_path = output_dir / (dwg_path.stem + ".dxf")

    # Try ODA File Converter first (better quality)
    oda = shutil.which("ODAFileConverter")
    if oda:
        try:
            result = subprocess.run(
                [oda, str(dwg_path.parent), str(output_dir), "ACAD2010", "DXF", "0", "1", str(dwg_path.name)],
                capture_output=True, timeout=60,
            )
            if dxf_path.exists():
                return dxf_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Try LibreOffice
    lo = shutil.which("soffice") or shutil.which("libreoffice")
    if lo:
        try:
            result = subprocess.run(
                [lo, "--headless", "--convert-to", "dxf", "--outdir", str(output_dir), str(dwg_path)],
                capture_output=True, timeout=60,
            )
            if dxf_path.exists():
                return dxf_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    raise RuntimeError(
        "No DWG converter available. Install LibreOffice or ODA File Converter. "
        "Alternatively, export your DWG to DXF manually in AutoCAD."
    )
