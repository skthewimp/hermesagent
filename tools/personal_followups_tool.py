"""Daily personal follow-up digest from recent Gmail and WhatsApp activity."""

from __future__ import annotations

import email as email_lib
import hashlib
import imaplib
import json
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from hermes_constants import get_hermes_home
from tools.registry import registry, tool_error


STATE_VERSION = 1
DEFAULT_LOOKBACK_DAYS = 7


PERSONAL_FOLLOWUPS_SCHEMA = {
    "name": "personal_followups",
    "description": (
        "Build and manage the user's daily personal follow-up todo digest from recent "
        "Gmail and WhatsApp messages. Use action='digest' for daily Telegram digests "
        "or when the user asks what they need to reply to/follow up on. Use "
        "action='feedback' when the user says things like 'done', 'don't want to "
        "reply', 'snooze this', or 'waiting on them' about digest items."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["digest", "feedback", "list", "status", "reset"],
                "description": "digest scans recent sources and returns today's todo digest. feedback applies user feedback. list/status inspect state. reset clears stored follow-up state.",
            },
            "lookback_days": {
                "type": "integer",
                "description": "Days of recent messages to inspect for action='digest'. Default 7, max 14.",
            },
            "limit_per_source": {
                "type": "integer",
                "description": "Maximum messages to inspect per source/mailbox. Default 150, max 300.",
            },
            "raw_text": {
                "type": "string",
                "description": "Natural-language feedback text for action='feedback'.",
            },
            "item_id": {
                "type": "string",
                "description": "Optional digest item id like F-123. If omitted for feedback, Hermes applies the feedback to the most recent digest item when unambiguous.",
            },
            "status_filter": {
                "type": "string",
                "enum": ["active", "waiting", "snoozed", "done", "dismissed", "all"],
                "description": "Optional status filter for action='list'. Default active.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "For action='digest', scan and render without persisting newly extracted items.",
            },
        },
        "required": [],
    },
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _db_path() -> Path:
    return Path(os.getenv("PERSONAL_FOLLOWUPS_DB") or get_hermes_home() / "personal_followups.sqlite3")


def _format_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    except ValueError:
        try:
            dt = parsedate_to_datetime(text)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _coerce_int(raw: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(value, maximum))


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _init_db(conn)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS source_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            source_id TEXT NOT NULL,
            thread_key TEXT NOT NULL,
            contact TEXT NOT NULL,
            contact_ref TEXT,
            direction TEXT NOT NULL,
            message_at TEXT NOT NULL,
            subject TEXT,
            body TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(source, source_id)
        );
        CREATE INDEX IF NOT EXISTS idx_source_messages_at ON source_messages(message_at);
        CREATE INDEX IF NOT EXISTS idx_source_messages_thread ON source_messages(source, thread_key);
        CREATE TABLE IF NOT EXISTS attention_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            suggested_action TEXT NOT NULL,
            source TEXT NOT NULL,
            thread_key TEXT NOT NULL,
            contact TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            priority INTEGER NOT NULL DEFAULT 2,
            reason TEXT NOT NULL,
            evidence TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            suppress_until TEXT,
            suppression_reason TEXT,
            notes TEXT,
            metadata_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_attention_status ON attention_items(status, suppress_until);
        CREATE TABLE IF NOT EXISTS item_messages (
            item_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            PRIMARY KEY (item_id, message_id)
        );
        CREATE TABLE IF NOT EXISTS feedback_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            raw_text TEXT NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT
        );
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
        (str(STATE_VERSION),),
    )
    conn.commit()


def _reset_db() -> None:
    path = _db_path()
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()


def _set_meta(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
        (key, json.dumps(value, ensure_ascii=False)),
    )


