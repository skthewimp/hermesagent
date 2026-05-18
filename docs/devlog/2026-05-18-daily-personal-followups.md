# 2026-05-18 - Daily Personal Follow-Ups

## Summary

Added the first Hermes-native version of the personal follow-up workflow inspired by the older `job-crm` project.

The target user flow is:

```text
09:00 IST -> Hermes scans recent Gmail + WhatsApp -> Telegram daily follow-up todos
Telegram feedback -> "done" / "don't want to reply" / "snooze" -> item state updates
```

This is intentionally not a direct port of `job-crm`. The old app is a Node/CommonJS job-search CRM built around companies, contacts, Google Sheets, summary email, and email-reply feedback. Hermes already has the useful runtime primitives: Telegram delivery, cron, Gmail IMAP access, WhatsApp bridge access, and tool routing.

## Product Intent

The workflow is for the post-job-hunt mode where the user is not tracking applications, but still wants help avoiding missed replies and follow-ups.

V1 goals:

- Build a daily Telegram todo digest.
- Inspect the previous week of Gmail and WhatsApp.
- Consider both incoming and outgoing messages.
- Detect likely replies owed, promises made by the user, and waiting-on-them states.
- Let Telegram feedback suppress or update items so stale todos do not recur.

LinkedIn is deferred. The old `job-crm` LinkedIn scanner uses Puppeteer plus browser cookies, which is useful as prior art but brittle enough that it should be a separate source integration rather than part of this first reliable daily loop.

## User-Facing Behavior

New messaging tool:

```text
personal_followups
```

Daily digest action:

```json
{"action": "digest"}
```

The digest returns short action bullets:

```text
Daily follow-ups

Waiting on you
1. [F-12] Asha via WhatsApp
   Action: Reply or decide no reply is needed.
   Why: Looks like they asked for a response or action. Can you send me the notes?

Waiting on others
- [F-13] Dev via email: Draft
  Note: Any update on the draft?
```

Feedback examples:

- `done F-12`
- `I don't want to reply to F-12`
- `snooze F-12 until tomorrow`
- `F-12 is waiting on them`
- `note F-12 replied on call`

If the most recent digest had exactly one active item, item id can be omitted.

## State Model

State is stored in SQLite:

```text
/home/karthik/.hermes/personal_followups.sqlite3
```

Main tables:

- `source_messages`: normalized Gmail and WhatsApp messages, keyed by source id.
- `attention_items`: deduped follow-up candidates with status and suppression metadata.
- `item_messages`: links items back to source messages.
- `feedback_events`: raw feedback audit log.
- `meta`: schema version and last digest item ids.

Statuses:

- `active`: waiting on the user.
- `waiting`: waiting on someone else.
- `snoozed`: hidden until `suppress_until`.
- `done`: completed by user feedback.
- `dismissed`: suppressed because no reply/follow-up is wanted.

Default dismissal scope is item-level. Saying `I don't want to reply` dismisses that specific follow-up, not the whole contact or thread.

## Source Handling

Gmail uses the existing IMAP configuration:

- `EMAIL_ADDRESS`
- `EMAIL_PASSWORD`
- `EMAIL_IMAP_HOST`
- `EMAIL_IMAP_PORT`

The scanner reads `INBOX` plus one detected sent mailbox when available. It fetches with `BODY.PEEK[]` and skips automated incoming senders.

WhatsApp uses the local bridge observed-message endpoint:

```text
GET http://127.0.0.1:3000/observed?direction=all&limit=N
```

The bridge observed buffer is still in-memory, but the new tool persists every observed message it sees into SQLite. That makes follow-up state durable after the first successful digest pass.

## Extraction Heuristics

V1 extraction is deterministic rather than model-based. It looks for:

- incoming asks: `can you`, `please`, `reply`, `let me know`, questions, and similar phrases
- outgoing commitments: `I'll`, `I will`, `will send`, `get back`, `follow up`, date-ish phrases
- outgoing waits: `any update`, `can you`, `let me know`, questions, and similar phrases

This keeps the scheduled job predictable and easy to test. The Telegram-facing Hermes model can still interpret the digest and feedback naturally.

## Implementation

New file:

```text
tools/personal_followups_tool.py
```

Registered in the `messaging` toolset and added to the shared Hermes core tool list:

```text
send_message
whatsapp
inbound_catchup
personal_followups
```

Daily cron wrapper:

```text
scripts/daily_personal_followups.py
/home/karthik/.hermes/scripts/daily_personal_followups.py
```

The tracked copy lives in `scripts/`. The installed runtime copy lives under `/home/karthik/.hermes/scripts/`, because Hermes cron only executes scripts from `HERMES_HOME/scripts`. The wrapper loads `/home/karthik/.hermes/.env`, imports the Hermes tool module, runs `personal_followups_tool({"action": "digest"})`, and prints only the digest summary. The cron job should run it in `--no-agent` mode and deliver stdout to Telegram. This avoids scheduled-agent tool restrictions while keeping the interactive Telegram feedback path available through the normal `messaging` toolset.

Installed cron job:

```text
id: ef407b713d26
name: daily_personal_followups
schedule: 0 9 * * *
deliver: telegram
script: daily_personal_followups.py
mode: no-agent
next run: 2026-05-19T09:00:00+05:30
```

Tool actions:

- `digest`: scan, persist, extract, dedupe, and render the daily summary.
- `feedback`: apply natural-language state changes to an item.
- `list`: inspect current items.
- `status`: inspect database path and counts.
- `reset`: delete the local follow-up database.

## Validation

Focused tests:

```bash
/home/karthik/apps/hermes/venv/bin/python -m pytest tests/tools/test_personal_followups_tool.py tests/tools/test_inbound_catchup_tool.py
/home/karthik/apps/hermes/venv/bin/python -m pytest tests/tools/test_personal_followups_tool.py tests/tools/test_inbound_catchup_tool.py tests/tools/test_registry.py
```

Result:

```text
6 passed
37 passed
```

Coverage:

- digest creates WhatsApp/email action items
- repeated digest dedupes existing items
- item-level dismiss feedback removes active item
- explicit-id snooze feedback updates the selected item
- existing inbound catch-up behavior still passes

## Next Steps

- Add LinkedIn as a separate optional source once the auth/session story is acceptable.
- Consider model-assisted extraction after deterministic v1 has real daily examples.
- Persist WhatsApp bridge observations directly at the bridge layer if longer history is needed across periods when the digest does not run.
