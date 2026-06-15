#!/usr/bin/env python3
"""向后兼容入口：等价于 `aarrr-agent run ...`。"""

from __future__ import annotations

import sys

from aarrr_agent.cli import app

if __name__ == "__main__":
    sys.argv.insert(1, "run")
    app()
