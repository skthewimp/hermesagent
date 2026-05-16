"""Gmail draft/send helpers for Telegram voice actions."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import stat
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional


SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home()
    except Exception:
        return Path.home() / ".hermes"


def gmail_credentials_path() -> Path:
    return Path(os.getenv("GMAIL_CREDENTIALS_FILE") or _hermes_home() / "gmail_credentials.json")


def gmail_token_path() -> Path:
    return Path(os.getenv("GMAIL_TOKEN_FILE") or _hermes_home() / "gmail_token.json")


def gmail_contacts_path() -> Path:
    return Path(os.getenv("GMAIL_CONTACTS_FILE") or _hermes_home() / "gmail_contacts.json")


def email_actions_db_path() -> Path:
    return Path(os.getenv("EMAIL_ACTIONS_DB") or _hermes_home() / "email_actions.sqlite3")


@dataclass
class EmailAction:
    id: int
    user_id: str
    recipients: List[str]
    subject: str
    body: str
    status: str
    created_at: int
    sent_at: Optional[int] = None


def _connect() -> sqlite3.Connection:
    db_path = email_actions_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            recipients_json TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('drafted', 'sent', 'cancelled')),
            created_at INTEGER NOT NULL,
            sent_at INTEGER
        )
        """
    )
    conn.commit()
    return conn


def create_email_action(*, user_id: str, recipients: List[str], subject: str, body: str) -> EmailAction:
    now = int(time.time())
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO email_actions (user_id, recipients_json, subject, body, status, created_at, sent_at)
            VALUES (?, ?, ?, ?, 'drafted', ?, NULL)
            """,
            (str(user_id), json.dumps(list(recipients)), subject, body, now),
        )
        action_id = int(cur.lastrowid)
        conn.commit()
    return EmailAction(
        id=action_id,
        user_id=str(user_id),
        recipients=list(recipients),
        subject=subject,
        body=body,
        status="drafted",
        created_at=now,
    )


def update_email_action_status(action_id: int, status: str) -> None:
    sent_at = int(time.time()) if status == "sent" else None
    with _connect() as conn:
        conn.execute(
            "UPDATE email_actions SET status = ?, sent_at = ? WHERE id = ?",
            (status, sent_at, int(action_id)),
        )
        conn.commit()


def list_email_actions(*, user_id: Optional[str] = None, limit: int = 10) -> List[EmailAction]:
    limit = max(1, min(int(limit), 50))
    with _connect() as conn:
        if user_id:
            rows = conn.execute(
                """
                SELECT * FROM email_actions
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (str(user_id), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM email_actions
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [
        EmailAction(
            id=int(row["id"]),
            user_id=str(row["user_id"]),
            recipients=json.loads(row["recipients_json"] or "[]"),
            subject=str(row["subject"]),
            body=str(row["body"]),
            status=str(row["status"]),
            created_at=int(row["created_at"]),
            sent_at=int(row["sent_at"]) if row["sent_at"] is not None else None,
        )
        for row in rows
    ]


def gmail_setup_instructions() -> str:
    creds = gmail_credentials_path()
    token = gmail_token_path()
    contacts = gmail_contacts_path()
    port = int(os.getenv("GMAIL_OAUTH_PORT", "8765"))
    return (
        "Gmail is not configured yet.\n\n"
        "Setup:\n"
        "1. In Google Cloud Console, enable the Gmail API.\n"
        "2. Create an OAuth client for a Desktop app.\n"
        f"3. Download the client JSON to `{creds}`.\n"
        "4. If authenticating from your laptop, open an SSH tunnel first:\n"
        f"   `ssh -L {port}:localhost:{port} karthik@64.227.150.189`\n"
        "5. Run on the server:\n"
        f"   `/home/karthik/.hermes/hermes-agent/venv/bin/python -m gateway.platforms.gmail_actions auth`\n"
        f"6. Optional contacts map for names like Subbu: `{contacts}`\n"
        "   Example: {\"Subbu\": \"subbu@example.com\"}\n\n"
        f"Tokens will be stored at `{token}` with owner-only permissions."
    )


def _secure_file(path: Path) -> None:
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _load_credentials():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:
        raise RuntimeError("Google API auth packages are not installed.") from exc

    token_path = gmail_token_path()
    if not token_path.exists():
        return None

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        _secure_file(token_path)
    return creds


def gmail_is_configured() -> bool:
    try:
        creds = _load_credentials()
        return bool(creds and creds.valid)
    except Exception:
        return False


def run_oauth_login() -> None:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError("google-auth-oauthlib is not installed.") from exc

    creds_path = gmail_credentials_path()
    if not creds_path.exists():
        raise RuntimeError(f"Missing Gmail OAuth client JSON: {creds_path}")

    port = int(os.getenv("GMAIL_OAUTH_PORT", "8765"))
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=port, open_browser=False)
    token_path = gmail_token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    _secure_file(token_path)
    print(f"Saved Gmail token to {token_path}")


def load_contact_map() -> Dict[str, str]:
    path = gmail_contacts_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).strip().lower(): str(v).strip() for k, v in data.items() if str(k).strip() and str(v).strip()}


def resolve_recipients(recipients: List[str]) -> tuple[List[str], List[str]]:
    contacts = load_contact_map()
    resolved: List[str] = []
    unresolved: List[str] = []
    for recipient in recipients:
        text = str(recipient).strip()
        if not text:
            continue
        if "@" in text:
            resolved.append(text)
            continue
        mapped = contacts.get(text.lower())
        if mapped:
            resolved.append(mapped)
        else:
            unresolved.append(text)
    return resolved, unresolved


def send_email(*, recipients: List[str], subject: str, body: str) -> Dict[str, Any]:
    creds = _load_credentials()
    if not creds or not creds.valid:
        raise RuntimeError(gmail_setup_instructions())

    resolved, unresolved = resolve_recipients(recipients)
    if unresolved:
        raise RuntimeError(
            "I need an email address for: "
            + ", ".join(unresolved)
            + f"\n\nAdd mappings in `{gmail_contacts_path()}` or use Edit with the email address."
        )
    if not resolved:
        raise RuntimeError("No email recipients were found.")

    from googleapiclient.discovery import build

    message = EmailMessage()
    message["To"] = ", ".join(resolved)
    message["Subject"] = subject
    message.set_content(body)
    encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    service = build("gmail", "v1", credentials=creds)
    return service.users().messages().send(userId="me", body={"raw": encoded}).execute()


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Hermes Gmail action helper")
    parser.add_argument("command", choices=["auth", "status"])
    args = parser.parse_args()
    if args.command == "auth":
        run_oauth_login()
    elif args.command == "status":
        print("configured" if gmail_is_configured() else "not configured")


if __name__ == "__main__":
    _main()
