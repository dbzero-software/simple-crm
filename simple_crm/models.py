"""Durable domain model for the Simple CRM tutorial app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable

import dbzero as db0

from simple_crm.config import DATA_PREFIX
from simple_crm.utils import PageResult, paginate

ContactStatus = db0.enum(
    "ContactStatus",
    values=["lead", "prospect", "active_customer", "partner", "inactive", "archived"],
)
ContactStatusValue = type(ContactStatus.lead)
TaskState = db0.enum("TaskState", values=["open", "completed"])
TaskVisibility = db0.enum("TaskVisibility", values=["active_contact", "archived_contact"])
ContactOpenTaskState = db0.enum("ContactOpenTaskState", values=["none", "has_open"])


TASK_FILTER_ALL = "all"
TASK_FILTER_OPEN = "open"
TASK_FILTER_OVERDUE = "overdue"
CONTACT_TAG_PREFIX = "contact-tag:"


def _normalize_tags(tags: Iterable[str] | str | None) -> set[str]:
    if tags is None:
        return set()
    if isinstance(tags, str):
        raw_tags = tags.split(",")
    else:
        raw_tags = tags
    return {tag.strip().lower() for tag in raw_tags if tag and tag.strip()}


def _resolve_status(status: object) -> ContactStatusValue:
    for value in ContactStatus.values():
        if value == status:
            return value
    raise ValueError(f"Unknown contact status: {status!r}")


def _task_visibility(contact: Contact | None):
    TaskVisibility.values()
    return TaskVisibility.archived_contact if contact is not None and contact.archived else TaskVisibility.active_contact


@db0.memo(prefix=DATA_PREFIX)
@dataclass(eq=False)
class Company:
    """A customer, prospect, partner, or account organization."""

    name: str
    industry: str = ""
    website: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@db0.memo(prefix=DATA_PREFIX)
@dataclass(eq=False)
class Note:
    """A timestamped contact activity note."""

    body: str
    created_at: datetime = field(default_factory=datetime.now)


@db0.memo(prefix=DATA_PREFIX)
@db0.tag_fields("contact", "state", "visibility")
@dataclass(eq=False)
class Task:
    """A follow-up task attached to one contact."""

    title: str
    due_date: date | None = None
    description: str = ""
    state: object | None = None
    visibility: object | None = None
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    contact: Contact | None = None

    def __post_init__(self) -> None:
        TaskState.values()
        self.state = self.state or TaskState.open
        self.visibility = _task_visibility(self.contact)

    @property
    def completed(self) -> bool:
        return self.state == TaskState.completed

    def is_overdue(self, today: date | None = None) -> bool:
        today = today or date.today()
        return not self.completed and self.due_date is not None and self.due_date < today

    def complete(self) -> None:
        if not self.completed:
            self.state = TaskState.completed
            self.completed_at = datetime.now()

    def reopen(self) -> None:
        if self.completed:
            self.state = TaskState.open
            self.completed_at = None


@db0.memo(prefix=DATA_PREFIX)
@db0.tag_fields("status", "company", "open_task_state")
@dataclass(eq=False)
class Contact:
    """A person tracked in the CRM."""

    name: str
    email: str = ""
    title: str = ""
    company: Company | None = None
    status: ContactStatusValue = ContactStatus.lead
    tags: set[str] = field(default_factory=set)
    notes: list[Note] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    open_task_state: object | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.email = self.email.strip()
        self.title = self.title.strip()
        self.status = _resolve_status(self.status)
        self.tags = _normalize_tags(self.tags)
        ContactOpenTaskState.values()
        self.open_task_state = ContactOpenTaskState.has_open if self.open_tasks() else ContactOpenTaskState.none

    @property
    def archived(self) -> bool:
        return self.status == ContactStatus.archived

    @property
    def last_touch_at(self) -> datetime | None:
        note_times = [note.created_at for note in self.notes]
        completed_times = [task.completed_at for task in self.tasks if task.completed_at is not None]
        touches = note_times + completed_times
        return max(touches) if touches else None

    @property
    def next_task_due_at(self) -> date | None:
        due_dates = [task.due_date for task in self.open_tasks() if task.due_date is not None]
        return min(due_dates) if due_dates else None

    @property
    def open_task_count(self) -> int:
        return len(self.open_tasks())

    def open_tasks(self) -> list[Task]:
        return [task for task in self.tasks if not task.completed]

    def overdue_tasks(self, today: date | None = None) -> list[Task]:
        return [task for task in self.open_tasks() if task.is_overdue(today)]

    def update_basics(
        self,
        name: str,
        email: str = "",
        title: str = "",
        company: Company | None = None,
    ) -> None:
        self.name = name.strip()
        self.email = email.strip()
        self.title = title.strip()
        self.company = company
        self.updated_at = datetime.now()

    def change_status(self, status: ContactStatusValue) -> None:
        self.status = _resolve_status(status)
        self.updated_at = datetime.now()

    def add_note(self, body: str) -> Note:
        clean_body = body.strip()
        if not clean_body:
            raise ValueError("Note body is required.")
        note = Note(clean_body)
        self.notes.append(note)
        self.updated_at = datetime.now()
        return note

    def remove_note(self, note: Note) -> None:
        if note not in self.notes:
            raise ValueError("Note does not belong to this contact.")
        self.notes = [current for current in self.notes if current is not note]
        self.updated_at = datetime.now()

    def add_task(self, title: str, due_date: date | None = None, description: str = "") -> Task:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Task title is required.")
        task = Task(clean_title, due_date, description.strip(), contact=self)
        self.tasks.append(task)
        self.updated_at = datetime.now()
        return task

    def complete_task(self, task: Task) -> None:
        self._ensure_task(task)
        task.complete()
        self.updated_at = datetime.now()

    def reopen_task(self, task: Task) -> None:
        self._ensure_task(task)
        task.reopen()
        self.updated_at = datetime.now()

    def add_tag(self, tag: str) -> None:
        normalized = tag.strip().lower()
        if normalized and normalized not in self.tags:
            self.tags = {*self.tags, normalized}
            self.updated_at = datetime.now()

    def remove_tag(self, tag: str) -> None:
        normalized = tag.strip().lower()
        if normalized in self.tags:
            self.tags = {current for current in self.tags if current != normalized}
            self.updated_at = datetime.now()

    def _ensure_task(self, task: Task) -> None:
        if task not in self.tasks:
            raise ValueError("Task does not belong to this contact.")


@db0.memo(prefix=DATA_PREFIX, singleton=True)
@dataclass(eq=False)
class CRM:
    """The single durable root object for the Simple CRM app."""

    companies_by_name: dict[str, Company] = field(default_factory=dict)
    companies_by_created_at: db0.index = field(default_factory=db0.index)
    contacts_by_updated_at: db0.index = field(default_factory=db0.index)
    contacts_by_next_task_date: db0.index = field(default_factory=db0.index)
    tasks_by_created_at: db0.index = field(default_factory=db0.index)
    tasks_by_due_date: db0.index = field(default_factory=db0.index)

    def add_company(self, name: str, industry: str = "", website: str = "") -> Company:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Company name is required.")
        existing = self.find_company_by_name(clean_name)
        if existing is not None:
            return existing
        company = Company(clean_name, industry.strip(), website.strip())
        self.companies_by_name[self._company_key(clean_name)] = company
        self.companies_by_created_at.add(company.created_at, company)
        return company

    def add_contact(
        self,
        name: str,
        email: str = "",
        title: str = "",
        company: Company | None = None,
        status: ContactStatusValue = ContactStatus.lead,
        tags: Iterable[str] | str | None = None,
    ) -> Contact:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Contact name is required.")
        status = _resolve_status(status)
        contact = Contact(clean_name, email.strip(), title.strip(), company, status, tags=_normalize_tags(tags))
        self._index_contact(contact)
        return contact

    def update_contact_basics(
        self,
        contact: Contact,
        name: str,
        email: str = "",
        title: str = "",
        company: Company | None = None,
    ) -> None:
        old_updated_at = contact.updated_at
        contact.update_basics(name, email, title, company)
        self._reindex_contact_updated_at(contact, old_updated_at)

    def change_contact_status(self, contact: Contact, status: ContactStatusValue) -> None:
        old_status = contact.status
        old_updated_at = contact.updated_at
        contact.change_status(status)
        if old_status != contact.status:
            self._sync_contact_task_visibility(contact)
        self._reindex_contact_updated_at(contact, old_updated_at)

    def archive_contact(self, contact: Contact) -> None:
        self.change_contact_status(contact, ContactStatus.archived)

    def add_contact_tag(self, contact: Contact, tag: str) -> None:
        before = set(contact.tags)
        old_updated_at = contact.updated_at
        contact.add_tag(tag)
        after = set(contact.tags)
        for added in after - before:
            db0.tags(contact).add(self._contact_tag_key(added))
        if before != after:
            self._reindex_contact_updated_at(contact, old_updated_at)

    def remove_contact_tag(self, contact: Contact, tag: str) -> None:
        before = set(contact.tags)
        old_updated_at = contact.updated_at
        contact.remove_tag(tag)
        after = set(contact.tags)
        for removed in before - after:
            db0.tags(contact).remove(self._contact_tag_key(removed))
        if before != after:
            self._reindex_contact_updated_at(contact, old_updated_at)

    def add_note(self, contact: Contact, body: str) -> Note:
        old_updated_at = contact.updated_at
        note = contact.add_note(body)
        self._reindex_contact_updated_at(contact, old_updated_at)
        return note

    def remove_note(self, contact: Contact, note: Note) -> None:
        old_updated_at = contact.updated_at
        contact.remove_note(note)
        self._reindex_contact_updated_at(contact, old_updated_at)

    def add_task(self, contact: Contact, title: str, due_date: date | None = None, description: str = "") -> Task:
        old_next_due = contact.next_task_due_at
        old_updated_at = contact.updated_at
        task = contact.add_task(title, due_date, description)
        self._index_task(task)
        self._reindex_next_task_date(contact, old_next_due)
        self._sync_contact_open_task_state(contact)
        self._reindex_contact_updated_at(contact, old_updated_at)
        return task

    def complete_task(self, contact: Contact, task: Task) -> None:
        old_next_due = contact.next_task_due_at
        old_updated_at = contact.updated_at
        contact.complete_task(task)
        self._reindex_next_task_date(contact, old_next_due)
        self._sync_contact_open_task_state(contact)
        self._reindex_contact_updated_at(contact, old_updated_at)

    def reopen_task(self, contact: Contact, task: Task) -> None:
        old_next_due = contact.next_task_due_at
        old_updated_at = contact.updated_at
        contact.reopen_task(task)
        self._reindex_next_task_date(contact, old_next_due)
        self._sync_contact_open_task_state(contact)
        self._reindex_contact_updated_at(contact, old_updated_at)

    def companies(self):
        return self.companies_by_created_at.sort(db0.find(Company))

    def search_companies(self, query: str = ""):
        normalized_query = query.strip().lower()
        companies = db0.find(Company)
        if normalized_query:
            companies = db0.filter(lambda company: self._company_matches_text(company, normalized_query), companies)
        return self.companies_by_created_at.sort(companies)

    def tasks(self, task_filter: str = TASK_FILTER_OPEN, today: date | None = None):
        return self._task_query(task_filter, today)

    def tasks_page(
        self,
        task_filter: str = TASK_FILTER_OPEN,
        today: date | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> PageResult:
        return paginate(self.tasks(task_filter, today), page, page_size)

    def search_companies_page(self, query: str = "", page: int = 1, page_size: int = 10) -> PageResult:
        return paginate(self.search_companies(query), page, page_size)

    def contacts(self, include_archived: bool = False):
        contact_query = db0.find(Contact) if include_archived else db0.find(Contact, db0.no(ContactStatus.archived))
        return self.contacts_by_updated_at.sort(contact_query, desc=True)

    def contacts_page(
        self,
        page: int = 1,
        page_size: int = 10,
        include_archived: bool = False,
    ) -> PageResult:
        return paginate(self.contacts(include_archived=include_archived), page, page_size)

    def find_company_by_name(self, name: str) -> Company | None:
        return self.companies_by_name.get(self._company_key(name))

    def available_tags(self) -> list[str]:
        tags = set()
        for contact in self.contacts(include_archived=True):
            tags.update(contact.tags)
        return sorted(tags)

    def overdue_tasks(self, today: date | None = None):
        today = today or date.today()
        due_range = self.tasks_by_due_date.select(None, today - timedelta(days=1))
        return db0.find(Task, TaskState.open, TaskVisibility.active_contact, due_range)

    def task_rows(
        self,
        task_filter: str = TASK_FILTER_OPEN,
        today: date | None = None,
    ):
        return self._task_rows_from_tasks(self.tasks(task_filter, today))

    def task_rows_page(
        self,
        task_filter: str = TASK_FILTER_OPEN,
        today: date | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> PageResult:
        task_page = self.tasks_page(task_filter, today, page, page_size)
        return PageResult(self._task_rows_from_tasks(task_page.items), task_page.total, task_page.page, task_page.page_size)

    def counts(self, today: date | None = None) -> dict[str, int]:
        contacts = self.contacts()
        open_tasks = db0.find(Task, TaskState.open, TaskVisibility.active_contact)
        completed_tasks = db0.find(Task, TaskState.completed, TaskVisibility.active_contact)
        return {
            "companies": len(self.companies()),
            "contacts": len(contacts),
            "active_customers": len(db0.find(Contact, ContactStatus.active_customer, db0.no(ContactStatus.archived))),
            "leads": len(db0.find(Contact, ContactStatus.lead, db0.no(ContactStatus.archived))),
            "open_tasks": len(open_tasks),
            "completed_tasks": len(completed_tasks),
            "overdue_tasks": len(self.overdue_tasks(today)),
        }

    def search_contacts(
        self,
        query: str = "",
        company: Company | None = None,
        status: ContactStatusValue | None = None,
        tag: str | None = None,
        task_filter: str = TASK_FILTER_ALL,
        include_archived: bool = False,
        today: date | None = None,
    ):
        today = today or date.today()
        if task_filter not in {TASK_FILTER_ALL, TASK_FILTER_OPEN, TASK_FILTER_OVERDUE}:
            raise ValueError(f"Unknown task filter: {task_filter!r}")
        candidates = self._indexed_candidates(company, status, tag, task_filter, include_archived, today)
        normalized_query = query.strip().lower()
        result = candidates
        if not normalized_query:
            return self.contacts_by_updated_at.sort(result, desc=True)
        result = db0.filter(lambda contact: self._contact_matches_text(contact, normalized_query), result)
        return self.contacts_by_updated_at.sort(result, desc=True)

    def search_contacts_page(
        self,
        query: str = "",
        company: Company | None = None,
        status: ContactStatusValue | None = None,
        tag: str | None = None,
        task_filter: str = TASK_FILTER_ALL,
        include_archived: bool = False,
        today: date | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> PageResult:
        if (
            not query.strip()
            and company is None
            and status is None
            and tag is None
            and task_filter == TASK_FILTER_ALL
        ):
            return self.contacts_page(page, page_size, include_archived)
        return paginate(
            self.search_contacts(query, company, status, tag, task_filter, include_archived, today),
            page,
            page_size,
        )

    def _indexed_candidates(
        self,
        company: Company | None,
        status: ContactStatusValue | None,
        tag: str | None,
        task_filter: str,
        include_archived: bool,
        today: date,
    ):
        criteria: list[object] = [Contact]
        if not include_archived:
            criteria.append(db0.no(ContactStatus.archived))
        if company is not None:
            criteria.append(db0.as_tag(company))
        if status:
            criteria.append(_resolve_status(status))
        if tag:
            clean_tag = tag.strip().lower()
            criteria.append(self._contact_tag_key(clean_tag))
        if task_filter == TASK_FILTER_OPEN:
            criteria.append(ContactOpenTaskState.has_open)
        elif task_filter == TASK_FILTER_OVERDUE:
            overdue_contacts = db0.find(Contact, self.contacts_by_next_task_date.select(None, today - timedelta(days=1)))
            if not overdue_contacts:
                return overdue_contacts
            criteria.append(overdue_contacts)
        return db0.find(*criteria)

    def _task_query(self, task_filter: str, today: date | None = None):
        if task_filter not in {TASK_FILTER_OPEN, TASK_FILTER_OVERDUE}:
            raise ValueError(f"Unknown task filter: {task_filter!r}")
        today = today or date.today()
        task_query = db0.find(Task, TaskState.open, TaskVisibility.active_contact)
        if task_filter == TASK_FILTER_OVERDUE:
            task_query = db0.find(task_query, self.tasks_by_due_date.select(None, today - timedelta(days=1)))
        return self.tasks_by_due_date.sort(self.tasks_by_created_at.sort(task_query))

    def _index_contact(self, contact: Contact) -> None:
        self._sync_contact_open_task_state(contact)
        for tag in contact.tags:
            db0.tags(contact).add(self._contact_tag_key(tag))
        self.contacts_by_updated_at.add(contact.updated_at, contact)
        if contact.next_task_due_at is not None:
            self.contacts_by_next_task_date.add(contact.next_task_due_at, contact)

    def _index_task(self, task: Task) -> None:
        self.tasks_by_created_at.add(task.created_at, task)
        self.tasks_by_due_date.add(task.due_date, task)

    def _task_rows_from_tasks(self, tasks):
        return ((task.contact, task) for task in tasks if task.contact is not None)

    def _sync_contact_open_task_state(self, contact: Contact) -> None:
        ContactOpenTaskState.values()
        contact.open_task_state = ContactOpenTaskState.has_open if contact.open_tasks() else ContactOpenTaskState.none

    def _reindex_contact_updated_at(self, contact: Contact, old_updated_at: datetime) -> None:
        if old_updated_at == contact.updated_at:
            return
        self.contacts_by_updated_at.remove(old_updated_at, contact)
        self.contacts_by_updated_at.add(contact.updated_at, contact)

    def _sync_contact_task_visibility(self, contact: Contact) -> None:
        for task in contact.tasks:
            task.visibility = _task_visibility(contact)

    def _reindex_next_task_date(self, contact: Contact, old_next_due: date | None) -> None:
        new_next_due = contact.next_task_due_at
        if old_next_due == new_next_due:
            return
        if old_next_due is not None:
            self.contacts_by_next_task_date.remove(old_next_due, contact)
        if new_next_due is not None:
            self.contacts_by_next_task_date.add(new_next_due, contact)

    def _contact_matches_text(self, contact: Contact, query: str) -> bool:
        fields = [
            contact.name,
            contact.email,
            contact.title,
            contact.company.name if contact.company else "",
            " ".join(sorted(contact.tags)),
            " ".join(note.body for note in contact.notes),
        ]
        return any(query in field.lower() for field in fields)

    def _company_matches_text(self, company: Company, query: str) -> bool:
        fields = [company.name, company.industry, company.website]
        return any(query in field.lower() for field in fields)

    def _company_key(self, name: str) -> str:
        return name.strip().lower()

    def _contact_tag_key(self, tag: str) -> str:
        return f"{CONTACT_TAG_PREFIX}{tag.strip().lower()}"
