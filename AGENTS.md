# Agent Guidance

This repository is a Python application using dbzero for durable object state and
NiceGUI for the browser UI.

## dbzero Basics

Import dbzero as `db0`:

```python
import dbzero as db0
```

Use `@db0.memo` for durable model classes:

```python
@db0.memo(prefix=DATA_PREFIX)
@dataclass
class Item:
    name: str
```

Use one explicit root singleton for application state and workflow entrypoints:

```python
@db0.memo(prefix=DATA_PREFIX, singleton=True)
@dataclass
class AppState:
    items_by_created_at: db0.index = field(default_factory=db0.index)
```

Initialize dbzero once on app startup, and close it on app shutdown. Keep the
local dbzero storage directory out of tests unless a test deliberately verifies
local persistence.

## Modeling Rules

- Keep durable state reachable from an explicit root singleton.
- Put domain workflows and index/tag maintenance on model/root methods, not in UI callbacks.
- Use direct Python object references for relationships when ownership or navigation is clear.
- Use tags for discovery, grouping, and queryable labels.
- Use `db0.index` for sorted and range-queryable fields with supported key types, such as `int`, `Decimal`, `date`, `datetime`, `time`, and `None`.
- Use dicts for exact string-key lookups and small keyed metadata.
- Use lists only when order is part of the domain, such as ordered child records.
- Use sets for unique unordered labels.
- Do not model retrieval primarily as one large insertion-ordered list if the app needs filtering, lookup, or sorted views.

Maintain derived lookup structures in the same domain method that changes the
source value. For example, when changing an indexed field, remove the old index
entry and add the new one in that method.

## Queries And Filtering

Prefer native dbzero query composition:

```python
db0.find(Item)
db0.find(Item, "tag")
db0.find(Item, "A", "B")
db0.find(Item, ["A", "B"])
db0.find(Item, db0.no("archived"))
db0.find(existing_query, "extra-tag")
```

Use tags and indexes before Python predicates. `db0.filter(...)` scans in
Python and should be reserved for predicates that cannot be represented by tags,
indexes, or `db0.find(...)`.

Do not materialize dbzero query results inside model retrieval methods just to
count, page, filter, or sort:

- Avoid `list(db0.find(...))` in retrieval paths.
- Avoid `sorted(db0.find(...))` in retrieval paths.
- Avoid list comprehensions over dbzero queries when a query, tag, index, or slice can express the operation.

dbzero queries support `len(query)` and slicing, so pagination helpers should
use query length and query slices directly.

Materialization is acceptable at UI boundaries, in tests, and for genuinely
small metadata collections that cannot be represented as a dbzero query.

## Indexes And Sorting

Use `db0.index` for sorted retrieval and range selection:

```python
ix.add(key, obj)
ix.remove(key, obj)
ix.select(low, high)
ix.sort(query)
ix.sort(query, desc=True)
```

The local dbzero API uses the index object's `.sort()` method; do not assume a
top-level `db0.sort(...)` exists.

Sorting is a terminal operation for query composition. Apply all native
`db0.find(...)`, `db0.no(...)`, tag, subquery, and range constraints first, then
sort as the final step.

## Tags

Use tags intentionally and keep tag maintenance close to the mutation:

```python
db0.tags(obj).add("TAG")
db0.tags(obj).add(["A", "B"])
db0.tags(obj).remove("TAG")
db0.tags(obj) -= ["A", "B"]
```

There is no `discard` method. Use `remove` or the subtraction operator.

Object tags can also express relationships for query purposes:

```python
db0.tags(child).add(db0.as_tag(parent))
db0.find(Child, db0.as_tag(parent))
```

## Persistence

Rely on dbzero autocommit unless a task explicitly changes the transaction
model. Do not add explicit `db0.commit()` calls to UI handlers or ordinary
domain methods.

Objects that are no longer strongly referenced are eligible for dbzero garbage
collection after autocommit/close. If a method removes a child object from a
durable parent collection, detach it from the parent and let autocommit persist
the change.

Always call `db0.close()` on application shutdown and in test fixture cleanup.

## NiceGUI Integration

NiceGUI should call the domain layer directly. Do not add an API layer between
NiceGUI event handlers and dbzero-backed Python objects unless the architecture
explicitly requires one.

Keep UI event handlers short:

- read and validate UI values
- call a root/domain method
- refresh only the affected UI containers
- notify the user when useful

Do not scatter durable business rules, tag updates, index updates, or relationship
maintenance across UI callbacks.

Avoid rebuilding the input element currently receiving keyboard focus during its
own `on_change` or value-change handler. Update state and refresh dependent
views instead. Recreate the input only when its mode, label, options, or
surrounding context actually changes.

## UI Refresh Discipline

Prefer small refresh functions for specific containers instead of one broad
refresh for every interaction. Broad refreshes are acceptable after structural
changes, but they should not interfere with active text entry, dialogs, or
selection state.

When rendering query-backed data:

- keep dbzero query retrieval in model/root methods
- paginate before rendering
- materialize only the page or UI-specific collection being displayed
- avoid Python sorting/filtering in the UI when the model can return a query or sorted iterable

## Testing

Use focused tests for domain behavior that changes dbzero state:

- initialize dbzero in a temporary directory
- create the durable root singleton
- exercise root/domain methods rather than UI callbacks
- assert indexes, tags, retrieval methods, and persistence-sensitive behavior
- close dbzero in fixture cleanup

Do not weaken assertions to make tests pass. If a UI-only change is not practical
to test directly, still add or update domain regression coverage where the
behavior depends on durable state.

Before finalizing implementation work, run the focused tests for changed
behavior and then the full relevant test suite.

## Code Quality

- Read the relevant code before editing.
- Prefer the smallest coherent patch that fully solves the task.
- Keep durable model methods explicit and easy to follow.
- Add comments only for non-obvious reasoning or edge cases.
- Use names that make dbzero query/index/tag intent clear.
- Do not revert unrelated user changes in a dirty worktree.
