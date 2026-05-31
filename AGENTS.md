# Agent Guidance

## Repository Purpose

This repository contains the Simple CRM tutorial app for dbzero plus NiceGUI.
It is the first hands-on tutorial app for the dbzero community-growth plan: a
small, useful, stateful browser app written in Python without a separate
frontend build, REST API, ORM, cache service, migration framework, or database
server.

The app should teach this core idea:

> NiceGUI gives you the browser UI in Python, and dbzero gives your Python
> objects durable state. Together, a useful internal tool can start as one small
> Python app.

This guide is self-contained. Do not require future contributors or agents to
read another local repository before they can implement, test, or document this
app.

## Product Scope

Simple CRM is a lightweight relationship tracker for companies, contacts,
notes, tasks, and tags.

The first complete app must support one practical follow-up loop:

1. Add a company and contact.
2. Record a note from a conversation.
3. Create a dated follow-up task.
4. See the contact in open-task or overdue-task views.
5. Complete the follow-up task.
6. See last-touch, next-follow-up, and task metrics update.
7. Restart the app and keep the full history.

Keep the app beginner-friendly and tutorial-readable. It should feel like a
real internal tool for a consultant, founder, agency, or small team, but it is
not a full sales platform.

Do not add auth, multi-tenancy, live AI calls, STATEK, db0-rpc, email/calendar
integrations, file uploads, background workers, deployment automation, complex
reporting, or custom CSS-heavy visual design.

The first version should include:

- Add company form with name, industry, and website.
- Add contact form with name, email, title, company, relationship status, and
  comma-separated tags.
- Contact list showing name, company, title, status, tags, last note date, next
  open task due date, open task count, and updated time.
- Detail panel for selected contact basics, status, tags, notes, and tasks.
- Actions to update basics, change status, add a note, add a follow-up task,
  complete or reopen a task, and archive a contact.
- Filters for search text, company, tag, status, open tasks, and overdue tasks.
- Metrics for companies, contacts, active customers, leads, open tasks, and
  overdue tasks.
- Sample data so the app is useful immediately after launch.
- Optional activity checkpoints that record a label, timestamp, and current
  counts.

Use these relationship statuses unless a later task deliberately changes them:

```python
CONTACT_STATUSES = [
    "lead",
    "prospect",
    "active_customer",
    "partner",
    "inactive",
    "archived",
]
```

## Development Commands

Project tooling should stay small. Once the scaffold exists, prefer commands
like these:

```bash
# Install dependencies
python -m pip install -e ".[dev]"

# Run tests
python -m pytest -q

# Run a focused test
python -m pytest tests/test_contact_tasks.py -q

# Start the app
python app.py --host 0.0.0.0 --port 8081
```

If wrappers such as `run_tests.sh`, `run_lint.sh`, or `run_app.sh` are added
later, document and use them here. If commands cannot run in the current
environment, state the reason clearly in the final handoff.

## Architecture Target

Keep the repo layout compact:

```text
simple-crm/
  AGENTS.md
  README.md
  pyproject.toml
  app.py
  simple_crm/
    __init__.py
    config.py
    models.py
    seed.py
  tests/
    conftest.py
    test_contact_tasks.py
    test_contact_search_filters.py
```

The app should open directly to the working CRM. Avoid a landing page.

Use these stack defaults unless a newer local compatibility issue proves
otherwise:

- Python 3.11+
- `dbzero==0.3.3` as the current latest observed version; `dbzero==0.3.2` is an
  acceptable floor if compatibility requires it
- NiceGUI, using a current compatible release
- pytest for focused domain tests

All durable application state must be reachable from one explicit root
singleton named `CRM`.

The model surface should stay small:

- `CRM`: root singleton, indexes, app workflows, search/filtering, counts, and
  checkpoints.
- `Company`: name, industry, website, created time, updated time.
- `Contact`: name, email, title, company reference, status, tags, notes, tasks,
  archived flag, created time, updated time.
