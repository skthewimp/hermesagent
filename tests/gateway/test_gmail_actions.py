import json

from gateway.platforms import gmail_actions as ga


def test_email_action_storage_roundtrip(tmp_path, monkeypatch):
    db_path = tmp_path / "email_actions.sqlite3"
    monkeypatch.setenv("EMAIL_ACTIONS_DB", str(db_path))

    action = ga.create_email_action(
        user_id="u1",
        recipients=["subbu@example.com"],
        subject="Helping accelerate Wisdom",
        body="I can help accelerate the rollout over the next few weeks.",
    )

    rows = ga.list_email_actions(user_id="u1")
    assert len(rows) == 1
    assert rows[0].id == action.id
    assert rows[0].status == "drafted"
    assert rows[0].recipients == ["subbu@example.com"]

    ga.update_email_action_status(action.id, "sent")
    rows = ga.list_email_actions(user_id="u1")
    assert rows[0].status == "sent"
    assert rows[0].sent_at is not None


def test_resolve_recipients_uses_contacts_file(tmp_path, monkeypatch):
    contacts_path = tmp_path / "gmail_contacts.json"
    contacts_path.write_text(json.dumps({"Subbu": "subbu@example.com"}), encoding="utf-8")
    monkeypatch.setenv("GMAIL_CONTACTS_FILE", str(contacts_path))

    resolved, unresolved = ga.resolve_recipients(["Subbu", "person@example.com", "Missing"])

    assert resolved == ["subbu@example.com", "person@example.com"]
    assert unresolved == ["Missing"]


def test_gmail_setup_instructions_include_expected_paths(tmp_path, monkeypatch):
    creds = tmp_path / "gmail_credentials.json"
    token = tmp_path / "gmail_token.json"
    contacts = tmp_path / "gmail_contacts.json"
    monkeypatch.setenv("GMAIL_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv("GMAIL_TOKEN_FILE", str(token))
    monkeypatch.setenv("GMAIL_CONTACTS_FILE", str(contacts))

    instructions = ga.gmail_setup_instructions()

    assert str(creds) in instructions
    assert str(token) in instructions
    assert str(contacts) in instructions
    assert "Gmail API" in instructions

