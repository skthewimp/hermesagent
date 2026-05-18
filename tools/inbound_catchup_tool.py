"""On-demand inbound catch-up across WhatsApp and email."""

from __future__ import annotations

import email as email_lib
import imaplib
import json
import os
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
DEFAULT_LOOKBACK_HOURS = 24


INBOUND_CATCHUP_SCHEMA = {
    "name": "inbound_catchup",
    "description": (
        "Catch the user up on inbound WhatsApp and email messages since the last catch-up. "
        "Use this when the user says phrases like 'catch me up on my inbounds', "
        "'what did I miss', or asks for an inbound summary. The tool advances its "
        "checkpoint after action='catch_up' unless advance_checkpoint is false."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["catch_up", "status", "reset"],
                "description": "catch_up summarizes new inbounds and advances the checkpoint. status shows the current checkpoint. reset sets the checkpoint to now.",
            },
            "advance_checkpoint": {
                "type": "boolean",
                "description": "Whether action='catch_up' should mark the included interval as caught up. Default true.",
            },
            "lookback_hours": {
                "type": "integer",
                "description": "Fallback lookback if there is no checkpoint yet. Default 24, max 168.",
            },
            "limit_per_source": {
                "type": "integer",
                "description": "Maximum raw messages to inspect per source. Default 100, max 200.",
            },
        },
        "required": [],
    },
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _state_path() -> Path:
    return Path(os.getenv("INBOUND_CATCHUP_STATE_FILE") or get_hermes_home() / "inbound_catchup_state.json")


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


def _format_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return {"version": STATE_VERSION}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": STATE_VERSION}
    return data if isinstance(data, dict) else {"version": STATE_VERSION}


def _write_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": STATE_VERSION, **state}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _coerce_int(raw: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(value, maximum))


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
    params = {"limit": str(max(1, min(limit, 200))), "direction": "incoming"}
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
        rows.append(
            {
                "source": "whatsapp",
                "at": _format_dt(observed_at),
                "from": item.get("senderName") or item.get("chatName") or item.get("senderId") or item.get("chatId") or "WhatsApp",
                "chat": item.get("chatName") or item.get("chatId") or "",
                "body": str(item.get("body") or "").strip(),
                "media": bool(item.get("hasMedia")),
                "media_type": item.get("mediaType") or "",
            }
        )
    return sorted(rows, key=lambda row: row["at"])


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


def _is_automated(sender: str, headers: dict[str, str]) -> bool:
    try:
        from gateway.platforms.email import _is_automated_sender

        return _is_automated_sender(sender, headers)
    except Exception:
        lowered = sender.lower()
        return any(part in lowered for part in ("noreply", "no-reply", "donotreply", "postmaster"))


def _extract_body(msg: email_lib.message.Message) -> str:
    try:
        from gateway.platforms.email import _extract_text_body

        return _extract_text_body(msg)
    except Exception:
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        return str(payload or "")


def _email_env_configured() -> bool:
    return all(
        os.getenv(name)
        for name in ("EMAIL_ADDRESS", "EMAIL_PASSWORD", "EMAIL_IMAP_HOST")
    )


def _fetch_email_messages(since: datetime, until: datetime, limit: int) -> list[dict[str, Any]]:
    if not _email_env_configured():
        return []

    address = os.getenv("EMAIL_ADDRESS", "").strip()
    password = os.getenv("EMAIL_PASSWORD", "")
    imap_host = os.getenv("EMAIL_IMAP_HOST", "").strip()
    imap_port = int(os.getenv("EMAIL_IMAP_PORT", "993") or "993")
    search_since = since.strftime("%d-%b-%Y")
    rows: list[dict[str, Any]] = []

    try:
        imap = imaplib.IMAP4_SSL(imap_host, imap_port, timeout=30)
        try:
            imap.login(address, password)
            try:
                from gateway.platforms.email import _send_imap_id

                _send_imap_id(imap)
            except Exception:
                pass
            imap.select("INBOX", readonly=True)
            status, data = imap.uid("search", None, "SINCE", search_since)
            if status != "OK" or not data or not data[0]:
                return []
            uids = data[0].split()[-limit:]
            for uid in uids:
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
                sender_raw = msg.get("From", "")
                sender_addr = _extract_address(sender_raw)
                if sender_addr == address.lower():
                    continue
                headers = {str(key): str(value) for key, value in msg.items()}
                if _is_automated(sender_addr, headers):
                    continue
                message_at = _parse_dt(msg.get("Date")) or until
                if message_at < since or message_at > until:
                    continue
                sender_name = _decode_header(sender_raw)
                if "<" in sender_name:
                    sender_name = sender_name.split("<", 1)[0].strip().strip('"')
                rows.append(
                    {
                        "source": "email",
                        "at": _format_dt(message_at),
                        "from": sender_name or sender_addr,
                        "address": sender_addr,
                        "subject": _decode_header(msg.get("Subject", "(no subject)")),
                        "body": _extract_body(msg).strip(),
                    }
                )
        finally:
            try:
                imap.logout()
            except Exception:
                pass
    except Exception:
        return []

    return sorted(rows, key=lambda row: row["at"])


