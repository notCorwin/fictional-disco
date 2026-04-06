"""项目配置：从 .env 文件读取环境变量。"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（src/exam_parser/config.py → 上溯三级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

load_dotenv(PROJECT_ROOT / ".env")

# OpenRouter
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL_NAME: str = os.getenv("OPENROUTER_MODEL_NAME", "")

# Doc2X
DOC2X_API_KEY: str = os.getenv("DOC2X_API_KEY", "")

# 资源路径
SCHEMAS_DIR: Path = PROJECT_ROOT / "schemas"
PROMPTS_DIR: Path = PROJECT_ROOT / "prompts"
