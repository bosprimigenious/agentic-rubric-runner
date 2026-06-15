#!/usr/bin/env python3
"""兼容入口：转发至 `agentic-rubric run`。"""

from __future__ import annotations

import sys

from aarrr_agent.cli import main

if __name__ == "__main__":
    sys.argv.insert(1, "run")
    main()