def _get_meta(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def _bridge_port() -> int:
    try:
        from gateway.config import Platform, load_gateway_config

        pconfig = load_gateway_config().platforms.get(Platform.WHATSAPP)
        if pconfig:
            return int(pconfig.extra.get("bridge_port", 3000))
    except Exception:
        pass
    return int(os.getenv("WHATSAPP_BRIDGE_PORT", "3000"))


def _fetch_whatsapp_messages(since: datetime, until: datetime, limit: int) -> list[dict[str, Any]]:
    params = {"limit": str(max(1, min(limit, 300))), "direction": "all"}
    url = f"http://127.0.0.1:{_bridge_port()}/observed?{urlencode(params)}"
    try:
        with urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        observed_at = _parse_dt(item.get("observedAt") or item.get("timestamp"))
        if observed_at is None or observed_at < since or observed_at > until:
            continue
        body = str(item.get("body") or "").strip()
        if not body and not item.get("hasMedia"):
            continue
        chat_id = str(item.get("chatId") or item.get("senderId") or "").strip()
        message_id = str(item.get("messageId") or "").strip()
        source_id = message_id or _hash_key("whatsapp", chat_id, _format_dt(observed_at), body)
        rows.append(
            {
                "source": "whatsapp",
                "source_id": source_id,
                "thread_key": chat_id or str(item.get("chatName") or "whatsapp"),
                "contact": item.get("chatName") or item.get("senderName") or chat_id or "WhatsApp",
                "contact_ref": chat_id,
                "direction": "outgoing" if item.get("direction") == "outgoing" else "incoming",
                "message_at": _format_dt(observed_at),
                "subject": "",
                "body": body or "[media]",
                "metadata": {
                    "is_group": bool(item.get("isGroup")),
                    "has_media": bool(item.get("hasMedia")),
                    "media_type": item.get("mediaType") or "",
                },
            }
        )
    return sorted(rows, key=lambda row: row["message_at"])


def _decode_header(raw: str) -> str:
    try:
        from gateway.platforms.email import _decode_header_value

        return _decode_header_value(raw)
    except Exception:
        return raw


def _extract_address(raw: str) -> str:
    try:
        from gateway.platforms.email import _extract_email_address

        return _extract_email_address(raw)
    except Exception:
        if "<" in raw and ">" in raw:
            return raw.split("<", 1)[1].split(">", 1)[0].strip().lower()
        return raw.strip().lower()


def _extract_body(msg: email_lib.message.Message) -> str:
    try:
        from gateway.platforms.email import _extract_text_body

        return _extract_text_body(msg)
    except Exception:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        return str(payload or "")


def _is_automated(sender: str, headers: dict[str, str]) -> bool:
    try:
        from gateway.platforms.email import _is_automated_sender

        return _is_automated_sender(sender, headers)
    except Exception:
        lowered = sender.lower()
        return any(part in lowered for part in ("noreply", "no-reply", "donotreply", "postmaster"))


def _email_env_configured() -> bool:
    return all(os.getenv(name) for name in ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "EMAIL_IMAP_HOST"))


def _mailboxes(imap: imaplib.IMAP4_SSL) -> list[tuple[str, str]]:
    mailboxes = [("INBOX", "incoming")]
    try:
        status, data = imap.list()
    except Exception:
        return mailboxes
    if status != "OK" or not data:
        return mailboxes
    sent_candidates: list[str] = []
    for raw in data:
        line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        if "\\Sent" in line or re.search(r'(?i)(^|[/" ])sent(?: mail| items)?("?|\Z)', line):
            match = re.search(r' "([^"]+)"$', line)
            if match:
                sent_candidates.append(match.group(1))
            else:
                sent_candidates.append(line.rsplit(" ", 1)[-1].strip('"'))
    for name in sent_candidates:
        if name and name.upper() != "INBOX":
            mailboxes.append((name, "outgoing"))
            break
    return mailboxes


