"""md2json 模块的离线 pytest 测试。"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest


def _import_md2json_module():
    return importlib.import_module("exam_parser.md2json")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture()
def md2json_fixture_input(fixtures_dir: Path) -> str:
    path = fixtures_dir / "md2json" / "input" / "概率论7套真题.md"
    return path.read_text(encoding="utf-8")


@pytest.fixture()
def md2json_expected_output(fixtures_dir: Path) -> dict[str, Any]:
    path = fixtures_dir / "md2json" / "expected" / "概率论7套真题.json"
    return _load_json(path)


def test_markdown_to_questions_posts_structured_output_request(
    monkeypatch: pytest.MonkeyPatch,
    md2json_fixture_input: str,
    md2json_expected_output: dict[str, Any],
) -> None:
    module = _import_md2json_module()
    captured_requests: list[dict[str, Any]] = []

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeResponse:
        captured_requests.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json_module.dumps(md2json_expected_output, ensure_ascii=False)
                        }
                    }
                ]
            }
        )

    json_module = json
    monkeypatch.setattr(module, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(module, "OPENROUTER_MODEL_NAME", "anthropic/test-model")
    monkeypatch.setattr(module.requests, "post", fake_post)

    result = module.markdown_to_questions(md2json_fixture_input)

    assert result == md2json_expected_output
    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request["url"] == module.OPENROUTER_URL
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert request["json"]["model"] == "anthropic/test-model"
    assert request["json"]["response_format"]["type"] == "json_schema"
    assert request["json"]["response_format"]["json_schema"]["name"] == "exam_questions"
    assert request["json"]["response_format"]["json_schema"]["strict"] is True
    assert request["timeout"] == module.REQUEST_TIMEOUT
    assert request["json"]["messages"][0]["role"] == "system"
    assert request["json"]["messages"][1]["role"] == "user"
    assert "请将以下试卷 Markdown 内容解析为结构化 JSON" in request["json"]["messages"][1]["content"]


def test_markdown_to_questions_normalizes_fill_slots_and_question_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _import_md2json_module()

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeResponse:
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json_module.dumps(
                                {
                                    "questions": [
                                        {
                                            "stem": "设函数值为 ___",
                                            "options": None,
                                            "sub_questions": None,
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }
        )

    json_module = json
    monkeypatch.setattr(module, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(module, "OPENROUTER_MODEL_NAME", "anthropic/test-model")
    monkeypatch.setattr(module.requests, "post", fake_post)

    result = module.markdown_to_questions("1. 设函数值为 ___")

    assert result == {
        "questions": [
            {
                "type": "filling",
                "stem": "设函数值为 [[slot]]",
                "stem_images": [],
                "fill_slots_count": 1,
                "options": None,
                "sub_questions": None,
            }
        ]
    }


def test_markdown_file_to_questions_writes_output_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _import_md2json_module()
    markdown_path = tmp_path / "sample.md"
    output_path = tmp_path / "output" / "questions.json"
    markdown_path.write_text("# sample", encoding="utf-8")
    expected = {"questions": []}

    monkeypatch.setattr(module, "markdown_to_questions", lambda markdown_text, model=None: expected)

    result = module.markdown_file_to_questions(markdown_path, output_path=output_path)

    assert result == expected
    assert _load_json(output_path) == expected
