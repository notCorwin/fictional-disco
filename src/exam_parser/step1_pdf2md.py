"""Step 1：PDF 转换为 Markdown + 图片（调用 Doc2X API）。"""

from pathlib import Path


def pdf_to_markdown(pdf_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """调用 Doc2X 将 PDF 转为 Markdown，返回 (md_path, images_dir)。"""
    raise NotImplementedError("Step 1: pdf_to_markdown 尚未实现")
