"""pdf2md 模块的离线 pytest 测试。"""

from __future__ import annotations

import importlib
import zipfile
from pathlib import Path

import pytest


def _import_pdf2md_module():
    return importlib.import_module("exam_parser.pdf2md")


def test_extract_zip_returns_markdown_path_and_images_dir(tmp_path: Path) -> None:
    module = _import_pdf2md_module()
    zip_path = tmp_path / "doc2x_output.zip"

    with zipfile.ZipFile(zip_path, "w") as zip_file:
        zip_file.writestr("nested/output.md", "# title\n![](images/q1.png)\n")
        zip_file.writestr("nested/images/q1.png", b"fake-image")

    md_path, images_dir = module._extract_zip(zip_path, tmp_path / "extract")

    assert md_path.name == "output.md"
    assert md_path.read_text(encoding="utf-8").startswith("# title")
    assert images_dir.name == "images"
    assert (images_dir / "q1.png").exists()


def test_pdf_to_markdown_orchestrates_doc2x_flow_and_removes_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _import_pdf2md_module()
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_dir = tmp_path / "output"
    captured_calls: list[tuple[str, object]] = []

    def fake_preupload(*, model: str | None = module.DEFAULT_MODEL) -> tuple[str, str]:
        captured_calls.append(("preupload", model))
        return "uid-123", "https://upload.example.com/file"

    def fake_put_file(actual_pdf: Path, put_url: str) -> None:
        captured_calls.append(("put_file", (actual_pdf, put_url)))

    def fake_wait_for_parse(uid: str, *, poll_interval: int = module.POLL_INTERVAL) -> None:
        captured_calls.append(("wait_for_parse", (uid, poll_interval)))

    def fake_request_export(uid: str) -> None:
        captured_calls.append(("request_export", uid))

    def fake_wait_for_export(uid: str, *, poll_interval: int = module.POLL_INTERVAL) -> str:
        captured_calls.append(("wait_for_export", (uid, poll_interval)))
        return "https://download.example.com/doc2x.zip"

    def fake_download_zip(download_url: str, actual_output_dir: Path) -> Path:
        captured_calls.append(("download_zip", (download_url, actual_output_dir)))
        zip_path = actual_output_dir / "doc2x_output.zip"
        with zipfile.ZipFile(zip_path, "w") as zip_file:
            zip_file.writestr("bundle/output.md", "converted markdown\n")
            zip_file.writestr("bundle/images/figure.png", b"image-bytes")
        return zip_path

    monkeypatch.setattr(module, "_preupload", fake_preupload)
    monkeypatch.setattr(module, "_put_file", fake_put_file)
    monkeypatch.setattr(module, "_wait_for_parse", fake_wait_for_parse)
    monkeypatch.setattr(module, "_request_export", fake_request_export)
    monkeypatch.setattr(module, "_wait_for_export", fake_wait_for_export)
    monkeypatch.setattr(module, "_download_zip", fake_download_zip)

    md_path, images_dir = module.pdf_to_markdown(pdf_path, output_dir, model="doc2x-test", poll_interval=0)

    assert md_path.exists()
    assert images_dir.exists()
    assert not (output_dir / "doc2x_output.zip").exists()
    assert captured_calls == [
        ("preupload", "doc2x-test"),
        ("put_file", (pdf_path, "https://upload.example.com/file")),
        ("wait_for_parse", ("uid-123", 0)),
        ("request_export", "uid-123"),
        ("wait_for_export", ("uid-123", 0)),
        ("download_zip", ("https://download.example.com/doc2x.zip", output_dir)),
    ]


def test_pdf_to_markdown_rejects_non_pdf_input(tmp_path: Path) -> None:
    module = _import_pdf2md_module()
    txt_path = tmp_path / "sample.txt"
    txt_path.write_text("not a pdf", encoding="utf-8")

    with pytest.raises(ValueError, match="expected a .pdf file"):
        module.pdf_to_markdown(txt_path, tmp_path / "output")
