"""测试：Web UI 不含「公开演示」文案。"""

from pathlib import Path


def test_web_app_source_has_no_public_demo_label():
    root = Path(__file__).resolve().parent.parent
    for rel in ("aarrr_agent/web_app.py", "app.py"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "公开演示" not in text
