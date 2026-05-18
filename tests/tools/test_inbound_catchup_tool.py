import json
from datetime import datetime, timezone

from tools import inbound_catchup_tool as ict


def test_inbound_catchup_filters_since_and_advances_checkpoint(tmp_path, monkeypatch):
    state_path = tmp_path / "catchup.json"
    monkeypatch.setenv("INBOUND_CATCHUP_STATE_FILE", str(state_path))

    fixed_now = datetime(2026, 5, 18, 10, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(ict, "_now_utc", lambda: fixed_now)
    monkeypatch.setattr(
        ict,
        "_fetch_whatsapp_messages",
        lambda since, until, limit: [
            {
                "source": "whatsapp",
                "at": "2026-05-18T10:05:00Z",
                "from": "Asha",
                "body": "Can we move the 3pm call?",
            }
        ],
    )
    monkeypatch.setattr(
        ict,
        "_fetch_email_messages",
        lambda since, until, limit: [
            {
                "source": "email",
                "at": "2026-05-18T10:10:00Z",
                "from": "Dev",
                "subject": "Build status",
                "body": "The deploy passed.",
            }
        ],
    )

    ict.inbound_catchup_tool({"action": "reset"})
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_catchup_at"] == "2026-05-18T10:30:00Z"

    later_now = datetime(2026, 5, 18, 11, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(ict, "_now_utc", lambda: later_now)
    result = json.loads(ict.inbound_catchup_tool({"action": "catch_up"}))

    assert result["success"] is True
    assert result["since"] == "2026-05-18T10:30:00Z"
    assert result["until"] == "2026-05-18T11:00:00Z"
    assert result["counts"] == {"whatsapp": 1, "email": 1}
    assert "Asha" in result["summary"]
    assert "Build status" in result["summary"]
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["last_catchup_at"] == "2026-05-18T11:00:00Z"


def test_render_summary_handles_empty_window():
    since = datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc)
    until = datetime(2026, 5, 18, 11, 0, tzinfo=timezone.utc)

    summary = ict._render_summary(since, until, [], [])

    assert "No new WhatsApp or email inbounds" in summary


def test_whatsapp_fetch_keeps_incoming_messages_in_window(monkeypatch):
    payload = [
        {
            "observedAt": "2026-05-18T09:59:59Z",
            "direction": "incoming",
            "senderName": "Old",
            "body": "too old",
        },
        {
            "observedAt": "2026-05-18T10:15:00Z",
            "direction": "incoming",
            "senderName": "New",
            "body": "inside window",
        },
    ]

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(payload).encode("utf-8")

    monkeypatch.setattr(ict, "urlopen", lambda *args, **kwargs: FakeResponse())

    rows = ict._fetch_whatsapp_messages(
        datetime(2026, 5, 18, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 18, 11, 0, tzinfo=timezone.utc),
        100,
    )

    assert len(rows) == 1
    assert rows[0]["from"] == "New"
    assert rows[0]["body"] == "inside window"
