"""Step 2: 将 Markdown 解析为结构化题目 JSON。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests
from jsonschema import Draft202012Validator

from .config import OPENROUTER_API_KEY, OPENROUTER_MODEL_NAME, PROMPTS_DIR, SCHEMAS_DIR

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT = 180
QUESTION_SCHEMA_PATH = SCHEMAS_DIR / "question_schema.json"
PROMPT_PATH = PROMPTS_DIR / "prompt_md2json.md"

FALLBACK_SYSTEM_PROMPT = """你是试卷结构化解析助手。

任务：把用户提供的试卷 Markdown 解析成严格符合 JSON Schema 的题目 JSON。

规则：
1. 只输出符合 schema 的 JSON，不要输出解释。
2. 保留原始题目顺序。
3. 选择题 type=choices，填空题 type=filling，判断题 type=judging，其余解答/计算/证明等为 subjective。
4. 填空题题干中的空位统一改写为 [[slot]]，并正确填写 fill_slots_count。
5. 非选择题 options 必须为 null；有子题时 sub_questions 为数组，否则为 null。
6. stem_images 仅填写 Markdown 中显式引用的相对图片路径；没有图片时为 []。
7. 不要补题号、分值、章节标题等元信息，除非它们属于题干内容。
8. 不对 Markdown 做预清洗；直接容忍 Doc2X 噪音并抽取题目结构。
"""

FALLBACK_USER_TEMPLATE = """请将下面的 Markdown 试卷内容转换为 JSON：

```md
{markdown}
```
"""


class Md2JsonError(RuntimeError):
    """Markdown -> JSON 转换失败。"""


def _headers() -> dict[str, str]:
    if not OPENROUTER_API_KEY:
        raise Md2JsonError("OPENROUTER_API_KEY is not set in .env")
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }


def _load_question_schema_bundle() -> dict[str, Any]:
    if not QUESTION_SCHEMA_PATH.exists():
        raise Md2JsonError(f"question schema not found: {QUESTION_SCHEMA_PATH}")
    return json.loads(QUESTION_SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_prompt_parts() -> tuple[str, str]:
    if not PROMPT_PATH.exists():
        return FALLBACK_SYSTEM_PROMPT, FALLBACK_USER_TEMPLATE

    content = PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not content:
        return FALLBACK_SYSTEM_PROMPT, FALLBACK_USER_TEMPLATE

    parts = content.split("\n---\n", maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return FALLBACK_SYSTEM_PROMPT, content


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise Md2JsonError("OpenRouter response does not contain choices")

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

    raise Md2JsonError(f"unable to extract model response content: {message!r}")


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
            if (
                isinstance(entry, list)
                and len(entry) == 2
                and isinstance(entry[0], str)
            ):
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
        raise Md2JsonError(f"model output is not valid JSON: {exc}") from exc

    unwrapped = _unwrap_typed_node(data)
    if not isinstance(unwrapped, dict):
        raise Md2JsonError(f"parsed model output is not a JSON object: {type(unwrapped).__name__}")
    return unwrapped


def _count_fill_slots(stem: str) -> int:
    return stem.count("[[slot]]")


def _normalize_fill_slots(stem: str) -> str:
    return re.sub(r"_{3,}", "[[slot]]", stem)


def _normalize_option(option: Any) -> dict[str, Any]:
    if not isinstance(option, dict):
        return {"label": "", "text": str(option), "image": None}

    label = option.get("label")
    text = option.get("text")
    image = option.get("image")
    return {
        "label": "" if label is None else str(label),
        "text": "" if text is None else str(text),
        "image": None if image is None else str(image),
    }


def _infer_question_type(question: dict[str, Any]) -> str:
    question_type = question.get("type")
    if question_type in {"choices", "filling", "judging", "subjective"}:
        return question_type

    stem = str(question.get("stem") or "")
    if isinstance(question.get("options"), list):
        return "choices"
    if "[[slot]]" in stem:
        return "filling"
    return "subjective"


def _normalize_question(question: Any) -> dict[str, Any]:
    if not isinstance(question, dict):
        raise Md2JsonError(f"question node is not an object: {type(question).__name__}")

    question_type = _infer_question_type(question)
    stem = _normalize_fill_slots(str(question.get("stem") or ""))

    stem_images = question.get("stem_images")
    if not isinstance(stem_images, list):
        stem_images = []
    else:
        stem_images = [str(item) for item in stem_images]

    sub_questions = question.get("sub_questions")
    if isinstance(sub_questions, list):
        normalized_sub_questions = [_normalize_question(item) for item in sub_questions]
    else:
        normalized_sub_questions = None

    options = question.get("options")
    if question_type == "choices" and isinstance(options, list):
        normalized_options = [_normalize_option(item) for item in options]
    elif question_type == "choices":
        normalized_options = []
    else:
        normalized_options = None

    fill_slots_count = question.get("fill_slots_count")
    if isinstance(fill_slots_count, bool):
        fill_slots_count = int(fill_slots_count)
    elif not isinstance(fill_slots_count, int):
        fill_slots_count = None

    if fill_slots_count is None or fill_slots_count < 0:
        fill_slots_count = _count_fill_slots(stem) if question_type == "filling" else 0

    return {
        "type": question_type,
        "stem": stem,
        "stem_images": stem_images,
        "fill_slots_count": fill_slots_count,
        "options": normalized_options,
        "sub_questions": normalized_sub_questions,
    }


def normalize_questions_json(data: dict[str, Any]) -> dict[str, Any]:
    """对模型输出做确定性的结构修正，补齐 schema 必填字段。"""
    questions = data.get("questions")
    if not isinstance(questions, list):
        raise Md2JsonError("parsed model output does not contain a valid questions array")

    return {
        "questions": [_normalize_question(item) for item in questions],
    }


def validate_questions_json(data: dict[str, Any], schema_bundle: dict[str, Any] | None = None) -> None:
    schema_bundle = schema_bundle or _load_question_schema_bundle()
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
    raise Md2JsonError("question schema validation failed:\n" + "\n".join(lines))


def markdown_to_questions(markdown_text: str, *, model: str | None = None) -> dict[str, Any]:
    """调用 OpenRouter 将 Markdown 解析为题目 JSON。"""
    if not markdown_text.strip():
        raise Md2JsonError("markdown content is empty")

    schema_bundle = _load_question_schema_bundle()
    system_prompt, user_template = _load_prompt_parts()
    model_name = model or OPENROUTER_MODEL_NAME
    if not model_name:
        raise Md2JsonError("OPENROUTER_MODEL_NAME is not set in .env")

    response = requests.post(
        OPENROUTER_URL,
        headers=_headers(),
        json={
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_template.format(markdown=markdown_text)},
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
        raise Md2JsonError(f"OpenRouter error: {payload['error']}")

    data = normalize_questions_json(_parse_model_json(payload))
    validate_questions_json(data, schema_bundle=schema_bundle)
    return data


def markdown_file_to_questions(
    markdown_path: Path,
    *,
    output_path: Path | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """读取 Markdown 文件并返回结构化题目 JSON，可选写入 output_path。"""
    markdown_path = Path(markdown_path)
    if not markdown_path.exists():
        raise FileNotFoundError(f"markdown file not found: {markdown_path}")
    if markdown_path.suffix.lower() != ".md":
        raise ValueError(f"expected a .md file, got: {markdown_path.name}")

    markdown_text = markdown_path.read_text(encoding="utf-8")
    data = markdown_to_questions(markdown_text, model=model)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return data
