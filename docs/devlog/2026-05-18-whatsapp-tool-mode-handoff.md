# WhatsApp Tool Mode Handoff - 2026-05-18

## User Intent

Hermes should be contacted by the user on Telegram, not WhatsApp. WhatsApp is a tool Hermes can use on the user's behalf:

- send WhatsApp messages to contacts by name
- read recently observed WhatsApp messages
- summarize WhatsApp conversations
- recommend actions based on WhatsApp messages

Do not route the user's Hermes control conversation through WhatsApp.

## Privacy Constraints

- Do not commit contact data, phone numbers, WhatsApp session files, tokens, message bodies, or runtime cache files.
- WhatsApp message bodies should remain in memory only.
- Persistent message-body logging was intentionally removed.
- Runtime WhatsApp contacts may be cached outside the repo at:

```text
~/.hermes/whatsapp/contacts_cache.json
```

That runtime cache must not be copied into the git repo.

## Relevant Commits

- `5f4b76517 feat: add WhatsApp tool mode`
- `118a76dcb fix: resolve WhatsApp contacts from bridge`
- `51d3581dc feat: cache WhatsApp contacts in bridge`

All were pushed to `origin/main`.

## Current Repo State

As of this handoff, the repo was clean after commit `51d3581dc`.

Key changed files:

- `scripts/whatsapp-bridge/bridge.js`
- `tools/send_message_tool.py`
- `tools/whatsapp_tool.py`
- `tools/cronjob_tools.py`
- `tests/tools/test_send_message_tool.py`

## Implemented Behavior

### Bridge Contact Resolution

`scripts/whatsapp-bridge/bridge.js` now keeps an in-memory contact index populated from:

- `messaging-history.set` contacts
- `contacts.upsert`
- `contacts.update`
- observed message sender/chat metadata

Bridge endpoints:

- `GET /contacts?query=&limit=`
- `GET /resolve-contact?query=`
- `GET /contact-sync`
- `POST /sync-contacts`

`/resolve-contact` returns success only for a unique high-confidence match. Ambiguous matches return `409 ambiguous_contact`.

### Send By Name

`tools/send_message_tool.py` now resolves `whatsapp:<name>` through the live bridge before falling back to the static channel directory.

Example user-facing request:

```text
send WhatsApp message to Alex saying ...
```

Expected tool target:

```text
whatsapp:Alex
```

### WhatsApp Read Tool

`tools/whatsapp_tool.py` supports:

- `recent`
- `search`
- `chats`
- `contacts`

It reads from bridge-observed in-memory messages and returns `storage: "in_memory_only"` for message results.

### Contact Cache

`bridge.js` can persist learned contacts outside the repo:

```text
~/.hermes/whatsapp/contacts_cache.json
```

The cache is enabled by default and can be disabled with:

```text
WHATSAPP_CONTACT_CACHE=false
```

The bridge does not write an empty cache, to avoid replacing a useful contact cache with no contacts.

Important: the cache is populated only after WhatsApp/Baileys emits contact data. A forced app-state snapshot path was tested and found too disruptive for the live bridge, so do not rely on forced rebuild during startup.

## Current Runtime State

WhatsApp was not paired/connected at the end of this work. The bridge was showing a QR code and gateway logs showed WhatsApp reconnect timeouts.

Expected recovery step:

```bash
hermes whatsapp
```

When prompted:

```text
Re-pair? This will clear the existing session. [y/N]
```

answer:

```text
y
```

Then scan the QR in WhatsApp/WhatsApp Business:

```text
Settings -> Linked Devices -> Link a Device
```

After pairing:

```bash
pm2 restart hermes --update-env
```

Then verify without printing contacts:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python - <<'PY'
from urllib.request import urlopen
import json
for path in ("health", "contact-sync"):
    with urlopen(f"http://127.0.0.1:3000/{path}", timeout=5) as r:
        data = json.loads(r.read().decode())
    if path == "health":
        print("health", data.get("status"), data.get("queueLength"))
    else:
        print("contact_sync", "count", data.get("contactCount"), "runs", data.get("runs"), "error", bool(data.get("lastError")))
PY
```

## Verification Already Run

After the code changes:

```bash
node --check scripts/whatsapp-bridge/bridge.js
$HOME/.hermes/hermes-agent/venv/bin/python -m pytest tests/tools/test_send_message_tool.py -k whatsapp
$HOME/.hermes/hermes-agent/venv/bin/python -m ruff check tools/send_message_tool.py tools/whatsapp_tool.py tests/tools/test_send_message_tool.py
git diff --check
```

These passed before the final cache commit.

Privacy scan over changed files only found the literal runtime cache filename, not contact data or secrets.

## Known Issues / Follow-Up

1. Re-pair WhatsApp before testing live sends.
2. After re-pairing, wait for WhatsApp/Baileys contact events to populate the cache.
3. Confirm `contacts_cache.json` exists outside the repo and has nonzero contacts without printing contents.
4. Confirm name resolution for a user-provided contact without printing the resolved JID/phone:

```bash
$HOME/.hermes/hermes-agent/venv/bin/python - <<'PY'
from tools.send_message_tool import _resolve_whatsapp_live_contact
resolved = _resolve_whatsapp_live_contact("CONTACT_NAME_HERE")
print("resolved" if isinstance(resolved, str) and resolved else resolved)
PY
```

5. If contact sync is still empty after pairing, avoid forced startup sync. Investigate a non-blocking, bounded app-state contact snapshot or a safer Baileys contact source.
