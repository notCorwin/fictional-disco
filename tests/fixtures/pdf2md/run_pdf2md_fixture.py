"""批量运行 pdf2md fixtures 的手工测试脚本。

用途：
1. 扫描 tests/fixtures/pdf2md/input 下的 PDF 样本。
2. 调用 exam_parser.pdf2md.pdf_to_markdown 进行转换。
3. 将每个样本的输出写入 tests/fixtures/pdf2md/output/<case_name>/。
4. 对产物做基础校验，便于手工回归。

说明：
- 这是一个独立脚本，不依赖 pytest。
- 当前只处理 PDF 输入；图片样本属于阶段 0 范畴，不在这里直接执行。
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
INPUT_DIR = THIS_DIR / "input" / "PDF"
OUTPUT_DIR = THIS_DIR / "output"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from exam_parser.pdf2md import pdf_to_markdown
except Exception as exc:  # pragma: no cover - 脚本路径下的防御逻辑
    pdf_to_markdown = None
    IMPORT_ERROR = exc
else:
    IMPORT_ERROR = None


@dataclass
class CaseResult:
    name: str
    input_path: Path
    success: bool
    message: str
    md_path: Path | None = None
    images_dir: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量运行 pdf2md fixture 测试")
    parser.add_argument(
        "--case",
        help="只运行文件名中包含该关键字的样本",
    )
    parser.add_argument(
        "--keep-output",
        action="store_true",
        help="保留已有输出目录；默认每次运行前清空对应 case 输出",
    )
    return parser.parse_args()


def discover_cases(keyword: str | None) -> list[Path]:
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"输入目录不存在: {INPUT_DIR}")

    cases = sorted(path for path in INPUT_DIR.iterdir() if path.is_file())
    if keyword:
        cases = [path for path in cases if keyword in path.name]
    return cases


def ensure_callable() -> None:
    if pdf_to_markdown is None:
        raise RuntimeError(
            "无法导入 exam_parser.pdf2md.pdf_to_markdown。"
            f" 原因: {IMPORT_ERROR}"
        )


def validate_output(md_path: Path, images_dir: Path) -> str:
    if not md_path.exists():
        raise AssertionError(f"Markdown 文件不存在: {md_path}")
    if md_path.suffix.lower() != ".md":
        raise AssertionError(f"输出文件不是 Markdown: {md_path}")
    if not images_dir.exists() or not images_dir.is_dir():
        raise AssertionError(f"images 目录不存在: {images_dir}")

    content = md_path.read_text(encoding="utf-8")
    if not content.strip():
        raise AssertionError("Markdown 文件为空")

    image_refs = content.count("![](") + content.count("![")
    image_files = [path for path in images_dir.rglob("*") if path.is_file()]
    return f"markdown_ok image_refs={image_refs} image_files={len(image_files)}"


def run_case(input_path: Path, keep_output: bool) -> CaseResult:
    case_name = input_path.stem
    case_output_dir = OUTPUT_DIR / case_name

    if case_output_dir.exists() and not keep_output:
        shutil.rmtree(case_output_dir)
    case_output_dir.mkdir(parents=True, exist_ok=True)

    try:
        md_path, images_dir = pdf_to_markdown(input_path, case_output_dir)
        message = validate_output(md_path, images_dir)
    except Exception as exc:
        return CaseResult(
            name=case_name,
            input_path=input_path,
            success=False,
            message=str(exc),
        )

    return CaseResult(
        name=case_name,
        input_path=input_path,
        success=True,
        message=message,
        md_path=md_path,
        images_dir=images_dir,
    )


def main() -> int:
    args = parse_args()

    ensure_callable()
    cases = discover_cases(args.case)
    if not cases:
        print("未找到可执行的 PDF 样本。")
        return 1

    print(f"发现 {len(cases)} 个 PDF 样本，输出目录: {OUTPUT_DIR}")

    results: list[CaseResult] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] 运行: {case.name}")
        result = run_case(case, keep_output=args.keep_output)
        results.append(result)
        status = "PASS" if result.success else "FAIL"
        print(f"  {status}: {result.message}")
        if result.success:
            print(f"  md: {result.md_path}")
            print(f"  images: {result.images_dir}")

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
