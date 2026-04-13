"""Step 1：PDF 转换为 Markdown + 图片（调用 Doc2X API）。"""

import time
import zipfile
from pathlib import Path

import requests

from .config import DOC2X_API_KEY

BASE_URL = "https://v2.doc2x.noedgeai.com"
POLL_INTERVAL = 3  # seconds


def _headers() -> dict:
    return {"Authorization": f"Bearer {DOC2X_API_KEY}"}


def _preupload() -> tuple[str, str]:
    """获取预上传 URL，返回 (uid, put_url)。"""
    resp = requests.post(
        f"{BASE_URL}/api/v2/parse/preupload", headers=_headers(), timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "success":
        raise RuntimeError(f"preupload failed: {data}")
    return data["data"]["uid"], data["data"]["url"]


def _put_file(pdf_path: Path, put_url: str) -> None:
    with open(pdf_path, "rb") as f:
        resp = requests.put(put_url, data=f, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"PUT file failed ({resp.status_code}): {resp.text}")


def _wait_for_parse(uid: str) -> None:
    """轮询解析状态，直到 success 或 failed。"""
    url = f"{BASE_URL}/api/v2/parse/status"
    while True:
        resp = requests.get(url, headers=_headers(), params={"uid": uid}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "success":
            raise RuntimeError(f"parse status error: {data}")
        status = data["data"]["status"]
        if status == "success":
            return
        if status == "failed":
            raise RuntimeError(f"parse failed: {data['data'].get('detail')}")
        # processing
        progress = data["data"].get("progress", 0)
        print(f"  [Doc2X] parsing... {progress}%")
        time.sleep(POLL_INTERVAL)


def _request_export(uid: str) -> None:
    """触发 md 导出任务（dollar 模式，公式用 $ 包裹）。"""
    resp = requests.post(
        f"{BASE_URL}/api/v2/convert/parse",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "uid": uid,
            "to": "md",
            "formula_mode": "dollar",
            "filename": "output",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "success":
        raise RuntimeError(f"export request failed: {data}")


def _wait_for_export(uid: str) -> str:
    """轮询导出结果，返回 zip 下载 URL。"""
    url = f"{BASE_URL}/api/v2/convert/parse/result"
    while True:
        resp = requests.get(url, headers=_headers(), params={"uid": uid}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "success":
            raise RuntimeError(f"export result error: {data}")
        status = data["data"]["status"]
        if status == "success":
            # URL 中 \u0026 需替换为 &
            return data["data"]["url"].replace("\\u0026", "&")
        if status == "failed":
            raise RuntimeError("export task failed")
        print("  [Doc2X] exporting...")
        time.sleep(POLL_INTERVAL)


def _download_zip(download_url: str, dest: Path) -> Path:
    resp = requests.get(download_url, timeout=120)
    resp.raise_for_status()
    zip_path = dest / "doc2x_output.zip"
    zip_path.write_bytes(resp.content)
    return zip_path


def _extract_zip(zip_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """解压 zip，返回 (md_path, images_dir)。"""
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_dir)

    # 找到解压出的 .md 文件
    md_files = list(output_dir.rglob("*.md"))
    if not md_files:
        raise RuntimeError("No .md file found in Doc2X output zip")
    md_path = md_files[0]

    images_dir = md_path.parent / "images"
    if not images_dir.exists():
        images_dir.mkdir(parents=True, exist_ok=True)

    return md_path, images_dir


def pdf_to_markdown(pdf_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """调用 Doc2X 将 PDF 转为 Markdown，返回 (md_path, images_dir)。

    Args:
        pdf_path: 输入 PDF 文件路径。
        output_dir: 解压产物的输出目录。

    Returns:
        (md_path, images_dir) — Markdown 文件路径和图片文件夹路径。
    """
    if not DOC2X_API_KEY:
        raise RuntimeError("DOC2X_API_KEY is not set in .env")

    output_dir.mkdir(parents=True, exist_ok=True)

    print("[Step 1] Preuploading PDF...")
    uid, put_url = _preupload()

    print(f"[Step 1] Uploading {pdf_path.name} (uid={uid})...")
    _put_file(pdf_path, put_url)

    print("[Step 1] Waiting for parse to complete...")
    _wait_for_parse(uid)

    print("[Step 1] Requesting markdown export...")
    _request_export(uid)

    print("[Step 1] Waiting for export...")
    download_url = _wait_for_export(uid)

    print("[Step 1] Downloading zip...")
    zip_path = _download_zip(download_url, output_dir)

    print("[Step 1] Extracting...")
    md_path, images_dir = _extract_zip(zip_path, output_dir)

    zip_path.unlink(missing_ok=True)

    print(f"[Step 1] Done. md={md_path}, images={images_dir}")
    return md_path, images_dir
