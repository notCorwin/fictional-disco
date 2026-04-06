"""Step 3 / Step 5：校验 JSON（可复用模块）。"""

from pathlib import Path


def validate_json(json_path: Path, *, check_answers: bool = False) -> Path:
    """校验 JSON 文件，返回修正后的 JSON 文件路径。

    Args:
        json_path: 待校验的 JSON 文件。
        check_answers: 是否启用答案校验规则（Step 5 时为 True）。
    """
    raise NotImplementedError("Step 3: validate_json 尚未实现")
