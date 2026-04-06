"""pytest 公共 fixtures。"""

from pathlib import Path

import pytest


@pytest.fixture()
def fixtures_dir() -> Path:
    """返回测试 fixtures 目录的路径。"""
    return Path(__file__).resolve().parent / "fixtures"