def _fetch_email_messages(since: datetime, until: datetime, limit: int) -> list[dict[str, Any]]:
    if not _email_env_configured():
        return []

    address = os.getenv("EMAIL_ADDRESS", "").strip().lower()
    password = os.getenv("EMAIL_PASSWORD", "")
    imap_host = os.getenv("EMAIL_IMAP_HOST", "").strip()
    imap_port = int(os.getenv("EMAIL_IMAP_PORT", "993") or "993")
    search_since = since.strftime("%d-%b-%Y")
    rows: list[dict[str, Any]] = []

    try:
        imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30)
        try:
            imap.login(address, password)
            for mailbox, mailbox_direction in _mailboxes(imap):
                try:
                    status, _ = imap.select(f'"{mailbox}"', readonly=True)
                    if status != "OK":
                        status, _ = imap.select(mailbox, readonly=True)
                    if status != "OK":
                        continue
                    status, data = imap.uid("search", None, "SINCE", search_since)
                    if status != "OK" or not data or not data[0]:
                        continue
                    for uid in data[0].split()[-limit:]:
                        status, msg_data = imap.uid("fetch", uid, "(BODY.PEEK[])")
                        if status != "OK" or not msg_data:
                            continue
                        raw = None
                        for part in msg_data:
                            if isinstance(part, tuple) and len(part) > 1:
                                raw = part[1]
                                break
                        if not raw:
                            continue
                        msg = email_lib.message_from_bytes(raw)
                        headers = {str(key): str(value) for key, value in msg.items()}
                        sender_raw = msg.get("From", "")
                        sender_addr = _extract_address(sender_raw)
                        recipient_addr = _extract_address(msg.get("To", ""))
                        direction = mailbox_direction
                        if sender_addr == address:
                            direction = "outgoing"
                        elif _is_automated(sender_addr, headers):
                            continue
                        message_at = _parse_dt(msg.get("Date")) or until
                        if message_at < since or message_at > until:
                            continue
                        contact = sender_addr if direction == "incoming" else recipient_addr
                        sender_name = _decode_header(sender_raw)
                        if "<" in sender_name:
                            sender_name = sender_name.split("<", 1)[0].strip().strip('"')
                        subject = _decode_header(msg.get("Subject", "(no subject)"))
                        message_id = str(msg.get("Message-ID") or "").strip()
                        source_id = message_id or f"{mailbox}:{uid.decode('utf-8', errors='replace')}"
                        thread_key = str(msg.get("Thread-Index") or msg.get("In-Reply-To") or subject or contact).strip()
                        rows.append(
                            {
                                "source": "email",
                                "source_id": source_id,
                                "thread_key": _hash_key("email-thread", thread_key.lower()),
                                "contact": sender_name or contact or "Email",
                                "contact_ref": contact,
                                "direction": direction,
                                "message_at": _format_dt(message_at),
                                "subject": subject,
                                "body": _extract_body(msg).strip(),
                                "metadata": {"mailbox": mailbox, "message_id": message_id},
                            }
                        )
                except Exception:
                    continue
        finally:
            try:
                imap.logout()
            except Exception:
                pass
    except Exception:
        return []

    return sorted(rows, key=lambda row: row["message_at"])


def _hash_key(*parts: Any) -> str:
    text = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _clean_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _snippet(text: str, limit: int = 180) -> str:
    clean = _clean_text(text)
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


_INCOMING_ACTION_RE = re.compile(
    r"\b(can you|could you|please|pls|send me|share|review|reply|respond|let me know|"
    r"follow up|remind me|available|free\?|thoughts\?|wdyt|what do you think)\b|\?",
    re.IGNORECASE,
)
_OUTGOING_COMMIT_RE = re.compile(
    r"\b(i will|i'll|i can|i should|let me|will send|will share|will check|"
    r"get back|circle back|follow up|tomorrow|tonight|later today|next week)\b",
    re.IGNORECASE,
)
_OUTGOING_WAITING_RE = re.compile(
    r"\b(can you|could you|please|let me know|waiting for|following up|any update|"
    r"thoughts|wdyt)\b|\?",
    re.IGNORECASE,
)


def _upsert_source_message(conn: sqlite3.Connection, row: dict[str, Any], now: datetime) -> int:
    conn.execute(
        """
        INSERT INTO source_messages(
            source, source_id, thread_key, contact, contact_ref, direction,
            message_at, subject, body, metadata_json, created_at
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, source_id) DO UPDATE SET
            thread_key = excluded.thread_key,
            contact = excluded.contact,
            contact_ref = excluded.contact_ref,
            direction = excluded.direction,
            message_at = excluded.message_at,
            subject = excluded.subject,
            body = excluded.body,
            metadata_json = excluded.metadata_json
        """,
        (
            row["source"],
            row["source_id"],
            row["thread_key"],
            row["contact"],
            row.get("contact_ref"),
            row["direction"],
            row["message_at"],
            row.get("subject") or "",
            row.get("body") or "",
            json.dumps(row.get("metadata") or {}, ensure_ascii=False),
            _format_dt(now),
        ),
    )
    msg = conn.execute(
        "SELECT id FROM source_messages WHERE source = ? AND source_id = ?",
        (row["source"], row["source_id"]),
    ).fetchone()
    return int(msg["id"])


