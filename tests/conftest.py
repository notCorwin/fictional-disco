"""pytest 公共 fixtures。"""

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture()
def fixtures_dir() -> Path:
    """返回测试 fixtures 目录的路径。"""
    return Path(__file__).resolve().parent / "fixtures"
