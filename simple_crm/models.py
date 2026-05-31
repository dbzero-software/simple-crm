"""Durable domain model for the Simple CRM tutorial app."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable

import dbzero as db0

from simple_crm.config import DATA_PREFIX

CONTACT_STATUSES = [
    "lead",
    "prospect",
    "active_customer",
    "partner",
    "inactive",
    "archived",
]

TASK_FILTER_ALL = "all"
TASK_FILTER_OPEN = "open"
TASK_FILTER_OVERDUE = "overdue"


def _now() -> datetime:
    return datetime.now()


def _normalize_tags(tags: Iterable[str] | str | None) -> set[str]:
    if tags is None:
        return set()
    if isinstance(tags, str):
        raw_tags = tags.split(",")
    else:
        raw_tags = tags
    return {tag.strip().lower() for tag in raw_tags if tag and tag.strip()}


def _check_status(status: str) -> str:
    if status not in CONTACT_STATUSES:
        raise ValueError(f"Unknown contact status: {status!r}")
    return status


@db0.memo(prefix=DATA_PREFIX)
@dataclass(eq=False)
class Company:
    """A customer, prospect, partner, or account organization."""

    name: str
    industry: str = ""
    website: str = ""
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def update_basics(self, name: str, industry: str = "", website: str = "") -> None:
        self.name = name.strip()
        self.industry = industry.strip()
        self.website = website.strip()
        self.updated_at = _now()


@db0.memo(prefix=DATA_PREFIX)
@dataclass(eq=False)
class Note:
    """A timestamped contact activity note."""

    body: str
    created_at: datetime = field(default_factory=_now)


@db0.memo(prefix=DATA_PREFIX)
@dataclass(eq=False)
class Task:
    """A follow-up task attached to one contact."""

    title: str
    due_date: date | None = None
    completed: bool = False
    created_at: datetime = field(default_factory=_now)
    completed_at: datetime | None = None

    def complete(self) -> None:
        if not self.completed:
            self.completed = True
            self.completed_at = _now()

    def reopen(self) -> None:
        if self.completed:
            self.completed = False
            self.completed_at = None


@db0.memo(prefix=DATA_PREFIX)
@dataclass(eq=False)
class Contact:
    """A person tracked in the CRM."""

    name: str
    email: str = ""
    title: str = ""
    company: Company | None = None
    status: str = "lead"
    tags: set[str] = field(default_factory=set)
    notes: list[Note] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    archived: bool = False
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.email = self.email.strip()
        self.title = self.title.strip()
        self.status = _check_status(self.status)
        self.tags = _normalize_tags(self.tags)

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
        today = today or date.today()
        return [
            task
            for task in self.open_tasks()
            if task.due_date is not None and task.due_date < today
        ]

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
        self.updated_at = _now()

    def change_status(self, status: str) -> None:
        self.status = _check_status(status)
        self.archived = status == "archived"
        self.updated_at = _now()

    def add_note(self, body: str) -> Note:
        clean_body = body.strip()
        if not clean_body:
            raise ValueError("Note body is required.")
        note = Note(clean_body)
        self.notes.append(note)
        self.updated_at = _now()
        return note

    def add_task(self, title: str, due_date: date | None = None) -> Task:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("Task title is required.")
        task = Task(clean_title, due_date)
        self.tasks.append(task)
        self.updated_at = _now()
        return task

    def complete_task(self, task: Task) -> None:
        self._ensure_task(task)
        task.complete()
        self.updated_at = _now()

    def reopen_task(self, task: Task) -> None:
        self._ensure_task(task)
        task.reopen()
        self.updated_at = _now()

    def add_tag(self, tag: str) -> None:
        normalized = tag.strip().lower()
        if normalized:
            self.tags.add(normalized)
            self.updated_at = _now()

    def remove_tag(self, tag: str) -> None:
        normalized = tag.strip().lower()
        if normalized in self.tags:
            self.tags.remove(normalized)
            self.updated_at = _now()

    def archive(self) -> None:
        self.status = "archived"
        self.archived = True
        self.updated_at = _now()

    def _ensure_task(self, task: Task) -> None:
        if task not in self.tasks:
            raise ValueError("Task does not belong to this contact.")


@db0.memo(prefix=DATA_PREFIX)
@dataclass(eq=False)
class CRMCheckpoint:
    """A lightweight count checkpoint for tutorial activity tracking."""

    label: str
    counts: dict[str, int]
    created_at: datetime = field(default_factory=_now)


@db0.memo(prefix=DATA_PREFIX, singleton=True)
@dataclass(eq=False)
class CRM:
    """The single durable root object for the Simple CRM app."""

    companies_by_name: dict[str, Company] = field(default_factory=dict)
    contacts_by_company: dict[str, list[Contact]] = field(default_factory=dict)
    contacts_by_status: dict[str, list[Contact]] = field(default_factory=dict)
    contacts_by_tag: dict[str, list[Contact]] = field(default_factory=dict)
    contacts_by_next_task_date: db0.index = field(default_factory=db0.index)
    checkpoints_by_created_at: db0.index = field(default_factory=db0.index)

    def add_company(self, name: str, industry: str = "", website: str = "") -> Company:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Company name is required.")
        existing = self.find_company_by_name(clean_name)
        if existing is not None:
            return existing
        company = Company(clean_name, industry.strip(), website.strip())
        self.companies_by_name[self._company_key(clean_name)] = company
        return company

    def update_company(
        self,
        company: Company,
        name: str,
        industry: str = "",
        website: str = "",
    ) -> None:
        old_name = company.name
        old_key = self._company_key(old_name)
        company.update_basics(name, industry, website)
        new_key = self._company_key(company.name)
        if old_key != new_key:
            self.companies_by_name.pop(old_key, None)
            self.companies_by_name[new_key] = company
            contacts = self.contacts_by_company.pop(old_key, [])
            if contacts:
                self.contacts_by_company[new_key] = contacts

    def add_contact(
        self,
        name: str,
        email: str = "",
        title: str = "",
        company: Company | None = None,
        status: str = "lead",
        tags: Iterable[str] | str | None = None,
    ) -> Contact:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Contact name is required.")
        contact = Contact(clean_name, email.strip(), title.strip(), company, _check_status(status), _normalize_tags(tags))
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
        old_company = contact.company
        contact.update_basics(name, email, title, company)
        if old_company is not company:
            if old_company is not None:
                self._dict_list_remove(self.contacts_by_company, self._company_index_key(old_company), contact)
            if company is not None:
                self._dict_list_add(self.contacts_by_company, self._company_index_key(company), contact)

    def change_contact_status(self, contact: Contact, status: str) -> None:
        old_status = contact.status
        contact.change_status(status)
        if old_status != contact.status:
            self._dict_list_remove(self.contacts_by_status, old_status, contact)
            self._dict_list_add(self.contacts_by_status, contact.status, contact)

    def archive_contact(self, contact: Contact) -> None:
        self.change_contact_status(contact, "archived")

    def add_contact_tag(self, contact: Contact, tag: str) -> None:
        before = set(contact.tags)
        contact.add_tag(tag)
        for added in contact.tags - before:
            self._dict_list_add(self.contacts_by_tag, added, contact)

    def remove_contact_tag(self, contact: Contact, tag: str) -> None:
        before = set(contact.tags)
        contact.remove_tag(tag)
        for removed in before - contact.tags:
            self._dict_list_remove(self.contacts_by_tag, removed, contact)

    def add_note(self, contact: Contact, body: str) -> Note:
        return contact.add_note(body)

    def add_task(self, contact: Contact, title: str, due_date: date | None = None) -> Task:
        old_next_due = contact.next_task_due_at
        task = contact.add_task(title, due_date)
        self._reindex_next_task_date(contact, old_next_due)
        return task

    def complete_task(self, contact: Contact, task: Task) -> None:
        old_next_due = contact.next_task_due_at
        contact.complete_task(task)
        self._reindex_next_task_date(contact, old_next_due)

    def reopen_task(self, contact: Contact, task: Task) -> None:
        old_next_due = contact.next_task_due_at
        contact.reopen_task(task)
        self._reindex_next_task_date(contact, old_next_due)

    def companies(self) -> list[Company]:
        return sorted(db0.find(Company), key=lambda company: company.name.lower())

    def contacts(self, include_archived: bool = False) -> list[Contact]:
        contacts = list(db0.find(Contact))
        if not include_archived:
            contacts = [contact for contact in contacts if not contact.archived and contact.status != "archived"]
        return sorted(contacts, key=lambda contact: contact.updated_at, reverse=True)

    def find_company_by_name(self, name: str) -> Company | None:
        return self.companies_by_name.get(self._company_key(name))

    def available_tags(self) -> list[str]:
        tags = set()
        for contact in self.contacts(include_archived=True):
            tags.update(contact.tags)
        return sorted(tags)

    def open_tasks(self) -> list[Task]:
        tasks: list[Task] = []
        for contact in self.contacts():
            tasks.extend(contact.open_tasks())
        return tasks

    def overdue_tasks(self, today: date | None = None) -> list[Task]:
        today = today or date.today()
        tasks: list[Task] = []
        for contact in self.contacts():
            tasks.extend(contact.overdue_tasks(today))
        return tasks

    def counts(self, today: date | None = None) -> dict[str, int]:
        contacts = self.contacts()
        all_tasks = [task for contact in contacts for task in contact.tasks]
        return {
            "companies": len(self.companies()),
            "contacts": len(contacts),
            "active_customers": len([contact for contact in contacts if contact.status == "active_customer"]),
            "leads": len([contact for contact in contacts if contact.status == "lead"]),
            "open_tasks": len([task for task in all_tasks if not task.completed]),
            "completed_tasks": len([task for task in all_tasks if task.completed]),
            "overdue_tasks": len(self.overdue_tasks(today)),
        }

    def create_checkpoint(self, label: str) -> CRMCheckpoint:
        clean_label = label.strip()
        if not clean_label:
            raise ValueError("Checkpoint label is required.")
        checkpoint = CRMCheckpoint(clean_label, self.counts())
        self.checkpoints_by_created_at.add(checkpoint.created_at, checkpoint)
        return checkpoint

    def search_contacts(
        self,
        query: str = "",
        company: Company | None = None,
        status: str | None = None,
        tag: str | None = None,
        task_filter: str = TASK_FILTER_ALL,
        include_archived: bool = False,
        today: date | None = None,
    ) -> list[Contact]:
        today = today or date.today()
        candidates = self._indexed_candidates(company, status, tag, include_archived)
        normalized_query = query.strip().lower()
        result = []
        for contact in candidates:
            if not include_archived and (contact.archived or contact.status == "archived"):
                continue
            if task_filter == TASK_FILTER_OPEN and not contact.open_tasks():
                continue
            if task_filter == TASK_FILTER_OVERDUE and not contact.overdue_tasks(today):
                continue
            if task_filter not in {TASK_FILTER_ALL, TASK_FILTER_OPEN, TASK_FILTER_OVERDUE}:
                raise ValueError(f"Unknown task filter: {task_filter!r}")
            if normalized_query and not self._contact_matches_text(contact, normalized_query):
                continue
            result.append(contact)
        return sorted(result, key=lambda contact: contact.updated_at, reverse=True)

    def _indexed_candidates(
        self,
        company: Company | None,
        status: str | None,
        tag: str | None,
        include_archived: bool,
    ) -> set[Contact]:
        candidate_sets: list[set[Contact]] = []
        if company is not None:
            candidate_sets.append(set(self.contacts_by_company.get(self._company_index_key(company), [])))
        if status:
            candidate_sets.append(set(self.contacts_by_status.get(_check_status(status), [])))
        if tag:
            clean_tag = tag.strip().lower()
            candidate_sets.append(set(self.contacts_by_tag.get(clean_tag, [])))
        if not candidate_sets:
            return set(self.contacts(include_archived=include_archived))
        return set.intersection(*candidate_sets) if candidate_sets else set()

    def _index_contact(self, contact: Contact) -> None:
        if contact.company is not None:
            self._dict_list_add(self.contacts_by_company, self._company_index_key(contact.company), contact)
        self._dict_list_add(self.contacts_by_status, contact.status, contact)
        for tag in contact.tags:
            self._dict_list_add(self.contacts_by_tag, tag, contact)
        if contact.next_task_due_at is not None:
            self.contacts_by_next_task_date.add(contact.next_task_due_at, contact)

    def _reindex_next_task_date(self, contact: Contact, old_next_due: date | None) -> None:
        new_next_due = contact.next_task_due_at
        if old_next_due == new_next_due:
            return
        if old_next_due is not None:
            self._safe_remove(self.contacts_by_next_task_date, old_next_due, contact)
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

    def _company_index_key(self, company: Company) -> str:
        return self._company_key(company.name)

    def _company_key(self, name: str) -> str:
        return name.strip().lower()

    def _dict_list_add(self, index: dict[str, list[Contact]], key: str, contact: Contact) -> None:
        contacts = index.setdefault(key, [])
        if contact not in contacts:
            contacts.append(contact)

    def _dict_list_remove(self, index: dict[str, list[Contact]], key: str, contact: Contact) -> None:
        contacts = index.get(key)
        if not contacts:
            return
        if contact in contacts:
            contacts.remove(contact)
        if not contacts:
            index.pop(key, None)

    def _safe_remove(self, index: db0.index, key: object, value: object) -> None:
        try:
            index.remove(key, value)
        except Exception:  # dbzero raises when the index entry is already absent.
            pass