def _candidate_from_message(row: sqlite3.Row) -> dict[str, Any] | None:
    body = _clean_text(row["body"] or "")
    subject = _clean_text(row["subject"] or "")
    searchable = f"{subject} {body}".strip()
    if len(searchable) < 8:
        return None

    direction = row["direction"]
    status = "active"
    reason = ""
    action = ""
    priority = 2
    if direction == "incoming" and _INCOMING_ACTION_RE.search(searchable):
        reason = "Looks like they asked for a response or action."
        action = "Reply or decide no reply is needed."
        priority = 1 if "?" in searchable else 2
    elif direction == "outgoing" and _OUTGOING_COMMIT_RE.search(searchable):
        reason = "Looks like you committed to follow up."
        action = "Follow through or mark it done."
        priority = 1
    elif direction == "outgoing" and _OUTGOING_WAITING_RE.search(searchable):
        status = "waiting"
        reason = "Looks like you are waiting on them."
        action = "No action unless you want to follow up."
        priority = 3
    else:
        return None

    title_subject = f": {subject}" if subject else ""
    source_label = "email" if row["source"] == "email" else "WhatsApp"
    title = f"{row['contact']} via {source_label}{title_subject}"
    evidence = _snippet(body or subject, 220)
    fingerprint = _hash_key(row["source"], row["thread_key"], action.lower(), title.lower())
    return {
        "fingerprint": fingerprint,
        "title": title[:240],
        "suggested_action": action,
        "source": row["source"],
        "thread_key": row["thread_key"],
        "contact": row["contact"],
        "status": status,
        "priority": priority,
        "reason": reason,
        "evidence": evidence,
        "metadata": {"direction": direction, "message_at": row["message_at"]},
    }


def _upsert_attention_item(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    message_id: int,
    now: datetime,
) -> int:
    now_text = _format_dt(now)
    existing = conn.execute(
        "SELECT id, status FROM attention_items WHERE fingerprint = ?",
        (candidate["fingerprint"],),
    ).fetchone()
    if existing:
        if existing["status"] in {"done", "dismissed"}:
            item_id = int(existing["id"])
        else:
            conn.execute(
                """
                UPDATE attention_items
                SET title = ?, suggested_action = ?, contact = ?, priority = ?,
                    reason = ?, evidence = ?, last_seen_at = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    candidate["title"],
                    candidate["suggested_action"],
                    candidate["contact"],
                    candidate["priority"],
                    candidate["reason"],
                    candidate["evidence"],
                    now_text,
                    json.dumps(candidate.get("metadata") or {}, ensure_ascii=False),
                    int(existing["id"]),
                ),
            )
            item_id = int(existing["id"])
    else:
        cursor = conn.execute(
            """
            INSERT INTO attention_items(
                fingerprint, title, suggested_action, source, thread_key, contact,
                status, priority, reason, evidence, first_seen_at, last_seen_at,
                metadata_json
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate["fingerprint"],
                candidate["title"],
                candidate["suggested_action"],
                candidate["source"],
                candidate["thread_key"],
                candidate["contact"],
                candidate["status"],
                candidate["priority"],
                candidate["reason"],
                candidate["evidence"],
                now_text,
                now_text,
                json.dumps(candidate.get("metadata") or {}, ensure_ascii=False),
            ),
        )
        item_id = int(cursor.lastrowid)
    conn.execute(
        "INSERT OR IGNORE INTO item_messages(item_id, message_id) VALUES(?, ?)",
        (item_id, message_id),
    )
    return item_id


def _scan_sources(conn: sqlite3.Connection, since: datetime, until: datetime, limit: int, dry_run: bool) -> dict[str, int]:
    now = _now_utc()
    source_rows = _fetch_whatsapp_messages(since, until, limit) + _fetch_email_messages(since, until, limit)
    counts = {"messages": len(source_rows), "items_created_or_updated": 0}
    if dry_run:
        return counts
    for source_row in source_rows:
        message_id = _upsert_source_message(conn, source_row, now)
        stored = conn.execute("SELECT * FROM source_messages WHERE id = ?", (message_id,)).fetchone()
        candidate = _candidate_from_message(stored)
        if not candidate:
            continue
        _upsert_attention_item(conn, candidate, message_id, now)
        counts["items_created_or_updated"] += 1
    conn.commit()
    return counts


