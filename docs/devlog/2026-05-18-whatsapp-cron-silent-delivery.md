# 2026-05-18 - WhatsApp Cron Silent Delivery

## Summary

Debugged a scheduled WhatsApp message that was expected at 17:00 IST but did not appear in WhatsApp.

The cron job did run. It was not a timezone miss.

Observed job:

```text
id: b3569610aa03
name: send_whatsapp_hari_balaji
schedule: once at 2026-05-18 17:00 IST
run time: 2026-05-18 17:00:10 IST
output: ~/.hermes/cron/output/b3569610aa03/2026-05-18_17-00-10.md
```

The saved cron output showed the future cron agent responded with:

```text
[SILENT]
```

Hermes treats `[SILENT]` as an intentional suppression marker for successful cron jobs, so delivery was skipped and the one-shot job was consumed.

## Root Cause

The job prompt was effectively a short literal WhatsApp message body:

```text
trying to build some cool whatsapp tools on hermes
```

But because the future cron run still went through the LLM, the scheduler's generic cron prompt included guidance that says `[SILENT]` may be used when there is nothing to report. The model incorrectly treated the direct message body as non-report content and returned `[SILENT]`.

This is a product footgun for direct-message cron jobs:

- the user intended "send this literal text later"
- the scheduled agent interpreted the prompt as an autonomous reporting task
- `[SILENT]` suppressed delivery

## Fix

Added a narrow guard in:

```text
tools/cronjob_tools.py
```

If a cron job has an explicit WhatsApp delivery target such as:

```text
deliver="whatsapp:..."
```

and the prompt looks like a short literal message body, Hermes now rewrites the prompt at create time to:

```text
Output exactly this text and nothing else:
...
```

The guard is intentionally conservative. Report-style prompts such as "summarize HN and report the top AI stories" are not rewritten, so WhatsApp can still be used as a delivery destination for scheduled reports.

## Tests

Added regression coverage in:

```text
tests/tools/test_cronjob_tools.py
```

Coverage:

- explicit WhatsApp delivery plus short literal prompt is wrapped as exact output
- explicit WhatsApp delivery plus report-style prompt is not wrapped

Validation run:

```text
/home/karthik/apps/hermes/venv/bin/python -m pytest tests/tools/test_cronjob_tools.py -q
/home/karthik/apps/hermes/venv/bin/python -m ruff check tools/cronjob_tools.py tests/tools/test_cronjob_tools.py
```

Result:

```text
57 passed
ruff: all checks passed
```

## Runtime Caveat

After restarting Hermes to load the fix, the gateway was online but WhatsApp delivery was still unavailable:

```text
curl http://127.0.0.1:3000/health
failed to connect to 127.0.0.1 port 3000
```

Recent gateway logs showed:

```text
[Whatsapp] Bridge HTTP server did not start in 15s
[Whatsapp] Poll error: Cannot connect to host 127.0.0.1:3000
```

So there are two distinct issues:

1. The 17:00 job itself was suppressed by `[SILENT]`. This is fixed for future literal WhatsApp cron jobs.
2. WhatsApp bridge reconnect/re-pair reliability is still an operational blocker for scheduled WhatsApp delivery.

Safe next operational step:

```text
hermes whatsapp
```

If it asks to re-pair, scan the QR from WhatsApp:

```text
Settings -> Linked Devices -> Link a Device
```

Then restart the gateway:

```text
pm2 restart hermes --update-env
```
