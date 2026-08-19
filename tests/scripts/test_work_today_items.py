import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "work_today_items.py"
SPEC = importlib.util.spec_from_file_location("work_today_items", SCRIPT_PATH)
work_today_items = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(work_today_items)


def test_today_items_ignores_other_sections_and_completed_items():
    text = """\
## Inbox
- [ ] stale inbox task
## Today
- [ ] current task
- [x] finished task
## Later
- [ ] later task
"""

    assert work_today_items.today_items(text) == ["current task"]


def test_main_is_silent_when_today_is_empty(tmp_path, monkeypatch, capsys):
    todo_path = tmp_path / "inbox.md"
    todo_path.write_text("## Inbox\n- [ ] backlog task\n\n## Today\n", encoding="utf-8")
    monkeypatch.setattr(work_today_items, "TODO_PATH", todo_path)

    assert work_today_items.main() == 0
    assert capsys.readouterr().out == ""


def test_main_prints_at_most_three_today_items(tmp_path, monkeypatch, capsys):
    todo_path = tmp_path / "inbox.md"
    todo_path.write_text(
        "## Today\n- [ ] one\n- [ ] two\n- [ ] three\n- [ ] four\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(work_today_items, "TODO_PATH", todo_path)

    assert work_today_items.main() == 0
    assert capsys.readouterr().out.splitlines() == [
        "Current unchecked Today items:",
        "- one",
        "- two",
        "- three",
    ]
