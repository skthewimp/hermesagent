#!/usr/bin/env python3
"""Print unchecked work-todo items from the Today section only.

Hermes cron treats empty script output as a wake gate and skips the agent and
delivery. This keeps stale Inbox/Later tasks out of daily reminders.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


HERMES_HOME = Path(os.getenv("HERMES_HOME") or (Path.home() / ".hermes"))
TODO_PATH = Path(os.getenv("WORK_TODO_PATH") or (HERMES_HOME / "work-todo" / "inbox.md"))
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
OPEN_ITEM_RE = re.compile(r"^-\s*\[\s\]\s+(.+?)\s*$")


def today_items(text: str) -> list[str]:
    section = ""
    items: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        section_match = SECTION_RE.match(line)
        if section_match:
            section = section_match.group(1).strip().casefold()
            continue
        if section != "today":
            continue
        item_match = OPEN_ITEM_RE.match(line)
        if item_match:
            items.append(item_match.group(1).strip())
    return items


def main() -> int:
    if not TODO_PATH.exists():
        return 0
    items = today_items(TODO_PATH.read_text(encoding="utf-8"))
    if not items:
        return 0
    print("Current unchecked Today items:")
    for item in items[:3]:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
