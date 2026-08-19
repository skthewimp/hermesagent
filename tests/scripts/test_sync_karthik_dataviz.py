from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "sync_karthik_dataviz.py"
SPEC = importlib.util.spec_from_file_location("sync_karthik_dataviz", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def make_skill(root: Path, name: str, marker: str) -> None:
    skill = root / name / "claude"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test\n---\n{marker}\n",
        encoding="utf-8",
    )
    scripts = skill / "scripts"
    scripts.mkdir()
    (scripts / "helper.py").write_text(marker, encoding="utf-8")


def test_sync_installs_only_the_external_claude_surface(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_skill(source, "chart-one", "first")
    make_skill(source, "chart-two", "second")
    target = tmp_path / "profile" / "skills" / "data-science"

    names = MODULE.sync_skills(source, target, validate=False)

    assert names == ["chart-one", "chart-two"]
    assert (target / "chart-one" / "SKILL.md").read_text().endswith("first\n")
    assert (target / "chart-two" / "scripts" / "helper.py").read_text() == "second"
    assert not (target / "chart-one" / "claude").exists()


def test_sync_replaces_a_managed_skill_without_touching_neighbours(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    make_skill(source, "chart-one", "new")
    target = tmp_path / "target"
    old = target / "chart-one"
    old.mkdir(parents=True)
    (old / "obsolete.txt").write_text("old", encoding="utf-8")
    neighbour = target / "unrelated"
    neighbour.mkdir()
    (neighbour / "keep.txt").write_text("keep", encoding="utf-8")

    MODULE.sync_skills(source, target, validate=False)

    assert not (old / "obsolete.txt").exists()
    assert (old / "scripts" / "helper.py").read_text() == "new"
    assert (neighbour / "keep.txt").read_text() == "keep"
