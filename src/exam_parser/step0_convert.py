"""Step 0：将上传内容统一转换为 PDF。"""

from pathlib import Path


def convert_to_pdf(input_path: Path, output_dir: Path) -> Path:
    """将输入文件转换为 PDF，已是 PDF 则直接返回。"""
    raise NotImplementedError("Step 0: convert_to_pdf 尚未实现")
