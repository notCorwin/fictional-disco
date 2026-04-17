"""any2pdf 模块的离线 pytest 测试。"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _import_any2pdf_module():
    return importlib.import_module("exam_parser.any2pdf")


def test_convert_to_pdf_copies_existing_pdf_exactly(tmp_path: Path) -> None:
    module = _import_any2pdf_module()
    input_path = tmp_path / "sample.pdf"
    output_dir = tmp_path / "output"
    input_bytes = b"%PDF-1.4\nfake-pdf\n"
    input_path.write_bytes(input_bytes)

    output_path = module.convert_to_pdf(input_path, output_dir)

    assert output_path == output_dir / "sample.pdf"
    assert output_path.read_bytes() == input_bytes


def test_convert_to_pdf_routes_image_input_to_image_converter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _import_any2pdf_module()
    input_path = tmp_path / "sample.jpg"
    input_path.write_bytes(b"fake-image")
    output_dir = tmp_path / "output"
    captured_calls: list[tuple[Path, Path]] = []

    def fake_convert_image(actual_input: Path, actual_output: Path) -> Path:
        captured_calls.append((actual_input, actual_output))
        actual_output.write_bytes(b"%PDF-1.4\nimage-pdf\n")
        return actual_output

    monkeypatch.setattr(module, "_convert_image", fake_convert_image)

    output_path = module.convert_to_pdf(input_path, output_dir)

    assert output_path == output_dir / "sample.pdf"
    assert captured_calls == [(input_path, output_path)]
    assert output_path.read_bytes().startswith(b"%PDF-1.4")


def test_convert_to_pdf_reports_missing_libreoffice_for_office_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _import_any2pdf_module()
    input_path = tmp_path / "sample.docx"
    input_path.write_bytes(b"fake-office")

    monkeypatch.setattr(module.shutil, "which", lambda _name: None)

    with pytest.raises(module.Any2PdfError, match="LibreOffice/soffice"):
        module.convert_to_pdf(input_path, tmp_path / "output")


def test_convert_to_pdf_rejects_unsupported_file_type(tmp_path: Path) -> None:
    module = _import_any2pdf_module()
    input_path = tmp_path / "sample.txt"
    input_path.write_text("plain text", encoding="utf-8")

    with pytest.raises(module.Any2PdfError, match="unsupported file type"):
        module.convert_to_pdf(input_path, tmp_path / "output")
