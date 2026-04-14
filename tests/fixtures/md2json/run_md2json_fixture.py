"""批量运行 md2json fixtures 的手工测试脚本。

用途：
1. 扫描 tests/fixtures/md2json/input 下的 Markdown 样本。
2. 调用 OpenRouter Structured Outputs 将 Markdown 解析为题目 JSON。
3. 将每个样本的输出写入 tests/fixtures/md2json/output/<case_name>.json。
4. 对产物做 schema 校验，并在存在 expected 文件时进行差异比对。

说明：
- 这是一个独立脚本，不依赖 pytest。
- 当前仓库尚未提交 src/exam_parser/md2json.py 与 prompts/prompt_md2json.md，
  因此此脚本内置了最小可用的请求封装与提示词回退逻辑。
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
INPUT_DIR = THIS_DIR / "input"
EXPECTED_DIR = THIS_DIR / "expected"
OUTPUT_DIR = THIS_DIR / "output"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from exam_parser.config import OPENROUTER_API_KEY, OPENROUTER_MODEL_NAME
    from exam_parser.md2json import (
        Md2JsonError,
        markdown_file_to_questions,
        normalize_questions_json,
        validate_questions_json,
    )
except Exception as exc:  # pragma: no cover - 脚本路径下的防御逻辑
    OPENROUTER_API_KEY = ""
    OPENROUTER_MODEL_NAME = ""
    Md2JsonError = RuntimeError
    markdown_file_to_questions = None
    normalize_questions_json = None
    validate_questions_json = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


MAX_DIFF_LINES = 80
@dataclass
class CaseResult:
    name: str
    input_path: Path
    success: bool
    message: str
    output_path: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量运行 md2json fixture 测试")
    parser.add_argument(
        "--case",
        help="只运行文件名中包含该关键字的样本",
    )
    parser.add_argument(
        "--keep-output",
        action="store_true",
        help="保留已有输出文件；默认会覆盖对应 case 的输出",
    )
    parser.add_argument(
        "--no-compare",
        action="store_true",
        help="跳过与 expected/*.json 的比对，只做 schema 校验",
    )
    return parser.parse_args()


def ensure_callable() -> None:
    if IMPORT_ERROR is not None:
        raise RuntimeError(
            "无法导入 exam_parser.md2json。"
            f" 原因: {IMPORT_ERROR}"
        )
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set in .env")
    if not OPENROUTER_MODEL_NAME:
        raise RuntimeError("OPENROUTER_MODEL_NAME is not set in .env")


def discover_cases(keyword: str | None) -> list[Path]:
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"输入目录不存在: {INPUT_DIR}")

    cases = sorted(path for path in INPUT_DIR.iterdir() if path.is_file() and path.suffix == ".md")
    if keyword:
        cases = [path for path in cases if keyword in path.name]
    return cases


def normalize_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_diff(expected: Any, actual: Any) -> str:
    expected_text = normalize_json(expected).splitlines()
    actual_text = normalize_json(actual).splitlines()
    diff_lines = list(
        difflib.unified_diff(
            expected_text,
            actual_text,
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )
    if len(diff_lines) > MAX_DIFF_LINES:
        diff_lines = diff_lines[:MAX_DIFF_LINES] + ["... diff truncated ..."]
    return "\n".join(diff_lines)


def validate_output(case_name: str, actual_data: Any, compare_expected: bool) -> str:
    validate_questions_json(actual_data)

    question_count = len(actual_data.get("questions", [])) if isinstance(actual_data, dict) else 0
    message = f"schema_ok questions={question_count}"

    if not compare_expected:
        return message

    expected_path = EXPECTED_DIR / f"{case_name}.json"
    if not expected_path.exists():
        return f"{message} expected=missing"

    expected_data = json.loads(expected_path.read_text(encoding="utf-8"))
    expected_data = normalize_questions_json(expected_data)
    validate_questions_json(expected_data)

    if expected_data != actual_data:
        diff_text = build_diff(expected_data, actual_data)
        raise Md2JsonError(f"与 expected 不一致:\n{diff_text}")

    return f"{message} expected=match"


def run_case(
    input_path: Path,
    *,
    keep_output: bool,
    compare_expected: bool,
) -> CaseResult:
    case_name = input_path.stem
    output_path = OUTPUT_DIR / f"{case_name}.json"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not keep_output:
        output_path.unlink()

    try:
        actual_data = markdown_file_to_questions(input_path, output_path=output_path)
        message = validate_output(case_name, actual_data, compare_expected)
    except Exception as exc:
        return CaseResult(
            name=case_name,
            input_path=input_path,
            success=False,
            message=str(exc),
            output_path=output_path if output_path.exists() else None,
        )

    return CaseResult(
        name=case_name,
        input_path=input_path,
        success=True,
        message=message,
        output_path=output_path,
    )


def main() -> int:
    args = parse_args()

    ensure_callable()
    cases = discover_cases(args.case)
    if not cases:
        print("未找到可执行的 Markdown 样本。")
        return 1

    print(f"发现 {len(cases)} 个 Markdown 样本，输出目录: {OUTPUT_DIR}")
    print(f"OpenRouter model: {OPENROUTER_MODEL_NAME}")

    results: list[CaseResult] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] 运行: {case.name}")
        result = run_case(
            case,
            keep_output=args.keep_output,
            compare_expected=not args.no_compare,
        )
        results.append(result)
        status = "PASS" if result.success else "FAIL"
        print(f"  {status}: {result.message}")
        if result.output_path is not None:
            print(f"  output: {result.output_path}")

    failed = [result for result in results if not result.success]
    print()
    print(f"总计: {len(results)}，通过: {len(results) - len(failed)}，失败: {len(failed)}")

    if failed:
        print("失败样本:")
        for result in failed:
            print(f"- {result.input_path.name}: {result.message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
