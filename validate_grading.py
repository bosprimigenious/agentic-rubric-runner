"""向后兼容入口：等价于 `aarrr-agent validate ...`。"""

from __future__ import annotations

import sys

from aarrr_agent.cli import app

if __name__ == "__main__":
    args = sys.argv[1:]
    sys.argv = ["aarrr-agent", "validate", *args]
    app()
