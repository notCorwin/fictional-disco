"""Step 4：生成答案与解析（使用 LLM）。"""

from pathlib import Path


def generate_answers(json_path: Path, output_dir: Path) -> Path:
    """逐题调用 OpenRouter API 生成答案与解析，合并回 JSON，返回更新后的文件路径。"""
    raise NotImplementedError("Step 4: generate_answers 尚未实现")
