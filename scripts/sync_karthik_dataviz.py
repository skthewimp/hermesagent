#!/usr/bin/env python3
"""Install the external Karthik dataviz skills into a Hermes profile."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from hermes_constants import get_hermes_home


DEFAULT_SOURCE = REPO_ROOT.parent / "karthik-data-visualization-skill"


def discover_skills(source: Path) -> list[Path]:
    skills = [
        path
        for path in sorted(source.iterdir())
        if path.is_dir() and (path / "claude" / "SKILL.md").is_file()
    ]
    if not skills:
        raise ValueError(
            f"No compatible skills found under {source}; expected <skill>/claude/SKILL.md"
        )
    return skills


def validate_source(source: Path) -> None:
    validator = source / "sync-skills.py"
    if not validator.is_file():
        raise ValueError(f"Source validator not found: {validator}")
    subprocess.run(
        [sys.executable, str(validator), "--validate-only"],
        cwd=source,
        check=True,
    )


def replace_tree(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    staged = staging_root / destination.name
    backup = destination.parent / f".{destination.name}.previous"
    try:
        shutil.copytree(
            source,
            staged,
            ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"),
        )
        if backup.exists():
            shutil.rmtree(backup)
        if destination.exists():
            destination.replace(backup)
        staged.replace(destination)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if not destination.exists() and backup.exists():
            backup.replace(destination)
        raise
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root)


def sync_skills(
    source: Path,
    target: Path,
    *,
    validate: bool = True,
    validate_only: bool = False,
) -> list[str]:
    source = source.expanduser().resolve()
    target = target.expanduser().resolve()
    if validate:
        validate_source(source)
    skills = discover_skills(source)
    if not validate_only:
        for skill in skills:
            replace_tree(skill / "claude", target / skill.name)
    return [skill.name for skill in skills]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install Karthik's external dataviz skill set into Hermes."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(os.getenv("KARTHIK_DATAVIZ_REPO", DEFAULT_SOURCE)),
        help="checkout containing <skill>/claude/SKILL.md directories",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="skill destination; defaults to the active profile's data-science directory",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate and list source skills without installing them",
    )
    args = parser.parse_args()
    target = args.target or (get_hermes_home() / "skills" / "data-science")
    names = sync_skills(
        args.source,
        target,
        validate=True,
        validate_only=args.validate_only,
    )
    action = "validated" if args.validate_only else f"installed to {target}"
    print(f"{action}: " + ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