- `Note`: body and created time.
- `Task`: title, optional due date, completed flag, created time, completed
  time.
- `CRMCheckpoint`: label, created time, and count snapshot.

## dbzero Guidance

Import dbzero as `db0`:

```python
import dbzero as db0
```

Use memo classes for durable objects:

```python
@db0.memo(prefix=DATA_PREFIX)
@dataclass
class Contact:
    name: str
```

Use one durable root:

```python
@db0.memo(prefix=DATA_PREFIX, singleton=True)
@dataclass
class CRM:
    contacts_by_status: dict[str, list[Contact]] = field(default_factory=dict)
    contacts_by_next_task_date: db0.index = field(default_factory=db0.index)
```

Recommended data prefix:

```python
DATA_PREFIX = "/dbzero/simple-crm/dev/data"
```

Recommended local dbzero root:

```text
.dbzero/
```

Follow these modeling rules:

- `CRM` is the only app root/singleton.
- All companies, contacts, indexes, checkpoints, and workflow methods are
  reachable through `CRM`.
- Use direct Python object references for relationships, such as
  `Contact.company`.
- Use dictionaries for string-key retrieval paths such as company name, status,
  and tag. dbzero 0.3.3 indexes do not support string keys.
- Use `db0.index` for supported sortable key types such as date and datetime,
  for example next task due date and checkpoint creation time.
- Do not model the app primarily as one top-level insertion-ordered list.
- Use lists only when order is the point, such as `Contact.notes` and
  `Contact.tasks`.
- Use sets for unique unordered labels such as contact tags.
- Use dicts for string-key lookup tables and small keyed metadata such as
  checkpoint counts.
- Keep mutation logic on domain methods, not scattered across UI handlers.

Lookup tables and indexes should be maintained inside domain methods. For
example, changing a contact's status should remove the old status entry and add
the new one in the same method that updates the status.

Prefer native dbzero query/index composition when possible:

```python
db0.find(Contact)
db0.find(Contact, "tag")
db0.find(Contact, ["lead", "customer"])
db0.find(Contact, db0.no("archived"))
ix.select(low, high)
ix.sort(query)
```

Push filtering into dictionaries, dbzero indexes, and queries where practical.
Use Python filtering only for predicates that do not have a lookup structure,
such as small text search across note bodies in this tutorial app.

Rely on dbzero autocommit unless current dbzero docs or local tests show a
different recommendation. Do not sprinkle `db0.commit()` through UI event
handlers. Always close dbzero on app shutdown.

Use tags sparingly and intentionally if needed:

```python
db0.tags(obj).add("TAG")
db0.tags(obj).add(["A", "B"])
db0.tags(obj).remove("TAG")
db0.tags(obj) -= ["A", "B"]
```

Avoid `db0.filter` when an index or native `db0.find` query can express the
same constraint. It scans in Python and bypasses the dbzero query engine.

## NiceGUI Guidance

The UI should be compact and practical, not a marketing page.

Use this structure:

- Top bar: app name, search box, seed sample data button, checkpoint button.
- Left column: add company form, add contact form, filters.
- Main column: metric row and contact list.
- Right panel or drawer: selected contact details, relationship status, tags,
  notes, tasks, and actions.

NiceGUI event handlers should be short:

- validate input
- call a `CRM` or domain object method
- refresh the affected UI containers
- notify the user when useful

Do not put durable business rules in UI callbacks when they belong on the
model. Do not add a REST API layer between NiceGUI and the Python objects.

Use visual cues sparingly:

- open tasks: amber
- overdue tasks: red
- completed tasks: green
- selected contact: clear row highlight
- tags: compact chips

Avoid large hero sections, decorative cards, nested cards, custom CSS-heavy
layouts, and explanatory in-app tutorial copy.

The README and tutorial docs can explain the stack. The app UI itself should
focus on doing CRM work.

## Sample Data

