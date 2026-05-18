# 2026-05-18 - On-Demand Inbound Catch-Up

## Summary

Added an on-demand inbound catch-up workflow for this Hermes deployment. The target user flow is:

```text
Telegram -> "catch me up on my inbounds" -> Hermes summarizes WhatsApp + Gmail since the last catch-up
```

This replaces the earlier hourly-summary idea. The user keeps WhatsApp and email notifications off while focusing, but can ask Hermes for a controlled catch-up when they choose.

## Product Intent

The workflow is designed around focused work:

- WhatsApp and email can stay closed or notification-muted.
- Outbound sending remains available through Hermes tools.
- Inbound review is pull-based, not push-based.
- The catch-up window is stateful: every successful catch-up advances a checkpoint.
- The next catch-up starts from the previous checkpoint, so the user does not reread old inbounds.

## User-Facing Behavior

From Telegram, the user can say natural phrases such as:

- `catch me up on my inbounds`
- `what did I miss`
- `summarize my inbound messages`
- `catch me up on WhatsApp and email`

The model now has a dedicated `inbound_catchup` tool in the `messaging` toolset. The tool returns a compact plain-text summary and structured counts. The model can then send the summary back in the normal Telegram reply.

## Checkpoint Semantics

State is stored at:

```text
/home/karthik/.hermes/inbound_catchup_state.json
```

Current schema:

```json
{
  "version": 1,
  "last_catchup_at": "2026-05-18T11:03:55.667472Z"
}
```

Rules:

- `action="catch_up"` reads from `last_catchup_at` through current UTC time.
- If there is no checkpoint, the tool falls back to a bounded lookback window.
- Default fallback lookback is 24 hours.
- Maximum fallback lookback is 168 hours.
- By default, `catch_up` advances the checkpoint after collecting/rendering the summary.
- `advance_checkpoint=false` allows dry-run validation without changing state.
- `action="status"` reports the checkpoint and state-file path.
- `action="reset"` sets the checkpoint to now.

The initial baseline was intentionally set to the setup time, `2026-05-18T11:03:55.667472Z` (`16:33:55 IST`), so the first real Telegram catch-up does not dump older setup/testing history.

## WhatsApp Source

WhatsApp catch-up reads from the local Baileys bridge endpoint:

```text
GET http://127.0.0.1:3000/observed?direction=incoming&limit=N
```

This relies on the existing bridge setting:

```text
WHATSAPP_TOOL_ONLY=true
```

That mode is important. It means observed WhatsApp messages remain available for tools, but they are not pushed into Hermes as normal active chat input. This matches the focused-work requirement: inbound messages are observable, but not interruptive.

Only incoming observed messages inside the checkpoint window are included. Outgoing/self messages are excluded from catch-up summaries.

Operational note: the observed WhatsApp buffer is in-memory in the Node bridge. It survives normal Hermes agent turns, but not a bridge process restart. This is acceptable for the current pull-based focus workflow, but a future persistent WhatsApp observation store would make catch-up robust across bridge restarts.

## Email Source

Email catch-up reads Gmail through IMAP on demand. It does not depend on enabling the always-on Hermes email adapter as a chat platform.

The tool uses:

- `EMAIL_ADDRESS`
- `EMAIL_PASSWORD`
- `EMAIL_IMAP_HOST`
- `EMAIL_IMAP_PORT`

It selects `INBOX` readonly and uses IMAP `SINCE` to narrow candidates, then applies exact timestamp filtering in Python. It fetches messages with `BODY.PEEK[]` so the catch-up operation does not mark messages as read.

Filtering:

- self-sent email is skipped
- automated/noreply/bulk-style senders are skipped using the existing email-platform helper when available
- only messages dated inside the checkpoint window are included

The gateway’s always-on email adapter currently logs SMTP connection failures in this environment, but the new catch-up path is independent of that always-on adapter. A smoke test verified direct Gmail IMAP login succeeds.

## Implementation

New tool:

