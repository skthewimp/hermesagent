# Hermes Executive Layer Todo - 2026-05-18

## Direction

Build Hermes into an ambient executive layer:

- Telegram-first capture surface.
- Durable personal memory.
- Reliable reminders, tasks, drafts, and follow-ups.
- Pull-based inbound catch-up instead of noisy notifications.
- Scheduled intelligence routines.
- Later, structured business and KPI monitoring.

Avoid building agent swarms, autonomous businesses, or large dashboards before the core personal loop is excellent.

## Phase 1 - Perfect Ambient Capture

- [ ] Execute confirmed Telegram voice reminders instead of only acknowledging them.
- [ ] Execute confirmed Telegram voice tasks into a durable task store.
- [ ] Execute confirmed Telegram voice memory writes into persistent memory.
- [ ] Finish confirmed Telegram voice Gmail draft/send flow.
- [ ] Add confirmed Telegram voice WhatsApp draft/send flow.
- [ ] Store every voice transcript with timestamp, source chat, parsed intent, and final action.
- [ ] Add `/voice_notes` or equivalent inspection command for recent voice captures.
- [ ] Add tests for voice confirmation actions: reminder, task, memory, email draft, cancel, edit.

## Phase 2 - Durable Memory

- [ ] Create a local SQLite memory/event store.
- [ ] Store extracted facts, decisions, preferences, people, projects, and commitments.
- [ ] Preserve source links back to Telegram voice notes, Gmail messages, WhatsApp messages, or manual entries.
- [ ] Add explicit memory commands: remember, recall, list, edit, delete, forget.
- [ ] Add semantic search over memories and transcripts.
- [ ] Add daily memory digest.
- [ ] Add person profiles for relationship context and open loops.
- [ ] Add project profiles for goals, notes, deadlines, and decisions.

## Phase 3 - Executive OS

- [ ] Add Google Calendar integration.
- [ ] Generate daily agenda brief from calendar, reminders, follow-ups, and memory.
- [ ] Generate meeting prep briefs from calendar attendees, recent emails, WhatsApp history, and memory.
- [ ] Summarize Gmail threads on demand.
- [ ] Draft Gmail replies from Telegram with approval before send.
- [ ] Track "waiting on me" and "waiting on them" across Gmail and WhatsApp.
- [ ] Add end-of-day review: completed items, missed replies, tomorrow's priorities.
- [ ] Add relationship review: stale contacts, promised follow-ups, important open loops.

## Phase 4 - Scheduled Intelligence

- [ ] Keep daily personal follow-ups running at 09:00 IST.
- [ ] Add morning operating brief.
- [ ] Add end-of-day review.
- [ ] Add weekly relationship review.
- [ ] Add AI/data/news briefing.
- [ ] Add HN/RSS summary routine.
- [ ] Add company/person monitoring routine.
- [ ] Add opportunity monitoring routine.
- [ ] Add failure reporting for scheduled jobs when a source is unavailable.

## Phase 5 - Structured Business Layer

- [ ] Define a simple local schema for companies, contacts, projects, opportunities, and notes.
- [ ] Link people and companies to Gmail, WhatsApp, memory, and calendar events.
- [ ] Add lightweight CRM-style queries through Telegram.
- [ ] Add consulting opportunity tracking.
- [ ] Add KPI snapshot ingestion.
- [ ] Add anomaly summaries for structured metrics.
- [ ] Add weekly business review from opportunities, follow-ups, meetings, and KPIs.

## Reliability And Infrastructure

- [ ] Persist WhatsApp bridge observed messages to SQLite so catch-up survives bridge restarts.
- [ ] Add per-source inbound catch-up checkpoints for Gmail and WhatsApp.
- [ ] Add contact-name enrichment for WhatsApp catch-up summaries.
- [ ] Improve WhatsApp reconnect diagnostics without dumping sensitive logs.
- [ ] Add a strict "do not advance checkpoint if source failed" mode for inbound catch-up.
- [ ] Add health summary command for Telegram: gateway, cron, Gmail, WhatsApp, memory DB.
- [ ] Keep timezone-less user scheduling in `Asia/Kolkata` unless the user states another timezone.

## Immediate Next Build

Start with:

1. Confirmed voice reminder execution.
2. Durable task/reminder store.
3. Confirmed voice memory writes.
4. WhatsApp observation persistence.
5. Daily operating brief.

Definition of done for the next milestone:

- A messy Telegram voice note can create a reminder, task, memory, or draft after confirmation.
- The action is persisted.
- Hermes can show what it captured.
- Scheduled reminders fire in IST.
- Catch-up and follow-up workflows keep working after a gateway restart.
