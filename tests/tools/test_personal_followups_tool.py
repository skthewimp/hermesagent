import json
from datetime import datetime, timezone

from tools import personal_followups_tool as pft


def test_digest_creates_action_items_and_dedupes(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONAL_FOLLOWUPS_DB", str(tmp_path / "followups.sqlite3"))
    fixed_now = datetime(2026, 5, 18, 3, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(pft, "_now_utc", lambda: fixed_now)
    monkeypatch.setattr(
        pft,
        "_fetch_whatsapp_messages",
        lambda since, until, limit: [
            {
                "source": "whatsapp",
                "source_id": "wa-1",
                "thread_key": "asha",
                "contact": "Asha",
                "contact_ref": "asha",
                "direction": "incoming",
                "message_at": "2026-05-18T03:00:00Z",
                "subject": "",
                "body": "Can you send me the notes from yesterday?",
                "metadata": {},
            }
        ],
    )
    monkeypatch.setattr(
        pft,
        "_fetch_email_messages",
        lambda since, until, limit: [
            {
                "source": "email",
                "source_id": "email-1",
                "thread_key": "thread-1",
                "contact": "Dev",
                "contact_ref": "dev@example.com",
                "direction": "outgoing",
                "message_at": "2026-05-17T12:00:00Z",
                "subject": "Draft",
                "body": "I'll share the draft tomorrow.",
                "metadata": {},
            }
        ],
    )

    first = json.loads(pft.personal_followups_tool({"action": "digest"}))
    second = json.loads(pft.personal_followups_tool({"action": "digest"}))

    assert first["success"] is True
    assert first["counts"]["items_created_or_updated"] == 2
    assert "Asha" in first["summary"]
    assert "Dev via email: Draft" in first["summary"]
    assert second["counts"]["items_created_or_updated"] == 2

    listed = json.loads(pft.personal_followups_tool({"action": "list", "status_filter": "all"}))
    assert len(listed["items"]) == 2


def test_feedback_dismisses_single_item_from_last_digest(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONAL_FOLLOWUPS_DB", str(tmp_path / "followups.sqlite3"))
    fixed_now = datetime(2026, 5, 18, 3, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(pft, "_now_utc", lambda: fixed_now)
    monkeypatch.setattr(pft, "_fetch_email_messages", lambda since, until, limit: [])
    monkeypatch.setattr(
        pft,
        "_fetch_whatsapp_messages",
        lambda since, until, limit: [
            {
                "source": "whatsapp",
                "source_id": "wa-1",
                "thread_key": "asha",
                "contact": "Asha",
                "contact_ref": "asha",
                "direction": "incoming",
                "message_at": "2026-05-18T03:00:00Z",
                "subject": "",
                "body": "Can you send me the notes from yesterday?",
                "metadata": {},
            }
        ],
    )
    digest = json.loads(pft.personal_followups_tool({"action": "digest"}))
    assert "[F-" in digest["summary"]

    feedback = json.loads(
        pft.personal_followups_tool(
            {
                "action": "feedback",
                "raw_text": "I don't want to reply",
            }
        )
    )

    assert feedback["success"] is True
    assert feedback["action"] == "dismissed"
    active = json.loads(pft.personal_followups_tool({"action": "list"}))
    dismissed = json.loads(pft.personal_followups_tool({"action": "list", "status_filter": "dismissed"}))
    assert active["items"] == []
    assert len(dismissed["items"]) == 1


def test_feedback_snoozes_item_with_explicit_id(tmp_path, monkeypatch):
    monkeypatch.setenv("PERSONAL_FOLLOWUPS_DB", str(tmp_path / "followups.sqlite3"))
    fixed_now = datetime(2026, 5, 18, 3, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(pft, "_now_utc", lambda: fixed_now)
    monkeypatch.setattr(pft, "_fetch_email_messages", lambda since, until, limit: [])
    monkeypatch.setattr(
        pft,
        "_fetch_whatsapp_messages",
        lambda since, until, limit: [
            {
                "source": "whatsapp",
                "source_id": "wa-1",
                "thread_key": "asha",
                "contact": "Asha",
                "contact_ref": "asha",
                "direction": "incoming",
                "message_at": "2026-05-18T03:00:00Z",
                "subject": "",
                "body": "Please review this today.",
                "metadata": {},
            },
            {
                "source": "whatsapp",
                "source_id": "wa-2",
                "thread_key": "dev",
                "contact": "Dev",
                "contact_ref": "dev",
                "direction": "incoming",
                "message_at": "2026-05-18T03:05:00Z",
                "subject": "",
                "body": "Can you reply on the plan?",
                "metadata": {},
            },
        ],
    )
    pft.personal_followups_tool({"action": "digest"})
    items = json.loads(pft.personal_followups_tool({"action": "list"}))["items"]
    target = items[0]["id"]

    result = json.loads(
        pft.personal_followups_tool(
            {
                "action": "feedback",
                "item_id": target,
                "raw_text": f"snooze {target} until tomorrow",
            }
        )
    )

    assert result["action"] == "snoozed"
    snoozed = json.loads(pft.personal_followups_tool({"action": "list", "status_filter": "snoozed"}))
    assert snoozed["items"][0]["id"] == target
