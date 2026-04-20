"""JSON 文件读写与校验工具。"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable


JsonValidator = Callable[[dict[str, Any]], None]


class JsonFileError(RuntimeError):
    """JSON 文件读写失败。"""


def load_json_file(path: Path, *, error_cls: type[Exception] = JsonFileError) -> dict[str, Any]:
    """读取并解析 JSON 文件。"""
    path = Path(path)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise error_cls(f"invalid JSON in file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise error_cls(f"JSON root must be an object: {path}")

    return data


def dump_json_text(data: dict[str, Any]) -> str:
    """生成统一格式的 JSON 文本。"""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def write_validated_json_file(
    path: Path,
    data: dict[str, Any],
    *,
    validator: JsonValidator | None = None,
    error_cls: type[Exception] = JsonFileError,
) -> None:
    """原子写入 JSON 文件，并在落盘前后校验格式与结构。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = dump_json_text(data)

    try:
        parsed_payload = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise error_cls(f"failed to serialize JSON for {path}: {exc}") from exc

    if not isinstance(parsed_payload, dict):
        raise error_cls(f"JSON root must be an object: {path}")
    if validator is not None:
        validator(parsed_payload)

    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_path = Path(temp_file.name)

        reloaded_payload = load_json_file(temp_path, error_cls=error_cls)
        if validator is not None:
            validator(reloaded_payload)

        temp_path.replace(path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
