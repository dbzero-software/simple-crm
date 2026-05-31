# Simple CRM

Simple CRM is a small tutorial app for building a persistent Python internal
tool with dbzero and NiceGUI.

The current implementation contains the durable CRM domain model, sample data,
tests, and a compact NiceGUI interface.

## What The App Does

Simple CRM tracks companies, contacts, notes, tags, and follow-up tasks. It is
small on purpose: the goal is to show how a useful internal tool can keep
durable state with Python objects instead of adding a frontend build, REST API,
ORM, cache service, migration framework, or separate database server.

The core workflow is:

1. Add a company and contact.
2. Record a note from a conversation.
3. Create a dated follow-up task.
4. See the contact in open-task or overdue-task views.
5. Complete or reopen the task.
6. Restart the app and keep the CRM history.

## Setup And Run

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python app.py --host 0.0.0.0 --port 8081
```

Open `http://localhost:8081`, then use **Seed data** to populate example
companies, contacts, notes, and tasks.

## Files To Inspect First

- `app.py`: NiceGUI entrypoint and UI event handlers.
- `simple_crm/models.py`: durable CRM objects and workflow methods.
- `simple_crm/seed.py`: idempotent sample data.
- `tests/`: domain, app startup, and browser smoke coverage.

## Durable Root And Persistence

The root object is `CRM` in `simple_crm/models.py`. It is decorated as the only
dbzero singleton root, and all durable app state is reachable from it:

- companies
- contacts
- lookup dictionaries
- date/datetime indexes
- checkpoints

The app opens dbzero in `app.py` with:

```python
db0.init(".dbzero", prefix="/dbzero/simple-crm/dev/data", autocommit=True)
crm = CRM()
```

Local durable app data lives under `.dbzero/`. To reset local app state, stop
the app and remove that directory:

```bash
rm -rf .dbzero
```

Tests use temporary dbzero roots, so they do not read or modify local app data.

## What Works

- Add companies and contacts.
- Seed sample CRM data.
- Filter contacts by company, status, tag, open tasks, overdue tasks, and text.
- Add notes and follow-up tasks.
- Complete and reopen tasks.
- Archive contacts.
- Create lightweight count checkpoints.

## Seed Data

The **Seed data** button creates five companies and twelve contacts with mixed
statuses, tags, notes, open tasks, completed tasks, and overdue tasks. The seed
operation is idempotent by sample contact email: pressing the button again
reuses existing records instead of duplicating the demo CRM.

## Stack Comparison

| Common internal-tool layer | Simple CRM tutorial |
| --- | --- |
| React/Vue/Svelte frontend | NiceGUI components in Python |
| REST API routes | NiceGUI event handlers |
| Request/response DTOs | Direct Python method calls |
| ORM models and query builders | dbzero-backed Python objects, references, dict lookups, and indexes |
| Database server | Embedded `.dbzero/` state |
| Manual cache layer | dbzero caching behavior |
| Separate audit subsystem | Lightweight checkpoint preview |

This is not the right stack for every app. Separate frontends, explicit APIs,
relational databases, queues, and deployment automation are still appropriate
for many systems. This tutorial focuses on small Python-first internal tools
where fewer layers make the app easier to build and inspect.

## Browser Verification

The dev test suite includes a Playwright smoke test for the browser workflow.
It starts the app with an isolated temporary `.dbzero` root, seeds data, opens a
contact, adds a note and task, and completes/reopens the task.

If the local machine is missing Chromium system libraries, pytest skips only
that browser test and reports the missing dependency. On a fully provisioned
machine, `python -m pytest -q` runs it with the rest of the suite.
