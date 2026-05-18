# Timezone, Reminders, and Runtime Handoff - 2026-05-18

## User Preference

If the user gives a time without an explicit timezone, interpret it in the user's current timezone.

Current user timezone:

```text
Asia/Kolkata
IST
UTC+05:30
```

This is intended to apply especially to reminders, scheduled WhatsApp sends, and any other natural-language scheduling request.

Examples:

- "remind me at 8" means 8:00 IST.
- "send this at 5pm" means 17:00 IST.
- Do not silently convert a timezone-less wall-clock time to UTC.
- Only use another timezone when the user explicitly states one.

## Configuration Change

Hermes profile configuration was updated outside the repo:

```text
~/.hermes/config.yaml
```

The effective timezone is now:

```yaml
timezone: Asia/Kolkata
```

This was verified with:

```bash
/home/karthik/.hermes/hermes-agent/venv/bin/python -c "import hermes_time; print(hermes_time.get_timezone()); print(hermes_time.now().isoformat())"
```

Expected output shape:

```text
Asia/Kolkata
2026-05-18T...+05:30
```

## Code Changes

Commit pushed to `origin/main`:

```text
3c6e6d692 fix: preserve configured timezone for schedules
```

Changed files:

- `run_agent.py`
- `tools/cronjob_tools.py`

### `run_agent.py`

The conversation-start timestamp now includes the timezone abbreviation from `hermes_time.now()`.

This gives the model an explicit runtime clue such as:

```text
Conversation started: Monday, May 18, 2026 03:52 PM IST
```

Purpose:

- Avoid ambiguity when the user says "today", "tomorrow", "at 8", "at 5pm", etc.
- Make the configured Hermes timezone visible in the agent's active prompt context.

### `tools/cronjob_tools.py`

The cron tool schema now instructs the model to preserve timezone-less wall-clock schedules in the configured Hermes timezone.

The key behavior is:

- Prefer human schedule strings like `at 2pm today`.
- If the user did not state a timezone, keep the time as a local wall-clock time.
- Do not pre-convert unspecified times to UTC.
- Include an explicit timezone only when the user stated one.

This is a model/tool-contract guardrail. The underlying scheduler still stores concrete `next_run_at` values with offsets once parsed.

## Existing Jobs Corrected

The existing cron jobs in:

```text
~/.hermes/cron/jobs.json
```

were corrected from UTC interpretations to IST wall-clock interpretations.

Current expected job summary after correction:

```text
b3569610aa03 once at 2026-05-18 17:00 IST 2026-05-18T17:00:00+05:30 whatsapp:Hari Balaji scheduled
f9b7db23bf87 once at 2026-05-18 19:50 IST 2026-05-18T19:50:00+05:30 origin scheduled
```

Use this command to inspect without dumping private message bodies:

```bash
/home/karthik/.hermes/hermes-agent/venv/bin/python -c "import json,pathlib; data=json.loads(pathlib.Path('/home/karthik/.hermes/cron/jobs.json').read_text()); [print(j.get('id'), j.get('schedule_display'), j.get('next_run_at'), j.get('deliver'), j.get('state')) for j in data.get('jobs', [])]"
```

Privacy note:

- Do not paste full job prompts into logs or commits unless the user asks.
- Job metadata is okay to inspect, but message bodies and contact details should be minimized.

## Verification Run

These checks passed before the commit:

```bash
/home/karthik/.hermes/hermes-agent/venv/bin/python -m ruff check tools/cronjob_tools.py run_agent.py
/home/karthik/.hermes/hermes-agent/venv/bin/python -m pytest tests/cron/test_jobs.py tests/test_timezone.py -q
git diff --check
```

Focused test result:

```text
102 passed
```

## Runtime State

Hermes was restarted under PM2 after the timezone changes:

```bash
pm2 restart hermes --update-env
```

Current service shape:

```text
PM2 process name: hermes
PM2 id: 0
Command: /home/karthik/apps/hermes/venv/bin/hermes gateway run --replace
Working directory: /home/karthik/apps/hermes
```

At the end of this handoff:

- Hermes gateway process was online.
- Telegram connected.
- Cron ticker started and was active.
- Email was failing due network reachability in this runtime context.
- WhatsApp was failing to reconnect after restart.

Important operational caveat:

The 17:00 IST scheduled job delivers via WhatsApp. If WhatsApp is not connected before that time, delivery may fail.

## WhatsApp Runtime Caveat

After restarting Hermes, WhatsApp repeatedly timed out during reconnect. A bridge process was observed pinning CPU near 100%, was killed, and Hermes was restarted cleanly. The clean restart still produced:

```text
whatsapp failed to connect
whatsapp connect timed out after 30s
```

Do not print full WhatsApp bridge logs or session files. They can contain sensitive session/contact data.

Useful safe checks:

```bash
pm2 describe hermes
tail -50 /home/karthik/.pm2/logs/hermes-error.log
```

When inspecting logs, keep output short and avoid dumping:

- `~/.hermes/whatsapp/session`
- full `bridge.log`
- contact cache contents
- phone numbers
- WhatsApp message bodies

Likely next step if WhatsApp remains disconnected:

```bash
hermes whatsapp
```

If it asks to re-pair and the user agrees, scan the QR from WhatsApp:

```text
Settings -> Linked Devices -> Link a Device
```

Then restart the gateway:

```bash
pm2 restart hermes --update-env
```

## Git State At Handoff

After the timezone fix:

```text
main -> origin/main
latest pushed commit: 3c6e6d692
repo clean before this devlog entry
```

This devlog entry replaces the older WhatsApp tool-mode handoff. The old handoff was intentionally removed because the user asked to clear stale handoffs before clearing the conversation.

## Resume Checklist

After clearing conversation context, start here:

1. Confirm profile timezone:

```bash
/home/karthik/.hermes/hermes-agent/venv/bin/python -c "import hermes_time; print(hermes_time.get_timezone()); print(hermes_time.now().isoformat())"
```

2. Confirm cron jobs are still IST:

```bash
/home/karthik/.hermes/hermes-agent/venv/bin/python -c "import json,pathlib; data=json.loads(pathlib.Path('/home/karthik/.hermes/cron/jobs.json').read_text()); [print(j.get('id'), j.get('schedule_display'), j.get('next_run_at'), j.get('deliver'), j.get('state')) for j in data.get('jobs', [])]"
```

3. Confirm Hermes is online:

```bash
pm2 describe hermes
```

4. Check WhatsApp status without dumping sensitive data:

```bash
tail -50 /home/karthik/.pm2/logs/hermes-error.log
```

5. If WhatsApp is disconnected and a WhatsApp delivery is due soon, prioritize reconnecting WhatsApp before doing more repo work.
