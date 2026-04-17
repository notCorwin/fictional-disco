"""批量运行 any2pdf fixtures 的手工测试脚本。

用途：
1. 扫描 tests/fixtures/any2pdf/input 下的图片、Office、PDF 样本。
2. 调用 exam_parser.any2pdf.convert_to_pdf 执行阶段 0 转换。
3. 将每个样本输出写入 tests/fixtures/any2pdf/output/<case_name>/。
4. 对产物做基础校验，便于手工回归。

说明：
- 这是一个独立脚本，不依赖 pytest。
- 图片、Office、PDF 三类输入统一在这里覆盖。
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent.parent.parent
SRC_DIR = PROJECT_ROOT / "src"
INPUT_DIR = THIS_DIR / "input"
OUTPUT_DIR = THIS_DIR / "output"
SUPPORTED_BUCKETS = ("Image", "Office", "PDF")

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from exam_parser.any2pdf import convert_to_pdf
except Exception as exc:  # pragma: no cover - 脚本路径下的防御逻辑
    convert_to_pdf = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@dataclass
class CaseResult:
    name: str
    bucket: str
    input_path: Path
    success: bool
    message: str
    output_path: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量运行 any2pdf fixture 测试")
    parser.add_argument(
        "--case",
        help="只运行文件名中包含该关键字的样本",
    )
    parser.add_argument(
        "--bucket",
        choices=SUPPORTED_BUCKETS,
        help="只运行某一类输入样本",
    )
    parser.add_argument(
        "--keep-output",
        action="store_true",
        help="保留已有输出目录；默认每次运行前清空对应 case 输出",
    )
    return parser.parse_args()


def ensure_callable() -> None:
    if convert_to_pdf is None:
        raise RuntimeError(
            "无法导入 exam_parser.any2pdf.convert_to_pdf。"
            f" 原因: {IMPORT_ERROR}"
        )


def discover_cases(bucket: str | None, keyword: str | None) -> list[tuple[str, Path]]:
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"输入目录不存在: {INPUT_DIR}")

    buckets = [bucket] if bucket else list(SUPPORTED_BUCKETS)
    cases: list[tuple[str, Path]] = []

    for current_bucket in buckets:
        current_dir = INPUT_DIR / current_bucket
        if not current_dir.exists():
            continue

        for path in sorted(
            candidate
            for candidate in current_dir.iterdir()
            if candidate.is_file() and not candidate.name.startswith(".")
        ):
            if keyword and keyword not in path.name:
                continue
            cases.append((current_bucket, path))

    return cases


def validate_output(input_path: Path, output_path: Path) -> str:
    if not output_path.exists():
        raise AssertionError(f"PDF 文件不存在: {output_path}")
    if output_path.suffix.lower() != ".pdf":
        raise AssertionError(f"输出文件不是 PDF: {output_path}")
    if output_path.stat().st_size <= 0:
        raise AssertionError("输出 PDF 为空文件")

    if input_path.suffix.lower() == ".pdf" and input_path.read_bytes() != output_path.read_bytes():
        raise AssertionError("PDF 直传复制结果与输入文件不一致")

    return f"pdf_ok size={output_path.stat().st_size}"


def run_case(bucket: str, input_path: Path, keep_output: bool) -> CaseResult:
    case_name = input_path.stem
    case_output_dir = OUTPUT_DIR / case_name

    if case_output_dir.exists() and not keep_output:
        shutil.rmtree(case_output_dir)
    case_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        output_path = convert_to_pdf(input_path, case_output_dir)
        message = validate_output(input_path, output_path)
    except Exception as exc:
        return CaseResult(
            name=case_name,
            bucket=bucket,
            input_path=input_path,
            success=False,
            message=str(exc),
        )

    return CaseResult(
        name=case_name,
        bucket=bucket,
        input_path=input_path,
        success=True,
        message=message,
        output_path=output_path,
    )


def main() -> int:
    args = parse_args()

    ensure_callable()
    cases = discover_cases(args.bucket, args.case)
    if not cases:
        print("未找到可执行的 any2pdf 样本。")
        return 1

    print(f"发现 {len(cases)} 个 any2pdf 样本，输出目录: {OUTPUT_DIR}")

    results: list[CaseResult] = []
    for index, (bucket, case) in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] 运行: [{bucket}] {case.name}")
        result = run_case(bucket, case, keep_output=args.keep_output)
        results.append(result)
        status = "PASS" if result.success else "FAIL"
        print(f"  {status}: {result.message}")
        if result.success:
            print(f"  pdf: {result.output_path}")

    failed = [result for result in results if not result.success]
    print()
    print(f"总计: {len(results)}，通过: {len(results) - len(failed)}，失败: {len(failed)}")

    if failed:
        print("失败样本:")
        for result in failed:
            print(f"- [{result.bucket}] {result.input_path.name}: {result.message}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
