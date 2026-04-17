"""阶段 4：为结构化题目生成答案与解析。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import requests
from jsonschema import Draft202012Validator

from .config import OPENROUTER_API_KEY, OPENROUTER_MODEL_NAME, PROMPTS_DIR, SCHEMAS_DIR

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT = 180
ANSWER_SCHEMA_PATH = SCHEMAS_DIR / "answer_schema.json"
PROMPT_PATH = PROMPTS_DIR / "prompt_answers.md"

FALLBACK_SYSTEM_PROMPT = """你是一个专业的学科解题器。

你的任务是根据给定的题目，推算出正确答案并给出完整的分步解析。

规则：
1. 只输出符合 schema 的 JSON，不要输出解释。
2. 选择题的 answer 填选项标号，如 "C" 或多选 "AC"。
3. 填空题的 answer 输出字符串数组，按 [[slot]] 顺序对应。
4. 判断题的 answer 填 "正确" 或 "错误"。
5. 主观题的 answer 填最终结论或结果表达式。
6. 有子题的父题 answer 和 solution 必须为 null，答案写入 sub_answers。
7. sub_answers 与 sub_questions 必须按位置一一对应。
8. solution 应包含完整、连贯的推导过程，可包含 LaTeX 公式。
"""

FALLBACK_USER_TEMPLATE = """请为以下题目生成正确答案和完整解析。