Seed data should include 4-6 companies and 12-18 contacts with mixed statuses,
tags, notes, open tasks, completed tasks, and overdue tasks.

Suggested companies:

- Northstar Analytics
- Harbor Clinic
- Circuit Supply
- Meadow Foods
- Atlas Legal

Suggested tags:

- `lead`
- `customer`
- `partner`
- `prospect`
- `renewal`
- `technical`
- `finance`
- `needs-follow-up`

Suggested tasks:

- Send pricing follow-up
- Schedule technical review
- Confirm renewal date
- Share implementation notes
- Check contract status
- Send recap from discovery call
- Follow up after trial period

## Testing Guidance

Default to TDD for backend/domain behavior:

1. Write or update the smallest test that proves the expected behavior.
2. Run the test and confirm it fails for the expected reason.
3. Implement the minimum production change required.
4. Re-run the focused test, then the broader relevant suite.

Tests should initialize dbzero in a temporary directory and close it after each
test. Do not share the app's `.dbzero/` data with tests.

Required early test coverage:

- adding a company and contact
- adding a note
- adding a dated follow-up task
- finding open and overdue tasks
- completing and reopening a task
- status, company, tag, task-state, and text search filters
- persistence-sensitive behavior around the singleton root and indexes

Do not weaken assertions to make tests pass. If TDD is genuinely impractical
for a UI-only change, say why and still add regression coverage where it
matters.

Before finalizing implementation work, run the focused tests for changed
behavior and then the full test suite. Run linting or formatting checks once the
project defines them.

## Documentation Guidance

The README should include:

- one-command setup and run
- screenshot or GIF once the UI exists
- what the app does
- what files to inspect first
- which class is the root/singleton object and how it is opened
- how persistence works
- where the `.dbzero/` data lives
- how to reset sample data
- what this tutorial intentionally leaves out
- why the follow-up workflow is useful
- caveats about when a separate frontend, API, relational database, or queue is
  still appropriate

Use this stack comparison when helpful:

| Common internal-tool layer | Simple CRM tutorial |
| --- | --- |
| React/Vue/Svelte frontend | NiceGUI components in Python |
| REST API routes | NiceGUI event handlers |
| Request/response DTOs | Direct Python method calls |
| ORM models and query builders | dbzero-backed Python objects, references, dict lookups, and indexes |
| Database server | Embedded `.dbzero/` state |
| Manual cache layer | dbzero caching behavior |
| Separate audit subsystem | Optional checkpoint preview |

Do not imply this stack is right for every app. Explicit APIs, relational
databases, external queues, and separate frontends are still appropriate for
many systems.

## Code Quality

- Read the relevant code before editing.
- Prefer the smallest coherent patch that fully solves the task.
- Preserve tutorial readability over clever abstractions.
- Keep functions explicit and short.
- Add comments only for non-obvious reasoning or edge cases.
- Use clear names that a new dbzero/NiceGUI reader can follow.
- Keep assumptions narrow and visible in final handoffs.
- Do not introduce speculative production features.
- Do not revert unrelated user changes in a dirty worktree.

For public-facing docs and README content:

- Say what dbzero reduces or avoids, not that it replaces every database.
- Include caveats and "when not to use this" notes.
- Prefer runnable proof, screenshots, and short code excerpts over broad claims.
- Avoid hype-heavy performance or reliability claims unless measured in this
  repo.

## Acceptance Criteria

The tutorial app is ready when:

- a reader can run it in under 10 minutes
- it starts as a working browser app
- it exposes a single durable `CRM` root object
- it persists companies, contacts, notes, and tasks across restart
- task and note changes are made through Python object methods
- core contact retrieval uses dict lookups and supported indexes, not a single insertion-ordered list
- list, set, and dict are used only where their semantics fit
- search, filtering, and metrics work
- contact rows show last touch, next follow-up, and open task count
- overdue follow-up tasks are visible
- sample data is available
- README explains the simplified stack and caveats
- STATEK and db0-rpc are not included or required
