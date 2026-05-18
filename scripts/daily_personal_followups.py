#!/usr/bin/env python3
"""Emit the Hermes daily personal follow-up digest for cron delivery.

The live cron job uses a copy of this file under ~/.hermes/scripts/, because
Hermes cron intentionally only executes scripts from that directory.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


HERMES_APP = Path(os.getenv("HERMES_APP_DIR", "/home/karthik/apps/hermes"))
if str(HERMES_APP) not in sys.path:
    sys.path.insert(0, str(HERMES_APP))


def _load_env() -> None:
    env_path = Path(os.getenv("HERMES_ENV_FILE", "/home/karthik/.hermes/.env"))
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    _load_env()
    from tools.personal_followups_tool import personal_followups_tool

    dry_run = os.getenv("PERSONAL_FOLLOWUPS_DRY_RUN", "").lower() in {"1", "true", "yes"}
    result = json.loads(
        personal_followups_tool(
            {
                "action": "digest",
                "lookback_days": int(os.getenv("PERSONAL_FOLLOWUPS_LOOKBACK_DAYS", "7")),
                "limit_per_source": int(os.getenv("PERSONAL_FOLLOWUPS_LIMIT_PER_SOURCE", "150")),
                "dry_run": dry_run,
            }
        )
    )
    if not result.get("success"):
        print(result.get("error") or "Failed to build daily follow-up digest.")
        return 1
    print(result.get("summary") or "Daily follow-ups\n\nNo digest generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
