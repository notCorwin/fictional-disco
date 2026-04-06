"""Step 5：最终校验（含答案规则）。"""

from pathlib import Path

from .step3_validate import validate_json


def final_validate(json_path: Path) -> Path:
    """调用校验模块，启用答案校验规则。"""
    return validate_json(json_path, check_answers=True)
