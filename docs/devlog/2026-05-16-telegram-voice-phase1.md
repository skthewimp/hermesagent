# 2026-05-16 - Telegram Voice Capture Phase 1

## Summary

Added a Phase 1 Telegram voice-note path for this Hermes deployment. Voice notes are captured, downloaded to `/tmp`, transcribed with OpenAI, parsed into structured intent JSON, and replied to in Telegram without executing reminders, tasks, calendar actions, or any other workflow.

## Changes

- Added Telegram `message.voice` interception before the normal Hermes agent pipeline.
- Added `/tmp` voice download and cleanup.
- Added OpenAI transcription using `gpt-4o-mini-transcribe`.
- Added transcript parsing into:
  - `type`
  - `task`
  - `time`
  - `people`
  - `places`
  - `confidence`
- Added Telegram reply formatting with the Phase 1 notice.
- Added graceful missing-`OPENAI_API_KEY` handling.
- Preserved non-voice Telegram media handling.

## Validation

Commands run:

```bash
/home/karthik/.hermes/hermes-agent/venv/bin/python -m py_compile gateway/platforms/telegram.py
/home/karthik/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/test_config.py
/home/karthik/.hermes/hermes-agent/venv/bin/python -m pytest tests/gateway/test_telegram_caption_merge.py tests/gateway/test_telegram_reply_mode.py tests/gateway/test_telegram_text_batch_perf.py
/home/karthik/.hermes/hermes-agent/venv/bin/python -m ruff check gateway/platforms/telegram.py
```

Results:

- `py_compile`: passed
- `tests/gateway/test_config.py`: 48 passed
- Telegram-focused tests: 55 passed
- `ruff`: passed

## Operations

Restart Hermes after setting `OPENAI_API_KEY`:

```bash
pm2 restart hermes --update-env
pm2 logs hermes --lines 100
```

## 2026-05-16 Configuration Update

Configured `OPENAI_API_KEY` in `/home/karthik/.hermes/.env` for the running server. Verified Hermes config loading sees the key without recording the secret value in this devlog.

## 2026-05-16 Phase 1.5 Confirmation Loop

Added Telegram inline-button confirmation for parsed voice notes. Parsed voice payloads are stored in memory for 15 minutes and scoped to Telegram user id plus chat id. The buttons currently support:

- Create Reminder: acknowledges that reminder execution is not enabled yet.
- Edit: asks for corrected text; the next text message from that user/chat is parsed again and shown with fresh confirmation buttons.
- Cancel: clears the pending action.

This phase still does not execute reminders, tasks, or calendar events.

## 2026-05-16 Gmail Drafting Integration

Started outbound Gmail support for the voice operating system direction:

- Added `draft_email` voice intent parsing.
- Added LLM email drafting with practical, conversational tone.
- Added Telegram draft approval buttons: Send, Edit, Cancel.
- Added SQLite persistence in `~/.hermes/email_actions.sqlite3`.
- Added `/draft_emails` to list recent email actions.
- Added Gmail OAuth/token helper using the official Gmail API Python client stack.

Voice never sends immediately. Gmail sending only happens after tapping Send, and only after OAuth is configured.
