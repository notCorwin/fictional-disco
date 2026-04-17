"""main.py 集成测试。

遵循 TDD：先定义 CLI 入口与主流水线的行为契约。
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _import_main_module():
    return importlib.import_module("exam_parser.main")


def test_run_pipeline_calls_all_stages_in_order_for_non_pdf_input(tmp_path: Path) -> None:
    module = _import_main_module()
    input_path = tmp_path / "sample.docx"
    input_path.write_text("fake office content", encoding="utf-8")
    output_dir = tmp_path / "output"

    converted_pdf = output_dir / "sample.pdf"
    markdown_path = output_dir / "doc2x" / "sample.md"
    images_dir = output_dir / "images"
    questions_path = output_dir / "questions.json"
    call_order: list[tuple[str, object, object]] = []

    def fake_convert_to_pdf(actual_input: str | Path, actual_output_dir: str | Path) -> Path:
        call_order.append(("convert_to_pdf", Path(actual_input), Path(actual_output_dir)))
        return converted_pdf

    def fake_pdf_to_markdown(actual_pdf: Path, actual_output_dir: Path) -> tuple[Path, Path]:
        call_order.append(("pdf_to_markdown", actual_pdf, actual_output_dir))
        return markdown_path, images_dir

    def fake_markdown_file_to_questions(
        actual_markdown_path: Path,
        *,
        output_path: Path | None = None,
        model: str | None = None,
    ) -> dict:
        call_order.append(("markdown_file_to_questions", actual_markdown_path, output_path))
        assert model is None
        return {"questions": [{"stem": "Q1"}]}

    def fake_questions_file_to_answers(
        actual_questions_path: Path,
        *,
        output_path: Path | None = None,
        model: str | None = None,
    ) -> dict:
        call_order.append(("questions_file_to_answers", actual_questions_path, output_path))
        assert model is None
        return {"questions": [{"stem": "Q1", "answer": "A", "solution": "..." }]}

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "convert_to_pdf", fake_convert_to_pdf)
    monkeypatch.setattr(module, "pdf_to_markdown", fake_pdf_to_markdown)
    monkeypatch.setattr(module, "markdown_file_to_questions", fake_markdown_file_to_questions)
    monkeypatch.setattr(module, "questions_file_to_answers", fake_questions_file_to_answers)

    try:
        result = module.run_pipeline(input_path=input_path, output_dir=output_dir)
    finally:
        monkeypatch.undo()

    assert result == questions_path
    assert call_order == [
        ("convert_to_pdf", input_path, output_dir),
        ("pdf_to_markdown", converted_pdf, output_dir),
        ("markdown_file_to_questions", markdown_path, questions_path),
        ("questions_file_to_answers", questions_path, questions_path),
    ]


def test_run_pipeline_skips_any2pdf_when_input_is_pdf(tmp_path: Path) -> None:
    module = _import_main_module()
    input_path = tmp_path / "sample.pdf"
    input_path.write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "output"

    markdown_path = output_dir / "doc2x" / "sample.md"
    images_dir = output_dir / "images"
    questions_path = output_dir / "questions.json"
    convert_calls: list[tuple[Path, Path]] = []
    pdf2md_calls: list[tuple[Path, Path]] = []

    def fake_convert_to_pdf(actual_input: str | Path, actual_output_dir: str | Path) -> Path:
        convert_calls.append((Path(actual_input), Path(actual_output_dir)))
        raise AssertionError("PDF input should bypass convert_to_pdf")

    def fake_pdf_to_markdown(actual_pdf: Path, actual_output_dir: Path) -> tuple[Path, Path]:
        pdf2md_calls.append((actual_pdf, actual_output_dir))
        return markdown_path, images_dir

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "convert_to_pdf", fake_convert_to_pdf)
    monkeypatch.setattr(module, "pdf_to_markdown", fake_pdf_to_markdown)
    monkeypatch.setattr(
        module,
        "markdown_file_to_questions",
        lambda markdown_path, *, output_path=None, model=None: {"questions": []},
    )
    monkeypatch.setattr(
        module,
        "questions_file_to_answers",
        lambda questions_path, *, output_path=None, model=None: {"questions": []},
    )

    try:
        result = module.run_pipeline(input_path=input_path, output_dir=output_dir)
    finally:
        monkeypatch.undo()

    assert result == questions_path
    assert convert_calls == []
    assert pdf2md_calls == [(input_path, output_dir)]


def test_main_invokes_pipeline_and_prints_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _import_main_module()
    input_path = tmp_path / "paper.pdf"
    input_path.write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "custom-output"
    final_output_path = output_dir / "questions.json"
    captured_calls: list[tuple[Path, Path]] = []

    def fake_run_pipeline(*, input_path: Path, output_dir: Path) -> Path:
        captured_calls.append((input_path, output_dir))
        return final_output_path

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "run_pipeline", fake_run_pipeline)

    try:
        exit_code = module.main([str(input_path), "--output-dir", str(output_dir)])
    finally:
        monkeypatch.undo()

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured_calls == [(input_path, output_dir)]
    assert str(final_output_path) in captured.out
    assert captured.err == ""


def test_main_returns_error_when_input_file_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _import_main_module()
    missing_input = tmp_path / "missing.pdf"

    exit_code = module.main([str(missing_input)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "input file not found" in captured.err
    assert str(missing_input) in captured.err


def test_main_returns_error_when_input_path_is_not_a_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _import_main_module()
    input_dir = tmp_path / "input-dir"
    input_dir.mkdir()

    exit_code = module.main([str(input_dir)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "input path is not a file" in captured.err
    assert str(input_dir) in captured.err


def test_main_returns_error_when_pipeline_raises(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _import_main_module()
    input_path = tmp_path / "paper.pdf"
    input_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(module, "run_pipeline", lambda **_: (_ for _ in ()).throw(RuntimeError("boom")))

    try:
        exit_code = module.main([str(input_path)])
    finally:
        monkeypatch.undo()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "boom" in captured.err
