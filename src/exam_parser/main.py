"""试卷转 JSON 转换工具入口。"""

import argparse
import sys
from pathlib import Path

from .convert import convert_to_pdf
from .pdf2md import pdf_to_markdown
from .md2json import markdown_to_json
from .validate import validate_json
from .answers import generate_answers
from .final import final_validate


def run_pipeline(input_path: Path, output_dir: Path) -> Path:
    """执行完整的阶段 0 到阶段 5 流水线。"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 0: 转换为 PDF
    pdf_path = convert_to_pdf(input_path, output_dir)

    # Step 1: PDF → Markdown + 图片
    md_path, images_dir = pdf_to_markdown(pdf_path, output_dir)

    # Step 2: Markdown → JSON（LLM）
    json_path = markdown_to_json(md_path, output_dir)

    # Step 3: 校验 JSON（通用规则）
    json_path = validate_json(json_path, check_answers=False)

    # Step 4: 生成答案与解析（LLM）
    json_path = generate_answers(json_path, output_dir)

    # Step 5: 最终校验（含答案规则）
    json_path = final_validate(json_path)

    print(f"✅ 完成！输出文件: {json_path}")
    return json_path


def main() -> None:
    parser = argparse.ArgumentParser(description="试卷转 JSON 转换工具")
    parser.add_argument("input", type=Path, help="输入文件路径（PDF/Word/图片等）")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output"),
        help="输出目录（默认: output/）",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"❌ 输入文件不存在: {args.input}", file=sys.stderr)
        sys.exit(1)

    run_pipeline(args.input, args.output)


if __name__ == "__main__":
    main()
