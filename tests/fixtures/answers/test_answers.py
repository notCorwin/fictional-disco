"""阶段 4：answers 模块的 TDD 测试。"""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


def _import_answers_module():
    return importlib.import_module("exam_parser.answers")


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
def answers_fixtures_dir(fixtures_dir: Path) -> Path:
    return fixtures_dir / "answers"


@pytest.fixture()
def questions_input(answers_fixtures_dir: Path) -> dict[str, Any]:
    return _load_json(answers_fixtures_dir / "input" / "概率论7套真题.json")


@pytest.fixture()
def top_level_question(questions_input: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(questions_input["questions"][0])


@pytest.fixture()
def questions_bundle(questions_input: dict[str, Any]) -> dict[str, Any]:
    return {"questions": deepcopy(questions_input["questions"][:2])}


@pytest.fixture()
def expected_merged_top_level_question() -> dict[str, Any]:
    return {
        "type": "filling",
        "stem": "设 $P(A) = 0.5,\\ P(B) = 0.7,\\ P(AB) = 0.3$，则 $P(A \\cup B) =$ [[slot]]",
        "stem_images": [],
        "fill_slots_count": 1,
        "options": None,
        "sub_questions": None,
        "answer": ["0.9"],
        "solution": "由容斥公式 $P(A \\cup B)=P(A)+P(B)-P(AB)=0.5+0.7-0.3=0.9$。",
    }


@pytest.fixture()
def expected_questions_with_answers() -> dict[str, Any]:
    return {
        "questions": [
            {
                "type": "filling",
                "stem": "设 $P(A) = 0.5,\\ P(B) = 0.7,\\ P(AB) = 0.3$，则 $P(A \\cup B) =$ [[slot]]",
                "stem_images": [],
                "fill_slots_count": 1,
                "options": None,
                "sub_questions": None,
                "answer": ["0.9"],
                "solution": "由容斥公式 $P(A \\cup B)=P(A)+P(B)-P(AB)=0.5+0.7-0.3=0.9$。",
            },
            {
                "type": "filling",
                "stem": "区间 $(-2, 7)$ 上的均匀分布的密度函数为 [[slot]]",
                "stem_images": [],
                "fill_slots_count": 1,
                "options": None,
                "sub_questions": None,
                "answer": ["1/9"],
                "solution": "均匀分布在区间 $(-2,7)$ 上的密度为区间长度的倒数，即 $1/(7-(-2))=1/9$。",
            },
        ]
    }


@pytest.fixture()
def answer_tree_for_top_level_question() -> dict[str, Any]:
    return {
        "answer": ["0.9"],
        "solution": "由容斥公式 $P(A \\cup B)=P(A)+P(B)-P(AB)=0.5+0.7-0.3=0.9$。",
        "sub_answers": None,
    }


@pytest.fixture()
def answer_tree_for_second_question() -> dict[str, Any]:
    return {
        "answer": ["1/9"],
        "solution": "均匀分布在区间 $(-2,7)$ 上的密度为区间长度的倒数，即 $1/(7-(-2))=1/9$。",
        "sub_answers": None,
    }


def test_question_to_answers_posts_structured_output_request(
    monkeypatch: pytest.MonkeyPatch,
    top_level_question: dict[str, Any],
    answer_tree_for_top_level_question: dict[str, Any],
) -> None:
    module = _import_answers_module()
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
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json_module.dumps(answer_tree_for_top_level_question, ensure_ascii=False)
                    }
                }
            ]
        }
        return _FakeResponse(payload)

    json_module = json
    monkeypatch.setattr(module, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(module, "OPENROUTER_MODEL_NAME", "anthropic/test-model")
    monkeypatch.setattr(module.requests, "post", fake_post)

    result = module.question_to_answers(top_level_question)

    assert result == answer_tree_for_top_level_question
    assert len(captured_requests) == 1

    request = captured_requests[0]
    assert request["url"] == module.OPENROUTER_URL
    assert request["headers"]["Authorization"] == "Bearer test-key"
    assert request["json"]["model"] == "anthropic/test-model"
    assert request["json"]["response_format"]["type"] == "json_schema"
    assert request["json"]["response_format"]["json_schema"]["name"] == "exam_answers"
    assert request["json"]["response_format"]["json_schema"]["strict"] is True
    assert request["timeout"] == module.REQUEST_TIMEOUT

    messages = request["json"]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "请为以下题目生成正确答案和完整解析" in messages[1]["content"]
    assert '"fill_slots_count"' in messages[1]["content"]


def test_merge_answer_tree_merges_recursively_by_position(
    top_level_question: dict[str, Any],
    answer_tree_for_top_level_question: dict[str, Any],
    expected_merged_top_level_question: dict[str, Any],
) -> None:
    module = _import_answers_module()

    merged = module.merge_answer_tree(
        deepcopy(top_level_question),
        deepcopy(answer_tree_for_top_level_question),
    )

    assert merged == expected_merged_top_level_question


def test_merge_answer_tree_rejects_sub_answer_count_mismatch(
) -> None:
    module = _import_answers_module()

    question = {
        "type": "subjective",
        "stem": "阅读材料并回答问题。",
        "stem_images": [],
        "fill_slots_count": 0,
        "options": None,
        "sub_questions": [
            {
                "type": "filling",
                "stem": "第 1 空 [[slot]]",
                "stem_images": [],
                "fill_slots_count": 1,
                "options": None,
                "sub_questions": None,
            },
            {
                "type": "filling",
                "stem": "第 2 空 [[slot]]",
                "stem_images": [],
                "fill_slots_count": 1,
                "options": None,
                "sub_questions": None,
            },
        ],
    }
    bad_answer_tree = {
        "answer": None,
        "solution": None,
        "sub_answers": [
            {
                "answer": ["1"],
                "solution": "示例解析。",
                "sub_answers": None,
            }
        ],
    }

    with pytest.raises(module.AnswersError, match="sub_answers"):
        module.merge_answer_tree(question, bad_answer_tree)


def test_generate_answers_for_questions_calls_llm_once_per_top_level_question(
    monkeypatch: pytest.MonkeyPatch,
    questions_bundle: dict[str, Any],
    expected_questions_with_answers: dict[str, Any],
    answer_tree_for_top_level_question: dict[str, Any],
    answer_tree_for_second_question: dict[str, Any],
) -> None:
    module = _import_answers_module()
    captured_bodies: list[dict[str, Any]] = []
    queued_answer_trees = [
        answer_tree_for_top_level_question,
        answer_tree_for_second_question,
    ]

    def fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: int) -> _FakeResponse:
        assert url == module.OPENROUTER_URL
        assert headers["Authorization"] == "Bearer test-key"
        assert timeout == module.REQUEST_TIMEOUT
        captured_bodies.append(json)

        next_answer_tree = queued_answer_trees.pop(0)
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": json_module.dumps(next_answer_tree, ensure_ascii=False)
                        }
                    }
                ]
            }
        )

    json_module = json
    monkeypatch.setattr(module, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(module, "OPENROUTER_MODEL_NAME", "anthropic/test-model")
    monkeypatch.setattr(module.requests, "post", fake_post)

    merged = module.generate_answers_for_questions(deepcopy(questions_bundle))

    assert merged == expected_questions_with_answers
    assert len(captured_bodies) == 2
    assert "请为以下题目生成正确答案和完整解析" in captured_bodies[0]["messages"][1]["content"]
    assert "区间 $(-2, 7)$ 上的均匀分布" in captured_bodies[1]["messages"][1]["content"]


def test_generate_answers_for_questions_rejects_non_array_questions() -> None:
    module = _import_answers_module()

    with pytest.raises(module.AnswersError, match="questions"):
        module.generate_answers_for_questions({"questions": None})


def test_questions_file_to_answers_keeps_existing_file_when_incremental_write_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    questions_bundle: dict[str, Any],
    answer_tree_for_top_level_question: dict[str, Any],
) -> None:
    module = _import_answers_module()
    questions_path = tmp_path / "questions.json"
    output_path = tmp_path / "answers.json"

    questions_path.write_text(json.dumps(questions_bundle, ensure_ascii=False), encoding="utf-8")
    output_path.write_text(json.dumps(questions_bundle, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(module, "question_to_answers", lambda question, model=None: answer_tree_for_top_level_question)
    monkeypatch.setattr(
        module,
        "merge_answer_tree",
        lambda question, answer_tree: {
            **question,
            "answer": answer_tree.get("answer"),
        },
    )

    with pytest.raises(module.AnswersError, match="missing answer or solution"):
        module.questions_file_to_answers(questions_path, output_path=output_path)

    assert _load_json(output_path) == questions_bundle
