"""Tool-only WhatsApp inbox access for the local Baileys bridge."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import urlopen

from hermes_constants import get_hermes_home
from tools.registry import registry, tool_error


WHATSAPP_SCHEMA = {
    "name": "whatsapp",
    "description": (
        "Read recent WhatsApp messages observed by the local WhatsApp bridge. "
        "Use this when the user asks to summarize WhatsApp, find messages, "
        "review conversations, or recommend actions based on WhatsApp. "
        "For sending WhatsApp messages, use send_message with target='whatsapp:<name-or-phone>'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["recent", "search", "chats", "contacts"],
                "description": "recent: return recent observed messages. search: keyword search. chats: list observed WhatsApp chats. contacts: search live WhatsApp contacts known to the bridge.",
            },
            "chat": {
                "type": "string",
                "description": "Optional chat/contact filter. Accepts a contact name, phone/JID, or chat id.",
            },
            "query": {
                "type": "string",
                "description": "Search text for action='search'. Case-insensitive substring match.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return. Default 50, max 200.",
            },
            "direction": {
                "type": "string",
                "enum": ["incoming", "outgoing", "all"],
                "description": "Filter by message direction. Default all.",
            },
        },
        "required": [],
    },
}


def _bridge_port() -> int:
    try:
        from gateway.config import Platform, load_gateway_config

        config = load_gateway_config()
        pconfig = config.platforms.get(Platform.WHATSAPP)
        if pconfig:
            return int(pconfig.extra.get("bridge_port", 3000))
    except Exception:
        pass
    return int(os.getenv("WHATSAPP_BRIDGE_PORT", "3000"))


def _normalize_ref(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "@" in text:
        text = text.split("@", 1)[0]
    if ":" in text:
        text = text.split(":", 1)[0]
    return "".join(ch for ch in text if ch.isalnum())


def _contact_map() -> dict[str, str]:
    path = Path(os.getenv("WHATSAPP_CONTACTS_FILE") or (get_hermes_home() / "whatsapp_contacts.json"))
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    items: Iterable[tuple[Any, Any]]
    if isinstance(data, dict):
        items = data.items()
    elif isinstance(data, list):
        rows = []
        for item in data:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            target = item.get("id") or item.get("chat_id") or item.get("phone") or item.get("jid")
            if name and target:
                rows.append((name, target))
        items = rows
    else:
        return {}

    mapping: dict[str, str] = {}
    for name, target in items:
        label = str(name or "").strip()
        if not label:
            continue
        mapping[_normalize_ref(name)] = label
        mapping[_normalize_ref(target)] = label
    return mapping


def _fetch_observed_messages(args: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    params: dict[str, str] = {"limit": str(max(1, min(limit, 200)))}
    for key in ("chat", "query", "direction"):
        value = str(args.get(key) or "").strip()
        if value and not (key == "direction" and value == "all"):
            params[key] = value
    url = f"http://127.0.0.1:{_bridge_port()}/observed?{urlencode(params)}"
    try:
        with urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _fetch_live_contacts(query: str, limit: int) -> list[dict[str, Any]]:
    params: dict[str, str] = {"limit": str(max(1, min(limit, 100)))}
    if query:
        params["query"] = query
    url = f"http://127.0.0.1:{_bridge_port()}/contacts?{urlencode(params)}"
    try:
        with urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _display_name(record: dict[str, Any], contacts: dict[str, str]) -> str:
    for key in ("chatId", "senderId"):
        label = contacts.get(_normalize_ref(record.get(key)))
        if label:
            return label
    return str(record.get("chatName") or record.get("senderName") or record.get("chatId") or "")


def _matches_chat(record: dict[str, Any], chat: str, contacts: dict[str, str]) -> bool:
    if not chat:
        return True
    needle = _normalize_ref(chat)
    candidates = [
        record.get("chatId"),
        record.get("senderId"),
        record.get("chatName"),
        record.get("senderName"),
        _display_name(record, contacts),
    ]
    return any(needle and needle in _normalize_ref(candidate) for candidate in candidates)


def _clean_record(record: dict[str, Any], contacts: dict[str, str]) -> dict[str, Any]:
    keys = [
        "observedAt",
        "direction",
        "messageId",
        "chatId",
        "senderId",
        "senderName",
        "chatName",
        "isGroup",
        "body",
        "hasMedia",
        "mediaType",
        "mediaUrls",
        "timestamp",
    ]
    cleaned = {key: record.get(key) for key in keys if key in record}
    cleaned["displayName"] = _display_name(record, contacts)
    return cleaned


def _parse_limit(raw: Any, default: int = 50) -> int:
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(1, min(value, 200))


def whatsapp_tool(args, **kw):
    action = str(args.get("action") or "recent").lower()
    limit = _parse_limit(args.get("limit"))
    chat = str(args.get("chat") or "").strip()
    direction = str(args.get("direction") or "all").lower()
    contacts = _contact_map()

    if action == "contacts":
        query = str(args.get("query") or chat).strip()
        return json.dumps(
            {
                "storage": "in_memory_only",
                "contacts": _fetch_live_contacts(query, limit),
            },
            ensure_ascii=False,
        )

    fetch_limit = max(limit * 10, 200) if action == "chats" else limit
    messages = _fetch_observed_messages(
        {**args, "direction": direction if direction in {"incoming", "outgoing"} else "all"},
        fetch_limit,
    )
    if chat:
        messages = [msg for msg in messages if _matches_chat(msg, chat, contacts)]

    if action == "recent":
        return json.dumps(
            {
                "storage": "in_memory_only",
                "messages": [_clean_record(msg, contacts) for msg in messages[-limit:]],
            },
            ensure_ascii=False,
        )

    if action == "search":
        query = str(args.get("query") or "").strip().lower()
        if not query:
            return tool_error("query is required for action='search'")
        matches = [msg for msg in messages if query in str(msg.get("body") or "").lower()]
        return json.dumps(
            {
                "storage": "in_memory_only",
                "matches": [_clean_record(msg, contacts) for msg in matches[-limit:]],
            },
            ensure_ascii=False,
        )

    if action == "chats":
        grouped: dict[str, dict[str, Any]] = {}
        for msg in messages:
            chat_id = str(msg.get("chatId") or "")
            if not chat_id:
                continue
            entry = grouped.setdefault(
                chat_id,
                {
                    "chatId": chat_id,
                    "displayName": _display_name(msg, contacts),
                    "chatName": msg.get("chatName"),
                    "isGroup": bool(msg.get("isGroup")),
                    "messageCount": 0,
                    "lastObservedAt": None,
                    "lastBody": "",
                },
            )
            entry["messageCount"] += 1
            entry["lastObservedAt"] = msg.get("observedAt")
            entry["lastBody"] = msg.get("body") or ""
        chats = sorted(
            grouped.values(),
            key=lambda item: item.get("lastObservedAt") or datetime.min.isoformat(),
            reverse=True,
        )
        return json.dumps({"storage": "in_memory_only", "chats": chats[:limit]}, ensure_ascii=False)

    return tool_error(f"Unknown WhatsApp action: {action}")


def _check_whatsapp_tool() -> bool:
    try:
        with urlopen(f"http://127.0.0.1:{_bridge_port()}/health", timeout=2) as response:
            return response.status == 200
    except Exception:
        try:
            from gateway.status import is_gateway_running

            return is_gateway_running()
        except Exception:
            return False


registry.register(
    name="whatsapp",
    toolset="messaging",
    schema=WHATSAPP_SCHEMA,
    handler=whatsapp_tool,
    check_fn=_check_whatsapp_tool,
    emoji="💬",
)