def _visible_items(conn: sqlite3.Connection, now: datetime, status_filter: str = "active") -> list[sqlite3.Row]:
    now_text = _format_dt(now)
    if status_filter == "all":
        query = "SELECT * FROM attention_items ORDER BY status, priority, last_seen_at DESC LIMIT 50"
        return list(conn.execute(query))
    if status_filter == "snoozed":
        return list(
            conn.execute(
                "SELECT * FROM attention_items WHERE status = 'snoozed' ORDER BY suppress_until, priority LIMIT 50"
            )
        )
    if status_filter in {"done", "dismissed", "waiting"}:
        return list(
            conn.execute(
                "SELECT * FROM attention_items WHERE status = ? ORDER BY priority, last_seen_at DESC LIMIT 50",
                (status_filter,),
            )
        )
    return list(
        conn.execute(
            """
            SELECT * FROM attention_items
            WHERE status = 'active'
               OR (status = 'snoozed' AND (suppress_until IS NULL OR suppress_until <= ?))
            ORDER BY priority ASC, last_seen_at DESC
            LIMIT 20
            """,
            (now_text,),
        )
    )


def _public_id(item_id: int) -> str:
    return f"F-{item_id}"


def _parse_public_id(value: Any) -> int | None:
    text = str(value or "").strip()
    match = re.search(r"\bF-?(\d+)\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if text.isdigit():
        return int(text)
    return None


def _render_digest(conn: sqlite3.Connection, now: datetime, counts: dict[str, int]) -> str:
    active = _visible_items(conn, now, "active")
    waiting = _visible_items(conn, now, "waiting")[:5]
    visible_ids = [int(row["id"]) for row in active]
    _set_meta(conn, "last_digest_item_ids", visible_ids)
    _set_meta(conn, "last_digest_at", _format_dt(now))
    conn.commit()

    if not active and not waiting:
        return "Daily follow-ups\n\nNo reply/follow-up todos found from the last week."

    lines = ["Daily follow-ups", ""]
    if active:
        lines.append("Waiting on you")
        for idx, row in enumerate(active, start=1):
            lines.append(f"{idx}. [{_public_id(row['id'])}] {row['title']}")
            lines.append(f"   Action: {row['suggested_action']}")
            lines.append(f"   Why: {row['reason']} {row['evidence']}")
        lines.append("")
    if waiting:
        lines.append("Waiting on others")
        for row in waiting:
            lines.append(f"- [{_public_id(row['id'])}] {row['title']}")
            lines.append(f"  Note: {row['evidence']}")
        lines.append("")
    lines.append(
        f"Scanned {counts.get('messages', 0)} recent Gmail/WhatsApp message(s); "
        f"updated {counts.get('items_created_or_updated', 0)} follow-up candidate(s)."
    )
    return "\n".join(lines).strip()


def _resolve_feedback_item(conn: sqlite3.Connection, args: dict[str, Any]) -> int | None:
    item_id = _parse_public_id(args.get("item_id")) or _parse_public_id(args.get("raw_text"))
    if item_id:
        return item_id
    last_ids = _get_meta(conn, "last_digest_item_ids", [])
    if isinstance(last_ids, list) and len(last_ids) == 1:
        try:
            return int(last_ids[0])
        except Exception:
            return None
    return None


def _parse_feedback_action(text: str) -> tuple[str, str | None]:
    lowered = text.lower()
    if any(phrase in lowered for phrase in ("don't want to reply", "do not want to reply", "no reply", "ignore", "dismiss")):
        return "dismissed", "no reply needed"
    if any(word in lowered for word in ("done", "replied", "handled", "completed", "clear it")):
        return "done", "marked done"
    if "waiting on them" in lowered or "waiting for them" in lowered or "they owe" in lowered:
        return "waiting", "waiting on them"
    if "snooze" in lowered or "remind" in lowered or "tomorrow" in lowered or "next week" in lowered:
        return "snoozed", "snoozed"
    if lowered.startswith("note") or "note:" in lowered:
        return "note", None
    return "unknown", None


def _snooze_until(text: str, now: datetime) -> datetime:
    lowered = text.lower()
    if "next week" in lowered:
        return now + timedelta(days=7)
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", lowered)
    if match:
        parsed = _parse_dt(match.group(1))
        if parsed:
            return parsed
    return now + timedelta(days=1)


def _apply_feedback(conn: sqlite3.Connection, args: dict[str, Any]) -> str:
    raw_text = str(args.get("raw_text") or "").strip()
    if not raw_text:
        return tool_error("raw_text is required for action='feedback'")
    item_id = _resolve_feedback_item(conn, args)
    if not item_id:
        return tool_error("Could not identify a follow-up item. Include an id like F-12.")
    item = conn.execute("SELECT * FROM attention_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return tool_error(f"Unknown follow-up item: {_public_id(item_id)}")

    now = _now_utc()
    action, reason = _parse_feedback_action(raw_text)
    if action == "unknown":
        return tool_error("Could not infer feedback action. Say done, dismiss/no reply, snooze, waiting on them, or note.")
    if action == "note":
        existing = str(item["notes"] or "").strip()
        note = raw_text
        notes = f"{existing}\n{_format_dt(now)} {note}".strip()
        conn.execute("UPDATE attention_items SET notes = ? WHERE id = ?", (notes, item_id))
    elif action == "snoozed":
        until = _snooze_until(raw_text, now)
        conn.execute(
            "UPDATE attention_items SET status = 'snoozed', suppress_until = ?, suppression_reason = ? WHERE id = ?",
            (_format_dt(until), reason, item_id),
        )
    else:
        conn.execute(
            "UPDATE attention_items SET status = ?, suppression_reason = ?, suppress_until = NULL WHERE id = ?",
            (action, reason, item_id),
        )
    conn.execute(
        "INSERT INTO feedback_events(item_id, raw_text, action, created_at, metadata_json) VALUES(?, ?, ?, ?, ?)",
        (item_id, raw_text, action, _format_dt(now), json.dumps({"reason": reason}, ensure_ascii=False)),
    )
    conn.commit()
    return json.dumps(
        {
            "success": True,
            "item_id": _public_id(item_id),
            "action": action,
            "summary": f"{_public_id(item_id)} updated: {action}.",
        },
        ensure_ascii=False,
    )


def _list_items(conn: sqlite3.Connection, status_filter: str) -> str:
    now = _now_utc()
    rows = _visible_items(conn, now, status_filter)
    return json.dumps(
        {
            "success": True,
            "items": [
                {
                    "id": _public_id(int(row["id"])),
                    "title": row["title"],
                    "status": row["status"],
                    "contact": row["contact"],
                    "suggested_action": row["suggested_action"],
                    "last_seen_at": row["last_seen_at"],
                    "suppress_until": row["suppress_until"],
                }
                for row in rows
            ],
        },
        ensure_ascii=False,
    )


def personal_followups_tool(args, **kw):
    action = str(args.get("action") or "digest").strip().lower()
    if action == "reset":
        _reset_db()
        return json.dumps({"success": True, "db_path": str(_db_path())})

    conn = _connect()
    try:
        if action == "status":
            total_messages = conn.execute("SELECT COUNT(*) AS c FROM source_messages").fetchone()["c"]
            total_items = conn.execute("SELECT COUNT(*) AS c FROM attention_items").fetchone()["c"]
            return json.dumps(
                {
                    "success": True,
                    "db_path": str(_db_path()),
                    "messages": total_messages,
                    "items": total_items,
                    "last_digest_at": _get_meta(conn, "last_digest_at"),
                },
                ensure_ascii=False,
            )
        if action == "list":
            status_filter = str(args.get("status_filter") or "active").strip().lower()
            if status_filter not in {"active", "waiting", "snoozed", "done", "dismissed", "all"}:
                status_filter = "active"
            return _list_items(conn, status_filter)
        if action == "feedback":
            return _apply_feedback(conn, args)
        if action != "digest":
            return tool_error(f"Unknown personal_followups action: {action}")

        now = _now_utc()
        lookback_days = _coerce_int(args.get("lookback_days"), DEFAULT_LOOKBACK_DAYS, minimum=1, maximum=14)
        limit = _coerce_int(args.get("limit_per_source"), 150, minimum=1, maximum=300)
        since = now - timedelta(days=lookback_days)
        counts = _scan_sources(conn, since, now, limit, dry_run=bool(args.get("dry_run")))
        summary = _render_digest(conn, now, counts)
        return json.dumps(
            {
                "success": True,
                "since": _format_dt(since),
                "until": _format_dt(now),
                "counts": counts,
                "summary": summary,
            },
            ensure_ascii=False,
        )
    finally:
        conn.close()


registry.register(
    name="personal_followups",
    toolset="messaging",
    schema=PERSONAL_FOLLOWUPS_SCHEMA,
    handler=personal_followups_tool,
    emoji="✅",
    max_result_size_chars=40_000,
)
