"""阶段 0：将任意支持文件转换为 PDF。"""

from __future__ import annotations

import shutil
import subprocess
from io import BytesIO
from pathlib import Path

IMAGE_SUFFIXES = {
    ".bmp",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
OFFICE_SUFFIXES = {
    ".doc",
    ".docx",
    ".odp",
    ".ods",
    ".odt",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
}


class Any2PdfError(RuntimeError):
    """任意文件转 PDF 失败。"""


def _copy_pdf(input_path: Path, output_path: Path) -> Path:
    shutil.copyfile(input_path, output_path)
    return output_path


def _convert_image_with_img2pdf(input_path: Path, output_path: Path) -> Path:
    import img2pdf

    pdf_bytes = img2pdf.convert(str(input_path))
    output_path.write_bytes(pdf_bytes)
    return output_path


def _convert_image_with_pillow(input_path: Path, output_path: Path) -> Path:
    from PIL import Image

    with Image.open(input_path) as image:
        if image.mode in {"RGBA", "LA"}:
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            converted = background
        else:
            converted = image.convert("RGB")

        buffer = BytesIO()
        converted.save(buffer, format="PDF", resolution=100.0)

    output_path.write_bytes(buffer.getvalue())
    return output_path


def _convert_image(input_path: Path, output_path: Path) -> Path:
    try:
        return _convert_image_with_img2pdf(input_path, output_path)
    except ModuleNotFoundError:
        return _convert_image_with_pillow(input_path, output_path)


def _convert_office(input_path: Path, output_dir: Path, output_path: Path) -> Path:
    soffice_path = shutil.which("libreoffice") or shutil.which("soffice")
    if not soffice_path:
        raise Any2PdfError(
            "LibreOffice/soffice 未安装，无法转换 Office 文档。"
        )

    command = [
        soffice_path,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(output_dir),
        str(input_path),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise Any2PdfError(f"LibreOffice 转换失败: {stderr}")

    generated_path = output_dir / f"{input_path.stem}.pdf"
    if not generated_path.exists():
        raise Any2PdfError(f"LibreOffice 未生成预期 PDF: {generated_path}")

    if generated_path != output_path:
        shutil.move(str(generated_path), str(output_path))
    return output_path


def convert_to_pdf(input_path: str | Path, output_dir: str | Path) -> Path:
    """将 PDF、图片或 Office 文档转换为 PDF，返回输出路径。"""
    input_path = Path(input_path)
    output_dir = Path(output_dir)

    if not input_path.exists():
        raise FileNotFoundError(f"input file not found: {input_path}")
    if not input_path.is_file():
        raise ValueError(f"input path is not a file: {input_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}.pdf"
    suffix = input_path.suffix.lower()

    if suffix == ".pdf":
        return _copy_pdf(input_path, output_path)
    if suffix in IMAGE_SUFFIXES:
        return _convert_image(input_path, output_path)
    if suffix in OFFICE_SUFFIXES:
        return _convert_office(input_path, output_dir, output_path)

    raise Any2PdfError(f"unsupported file type: {input_path.suffix or '<no suffix>'}")