题目：
```json
{question_json}
```
"""


class AnswersError(RuntimeError):
    """答案生成阶段失败。"""


def _question_summary(question: dict[str, Any], *, max_len: int = 60) -> str:
    stem = str(question.get("stem") or "").replace("\n", " ").strip()
    if not stem:
        return "<empty stem>"
    if len(stem) <= max_len:
        return stem
    return stem[: max_len - 3] + "..."


def _question_has_answer(question: Any) -> bool:
    if not isinstance(question, dict):
        return False
    return "answer" in question and "solution" in question


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_existing_output(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _headers() -> dict[str, str]:
    if not OPENROUTER_API_KEY:
        raise AnswersError("OPENROUTER_API_KEY is not set in .env")
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }


def _load_answer_schema_bundle() -> dict[str, Any]:
    if not ANSWER_SCHEMA_PATH.exists():
        raise AnswersError(f"answer schema not found: {ANSWER_SCHEMA_PATH}")
    return json.loads(ANSWER_SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_prompt_parts() -> tuple[str, str]:
    if not PROMPT_PATH.exists():
        return FALLBACK_SYSTEM_PROMPT, FALLBACK_USER_TEMPLATE

    content = PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not content:
        return FALLBACK_SYSTEM_PROMPT, FALLBACK_USER_TEMPLATE

    if "{question_json}" in content:
        return FALLBACK_SYSTEM_PROMPT, content

    return FALLBACK_SYSTEM_PROMPT, FALLBACK_USER_TEMPLATE


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise AnswersError("OpenRouter response does not contain choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                text_parts.append(item["text"])
        if text_parts:
            return "".join(text_parts)

    raise AnswersError(f"unable to extract model response content: {message!r}")


def _maybe_parse_json_string(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return value
    if stripped[0] not in "{[":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _unwrap_typed_node(node: Any) -> Any:
    if isinstance(node, str):
        parsed = _maybe_parse_json_string(node)
        if parsed is node:
            return node
        return _unwrap_typed_node(parsed)

    if isinstance(node, list):
        return [_unwrap_typed_node(item) for item in node]

    if not isinstance(node, dict):
        return node

    node_type = node.get("type")

    if node_type == "Object" and isinstance(node.get("entries"), list):
        result: dict[str, Any] = {}
        for entry in node["entries"]:
            if isinstance(entry, list) and len(entry) == 2 and isinstance(entry[0], str):
                result[entry[0]] = _unwrap_typed_node(entry[1])
        return result

    if node_type == "Array" and isinstance(node.get("items"), list):
        return [_unwrap_typed_node(item) for item in node["items"]]

    if node_type in {"String", "Number", "Boolean"} and "value" in node:
        return node["value"]

    if node_type == "Null":
        return None

    return {key: _unwrap_typed_node(value) for key, value in node.items()}


def _parse_model_json(payload: dict[str, Any]) -> dict[str, Any]:
    content = _extract_message_content(payload)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AnswersError(f"model output is not valid JSON: {exc}") from exc

    unwrapped = _unwrap_typed_node(data)
    if not isinstance(unwrapped, dict):
        raise AnswersError(f"parsed model output is not a JSON object: {type(unwrapped).__name__}")
    return unwrapped


def _normalize_answer_value(value: Any) -> str | list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return ["" if item is None else str(item) for item in value]
    return str(value)


def _normalize_answer_tree(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise AnswersError(f"answer node is not an object: {type(node).__name__}")

    sub_answers = node.get("sub_answers")
    if isinstance(sub_answers, list):
        normalized_sub_answers = [_normalize_answer_tree(item) for item in sub_answers]
    else:
        normalized_sub_answers = None

    return {
        "answer": _normalize_answer_value(node.get("answer")),
        "solution": None if node.get("solution") is None else str(node.get("solution")),
        "sub_answers": normalized_sub_answers,
    }


def normalize_answer_tree(data: dict[str, Any]) -> dict[str, Any]:
    """对模型输出做确定性的结构修正，补齐 schema 必填字段。"""
    return _normalize_answer_tree(data)


def validate_answers_json(data: dict[str, Any], schema_bundle: dict[str, Any] | None = None) -> None:
    schema_bundle = schema_bundle or _load_answer_schema_bundle()
    schema = schema_bundle["schema"]
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda item: list(item.path))
    if not errors:
        return

    lines = []
    for err in errors[:10]:
        path = "$"
        if err.path:
            path += "".join(f"[{part!r}]" if isinstance(part, str) else f"[{part}]" for part in err.path)
        lines.append(f"{path}: {err.message}")
    if len(errors) > 10:
        lines.append(f"... omitted {len(errors) - 10} additional errors")
    raise AnswersError("answer schema validation failed:\n" + "\n".join(lines))


def question_to_answers(question: dict[str, Any], *, model: str | None = None) -> dict[str, Any]:
    """调用 OpenRouter 为单道顶层题生成答案树。"""
    if not isinstance(question, dict):
        raise AnswersError(f"question must be an object, got: {type(question).__name__}")

    schema_bundle = _load_answer_schema_bundle()
    system_prompt, user_template = _load_prompt_parts()
    model_name = model or OPENROUTER_MODEL_NAME
    if not model_name:
        raise AnswersError("OPENROUTER_MODEL_NAME is not set in .env")

    question_json = json.dumps(question, ensure_ascii=False, indent=2)

    response = requests.post(
        OPENROUTER_URL,
        headers=_headers(),
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_template.format(question_json=question_json)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": schema_bundle,
            },
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    if payload.get("error"):
        raise AnswersError(f"OpenRouter error: {payload['error']}")

    data = normalize_answer_tree(_parse_model_json(payload))
    validate_answers_json(data, schema_bundle=schema_bundle)
    return data


def merge_answer_tree(question: dict[str, Any], answer_tree: dict[str, Any]) -> dict[str, Any]:
    """按位置将答案树合并回题目树。"""
    if not isinstance(question, dict):
        raise AnswersError(f"question node is not an object: {type(question).__name__}")
    if not isinstance(answer_tree, dict):
        raise AnswersError(f"answer node is not an object: {type(answer_tree).__name__}")

    merged = dict(question)
    merged["answer"] = answer_tree.get("answer")
    merged["solution"] = answer_tree.get("solution")

    question_sub_questions = question.get("sub_questions")
    answer_sub_answers = answer_tree.get("sub_answers")

    if question_sub_questions is None:
        if answer_sub_answers not in (None, []):
            raise AnswersError("sub_answers must be null when question.sub_questions is null")
        return merged

    if not isinstance(question_sub_questions, list):
        raise AnswersError("question.sub_questions must be a list or null")

    if not isinstance(answer_sub_answers, list):
        raise AnswersError("sub_answers must be a list when question.sub_questions is a list")

    if len(question_sub_questions) != len(answer_sub_answers):
        raise AnswersError(
            "sub_answers count does not match sub_questions count: "
            f"{len(answer_sub_answers)} != {len(question_sub_questions)}"
        )

    merged["sub_questions"] = [
        merge_answer_tree(sub_question, sub_answer)
        for sub_question, sub_answer in zip(question_sub_questions, answer_sub_answers, strict=True)
    ]
    return merged


def generate_answers_for_questions(data: dict[str, Any], *, model: str | None = None) -> dict[str, Any]:
    """对整份 questions JSON 中的每道顶层题逐题生成答案并合并。"""
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise AnswersError("questions must be an array")

    merged_questions = []
    for question in questions:
        answer_tree = question_to_answers(question, model=model)
        merged_questions.append(merge_answer_tree(question, answer_tree))

    merged_data = dict(data)
    merged_data["questions"] = merged_questions
    return merged_data


def questions_file_to_answers(
    questions_path: Path,
    *,
    output_path: Path | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """读取 questions JSON 文件并生成带答案的结果，可选写入 output_path。"""
    questions_path = Path(questions_path)
    if not questions_path.exists():
        raise FileNotFoundError(f"questions file not found: {questions_path}")
    if questions_path.suffix.lower() != ".json":
        raise ValueError(f"expected a .json file, got: {questions_path.name}")

    data = json.loads(questions_path.read_text(encoding="utf-8"))
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise AnswersError("questions must be an array")

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        existing_output = _load_existing_output(output_path)
    else:
        existing_output = None

    if existing_output is not None:
        existing_questions = existing_output.get("questions")
        if not isinstance(existing_questions, list):
            raise AnswersError("existing output questions must be an array")
        if len(existing_questions) != len(questions):
            raise AnswersError(
                "existing output question count does not match input: "
                f"{len(existing_questions)} != {len(questions)}"
            )
        merged_questions = existing_questions
        merged: dict[str, Any] = existing_output
    else:
        merged_questions = [dict(question) for question in questions]
        merged = dict(data)
        merged["questions"] = merged_questions

    for index, question in enumerate(questions):
        display_index = index + 1
        if _question_has_answer(merged_questions[index]):
            print(
                f"[answers] skip {display_index}/{len(questions)}: {_question_summary(question)}",
                file=sys.stderr,
                flush=True,
            )
            continue

        print(
            f"[answers] start {display_index}/{len(questions)}: {_question_summary(question)}",
            file=sys.stderr,
            flush=True,
        )

        try:
            answer_tree = question_to_answers(question, model=model)
            merged_questions[index] = merge_answer_tree(question, answer_tree)
        except Exception as exc:
            raise AnswersError(
                f"failed at question {display_index}/{len(questions)}: {_question_summary(question)}"
            ) from exc

        print(
            f"[answers] done {display_index}/{len(questions)}",
            file=sys.stderr,
            flush=True,
        )

        if output_path is not None:
            _write_json_file(output_path, merged)

    if output_path is not None:
        _write_json_file(output_path, merged)

    return merged