def _snippet(text: str, limit: int = 220) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."


def _render_summary(since: datetime, until: datetime, whatsapp: list[dict[str, Any]], email_rows: list[dict[str, Any]]) -> str:
    total = len(whatsapp) + len(email_rows)
    lines = [
        f"Inbound catch-up since {_format_dt(since)}",
        f"Window end: {_format_dt(until)}",
        "",
    ]
    if total == 0:
        lines.append("No new WhatsApp or email inbounds found in this window.")
        return "\n".join(lines)

    if whatsapp:
        lines.append(f"WhatsApp ({len(whatsapp)})")
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in whatsapp:
            grouped[str(row.get("from") or "WhatsApp")].append(row)
        for sender, rows in sorted(grouped.items(), key=lambda item: item[0].lower()):
            lines.append(f"- {sender}: {len(rows)} message(s)")
            for row in rows[-3:]:
                body = _snippet(row.get("body") or ("[media]" if row.get("media") else ""))
                if body:
                    lines.append(f"  - {body}")
        lines.append("")

    if email_rows:
        lines.append(f"Email ({len(email_rows)})")
        for row in email_rows[-20:]:
            sender = row.get("from") or row.get("address") or "Email"
            subject = row.get("subject") or "(no subject)"
            body = _snippet(row.get("body") or "", 180)
            lines.append(f"- {sender}: {subject}")
            if body:
                lines.append(f"  - {body}")

    return "\n".join(lines).strip()


def inbound_catchup_tool(args, **kw):
    action = str(args.get("action") or "catch_up").strip().lower()
    now = _now_utc()
    state = _load_state()

    if action == "reset":
        _write_state({"last_catchup_at": _format_dt(now)})
        return json.dumps({"success": True, "last_catchup_at": _format_dt(now)})

    checkpoint = _parse_dt(state.get("last_catchup_at"))
    if action == "status":
        return json.dumps(
            {
                "last_catchup_at": _format_dt(checkpoint) if checkpoint else None,
                "state_file": str(_state_path()),
            }
        )

    if action != "catch_up":
        return tool_error(f"Unknown inbound_catchup action: {action}")

    lookback_hours = _coerce_int(args.get("lookback_hours"), DEFAULT_LOOKBACK_HOURS, minimum=1, maximum=168)
    limit = _coerce_int(args.get("limit_per_source"), 100, minimum=1, maximum=200)
    since = checkpoint or (now - timedelta(hours=lookback_hours))

    whatsapp = _fetch_whatsapp_messages(since, now, limit)
    email_rows = _fetch_email_messages(since, now, limit)
    summary = _render_summary(since, now, whatsapp, email_rows)

    advance = args.get("advance_checkpoint")
    if advance is None or bool(advance):
        _write_state({"last_catchup_at": _format_dt(now)})

    return json.dumps(
        {
            "success": True,
            "since": _format_dt(since),
            "until": _format_dt(now),
            "checkpoint_advanced": advance is None or bool(advance),
            "counts": {"whatsapp": len(whatsapp), "email": len(email_rows)},
            "summary": summary,
        },
        ensure_ascii=False,
    )


registry.register(
    name="inbound_catchup",
    toolset="messaging",
    schema=INBOUND_CATCHUP_SCHEMA,
    handler=inbound_catchup_tool,
    emoji="📥",
    max_result_size_chars=40_000,
)
