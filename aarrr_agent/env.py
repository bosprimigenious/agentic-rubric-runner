"""加载项目根目录 .env（不覆盖已设置的环境变量）。"""

from __future__ import annotations

from pathlib import Path


def load_project_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    root = Path(__file__).resolve().parent.parent
    env_file = root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
