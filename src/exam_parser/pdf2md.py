"""Doc2X PDF -> Markdown 转换模块。"""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import requests

from .config import DOC2X_API_KEY

BASE_URL = "https://v2.doc2x.noedgeai.com"
DEFAULT_MODEL = "v3-2026"
POLL_INTERVAL = 3
REQUEST_TIMEOUT = 30
UPLOAD_TIMEOUT = 120
DOWNLOAD_TIMEOUT = 120


class Doc2XError(RuntimeError):
    """Doc2X 请求或转换错误。"""


def _headers() -> dict[str, str]:
    if not DOC2X_API_KEY:
        raise Doc2XError("DOC2X_API_KEY is not set in .env")
    return {"Authorization": f"Bearer {DOC2X_API_KEY}"}


def _raise_for_business_error(data: dict, action: str) -> None:
    if data.get("code") != "success":
        message = data.get("msg") or data.get("message") or str(data)
        raise Doc2XError(f"{action} failed: {message}")


def _preupload(model: str | None = DEFAULT_MODEL) -> tuple[str, str]:
    payload = {"model": model} if model else {}
    response = requests.post(
        f"{BASE_URL}/api/v2/parse/preupload",
        headers=_headers(),
        json=payload or None,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    _raise_for_business_error(data, "preupload")
    return data["data"]["uid"], data["data"]["url"]


def _put_file(pdf_path: Path, put_url: str) -> None:
    with pdf_path.open("rb") as file_obj:
        response = requests.put(put_url, data=file_obj, timeout=UPLOAD_TIMEOUT)
    if response.status_code != 200:
        raise Doc2XError(f"upload failed ({response.status_code}): {response.text}")


def _wait_for_parse(uid: str, poll_interval: int = POLL_INTERVAL) -> None:
    while True:
        response = requests.get(
            f"{BASE_URL}/api/v2/parse/status",
            headers=_headers(),
            params={"uid": uid},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        _raise_for_business_error(data, "parse status")

        status = data["data"]["status"]
        if status == "success":
            return
        if status == "failed":
            detail = data["data"].get("detail") or "unknown parse error"
            raise Doc2XError(f"parse failed: {detail}")

        progress = data["data"].get("progress", 0)
        print(f"  [Doc2X] parsing... {progress}%")
        time.sleep(poll_interval)


def _request_export(uid: str) -> None:
    response = requests.post(
        f"{BASE_URL}/api/v2/convert/parse",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "uid": uid,
            "to": "md",
            "formula_mode": "dollar",
            "filename": "output",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    _raise_for_business_error(data, "request export")


def _wait_for_export(uid: str, poll_interval: int = POLL_INTERVAL) -> str:
    while True:
        response = requests.get(
            f"{BASE_URL}/api/v2/convert/parse/result",
            headers=_headers(),
            params={"uid": uid},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        _raise_for_business_error(data, "export result")

        status = data["data"]["status"]
        if status == "success":
            return data["data"]["url"].replace("\\u0026", "&")
        if status == "failed":
            raise Doc2XError("export failed")

        print("  [Doc2X] exporting...")
        time.sleep(poll_interval)


def _download_zip(download_url: str, output_dir: Path) -> Path:
    response = requests.get(download_url, timeout=DOWNLOAD_TIMEOUT)
    response.raise_for_status()
    zip_path = output_dir / "doc2x_output.zip"
    zip_path.write_bytes(response.content)
    return zip_path


def _extract_zip(zip_path: Path, output_dir: Path) -> tuple[Path, Path]:
    with zipfile.ZipFile(zip_path, "r") as zip_file:
        zip_file.extractall(output_dir)

    md_files = sorted(output_dir.rglob("*.md"))
    if not md_files:
        raise Doc2XError("no markdown file found in Doc2X export")

    md_path = md_files[0]
    images_dir = md_path.parent / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    return md_path, images_dir


def pdf_to_markdown(
    pdf_path: Path,
    output_dir: Path,
    *,
    model: str | None = DEFAULT_MODEL,
    poll_interval: int = POLL_INTERVAL,
) -> tuple[Path, Path]:
    """调用 Doc2X 将 PDF 转为 Markdown，返回 (md_path, images_dir)。"""
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"expected a .pdf file, got: {pdf_path.name}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print("[Step 1] Preuploading PDF...")
    uid, put_url = _preupload(model=model)

    print(f"[Step 1] Uploading {pdf_path.name} (uid={uid})...")
    _put_file(pdf_path, put_url)

    print("[Step 1] Waiting for parse to complete...")
    _wait_for_parse(uid, poll_interval=poll_interval)

    print("[Step 1] Requesting markdown export...")
    _request_export(uid)

    print("[Step 1] Waiting for export...")
    download_url = _wait_for_export(uid, poll_interval=poll_interval)

    print("[Step 1] Downloading zip...")
    zip_path = _download_zip(download_url, output_dir)

    print("[Step 1] Extracting...")
    md_path, images_dir = _extract_zip(zip_path, output_dir)
    zip_path.unlink(missing_ok=True)

    print(f"[Step 1] Done. md={md_path}, images={images_dir}")
    return md_path, images_dir