```text
tools/inbound_catchup_tool.py
```

Registered as:

```python
registry.register(
    name="inbound_catchup",
    toolset="messaging",
    schema=INBOUND_CATCHUP_SCHEMA,
    handler=inbound_catchup_tool,
    max_result_size_chars=40_000,
)
```

Added to the shared core and explicit `messaging` toolset in:

```text
toolsets.py
```

This matters because Telegram is configured with the `messaging` toolset. After this change, a Telegram session sees:

```text
inbound_catchup
send_message
whatsapp
```

## Tool API

Actions:

- `catch_up`: collect and summarize new inbounds since checkpoint
- `status`: show current checkpoint
- `reset`: set checkpoint to current time

Parameters:

- `advance_checkpoint`: default `true`; set `false` for dry runs
- `lookback_hours`: default `24`; used only when no checkpoint exists
- `limit_per_source`: default `100`; max `200`

Return shape:

```json
{
  "success": true,
  "since": "2026-05-18T11:03:55.667472Z",
  "until": "2026-05-18T11:11:50.050334Z",
  "checkpoint_advanced": false,
  "counts": {
    "whatsapp": 0,
    "email": 0
  },
  "summary": "Inbound catch-up since ..."
}
```

## Summary Formatting

The summary renderer intentionally stays deterministic and compact:

- top-level window start/end
- no-message sentence for empty windows
- WhatsApp grouped by sender/chat label
- up to the last three WhatsApp snippets per sender
- email listed by sender and subject
- compact body snippets with whitespace collapsed

This keeps the tool useful even without a second LLM summarization pass. The Telegram-facing model can still rewrite or compress the summary in its final response if useful.

## Validation

Commands run:

```bash
/home/karthik/.hermes/hermes-agent/venv/bin/python -m py_compile tools/inbound_catchup_tool.py toolsets.py
/home/karthik/.hermes/hermes-agent/venv/bin/python -m pytest tests/tools/test_inbound_catchup_tool.py tests/tools/test_registry.py -q
/home/karthik/.hermes/hermes-agent/venv/bin/python -c "from model_tools import get_tool_definitions; names=[t['function']['name'] for t in get_tool_definitions(enabled_toolsets=['messaging'], quiet_mode=True)]; print(names); assert 'inbound_catchup' in names"
```

Results:

- `py_compile`: passed
- focused pytest: `34 passed`
- messaging toolset check: `['inbound_catchup', 'send_message', 'whatsapp']`

Runtime checks:

```bash
pm2 restart hermes --update-env
curl -sS --max-time 3 http://127.0.0.1:3000/health
```

Results:

- Hermes restarted under PM2.
- WhatsApp bridge health returned `{"status":"connected", ...}`.
- Gmail IMAP smoke test returned `OK` for login/search.
- Non-mutating catch-up smoke test returned success with `checkpoint_advanced=false`.

## Tests Added

```text
tests/tools/test_inbound_catchup_tool.py
```

Coverage:

- checkpoint reset and advancement
- summary includes WhatsApp and email rows
- empty-window summary behavior
- WhatsApp observed-message filtering by timestamp window

## Operational Caveats

- WhatsApp observation is currently in-memory in the bridge. A restart can lose observed messages that have not yet been caught up.
- Email catch-up uses IMAP date headers; messages with malformed dates fall back conservatively.
- The tool intentionally does not mark Gmail messages read.
- The tool intentionally does not send replies or take actions. It only summarizes inbounds and advances catch-up state.
- The always-on email platform adapter may still log SMTP failures separately; that is not required for this on-demand catch-up workflow.

## Future Follow-Ups

Potential next improvements:

- persist WhatsApp observed messages to SQLite for restart-safe catch-up
- add per-source checkpoints if WhatsApp and email should advance independently
- add contact-name enrichment for WhatsApp summaries using the bridge contact cache
- add a slash command or quick command alias for `catch me up on my inbounds`
- add an explicit "do not advance if errors occurred" mode if source failures should be surfaced more strictly
