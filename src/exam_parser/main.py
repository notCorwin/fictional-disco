"""CLI / 流水线入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .answers import questions_file_to_answers
from .any2pdf import convert_to_pdf
from .md2json import markdown_file_to_questions
from .pdf2md import pdf_to_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="试卷转 JSON 转换工具")
    parser.add_argument("input_path", help="输入试卷文件路径")
    parser.add_argument(
        "--output-dir",
        default="output",
        help="输出目录，默认 output",
    )
    return parser


def run_pipeline(*, input_path: str | Path, output_dir: str | Path) -> Path:
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if input_path.suffix.lower() == ".pdf":
        pdf_path = input_path
    else:
        pdf_path = convert_to_pdf(input_path, output_dir)

    markdown_path, _images_dir = pdf_to_markdown(pdf_path, output_dir)

    questions_path = output_dir / "questions.json"
    markdown_file_to_questions(markdown_path, output_path=questions_path)
    questions_file_to_answers(questions_path, output_path=questions_path)

    return questions_path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input_path)
    output_dir = Path(args.output_dir)

    if not input_path.exists():
        print(f"input file not found: {input_path}", file=sys.stderr)
        return 1
    if not input_path.is_file():
        print(f"input path is not a file: {input_path}", file=sys.stderr)
        return 1

    try:
        final_output_path = run_pipeline(input_path=input_path, output_dir=output_dir)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(final_output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
