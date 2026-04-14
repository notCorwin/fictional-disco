"""Step 0: 将输入文件统一转换为 PDF。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import img2pdf

OFFICE_EXTENSIONS = {
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".odt",
    ".odp",
    ".ods",
}

IMAGE_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


class ConversionError(RuntimeError):
    """输入文件无法转换为 PDF 时抛出。"""


def _normalize_output_path(input_path: Path, output_dir: Path) -> Path:
    return output_dir / f"{input_path.stem}.pdf"


def _copy_pdf(input_path: Path, output_path: Path) -> Path:
    shutil.copy2(input_path, output_path)
    return output_path


def _convert_image_to_pdf(input_path: Path, output_path: Path) -> Path:
    with input_path.open("rb") as input_file, output_path.open("wb") as output_file:
        output_file.write(img2pdf.convert(input_file))
    return output_path


def _convert_office_to_pdf(input_path: Path, output_dir: Path, output_path: Path) -> Path:
    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if soffice is None:
        raise ConversionError("LibreOffice is not installed or not found in PATH")

    try:
        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output_dir),
                str(input_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip()
        stdout = exc.stdout.strip()
        detail = stderr or stdout or "unknown LibreOffice error"
        raise ConversionError(f"LibreOffice conversion failed: {detail}") from exc

    if not output_path.exists():
        raise ConversionError(f"LibreOffice did not produce expected PDF: {output_path}")

    return output_path


def convert_to_pdf(input_path: Path, output_dir: Path) -> Path:
    """将输入文件转换为 PDF，返回生成的 PDF 路径。"""
    input_path = Path(input_path).expanduser().resolve()
    output_dir = Path(output_dir).expanduser().resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")
    if not input_path.is_file():
        raise ConversionError(f"input path is not a file: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    suffix = input_path.suffix.lower()
    output_path = _normalize_output_path(input_path, output_dir)

    if suffix == ".pdf":
        print(f"[Step 0] Input already PDF, copying to {output_path}")
        return _copy_pdf(input_path, output_path)

    if suffix in IMAGE_EXTENSIONS:
        print(f"[Step 0] Converting image to PDF: {input_path.name}")
        return _convert_image_to_pdf(input_path, output_path)

    if suffix in OFFICE_EXTENSIONS:
        print(f"[Step 0] Converting office document to PDF: {input_path.name}")
        return _convert_office_to_pdf(input_path, output_dir, output_path)

    raise ConversionError(f"unsupported input format: {input_path.suffix or '<no suffix>'}")
