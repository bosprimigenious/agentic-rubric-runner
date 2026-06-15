"""测试：Web 入口与 pip 安装兼容性。"""

from pathlib import Path

from aarrr_agent.cli import resolve_web_app_path


def test_resolve_web_app_path_packaged():
    path = resolve_web_app_path()
    assert path.exists()
    assert path.name in {"web_app.py", "app.py"}
    assert path.suffix == ".py"


def test_web_app_importable():
    import aarrr_agent.web_app  # noqa: F401

    assert Path(aarrr_agent.web_app.__file__).exists()
