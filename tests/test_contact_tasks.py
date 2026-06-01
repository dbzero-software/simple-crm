from datetime import date, timedelta

import dbzero as db0

from simple_crm.models import ContactStatus, TASK_FILTER_OPEN, TASK_FILTER_OVERDUE, TASK_TAG_COMPLETED, TASK_TAG_OPEN, Task


def test_follow_up_loop_updates_contact_and_metrics(crm):
    company = crm.add_company("Northstar Analytics", "Analytics", "https://northstar.example")
    contact = crm.add_contact(
        "Avery Stone",
        "avery@northstar.example",
        "Founder",
        company,
        ContactStatus.lead,
        "lead, technical",
    )

    note = crm.add_note(contact, "Discussed current reporting workflow.")
    due_date = date.today() + timedelta(days=2)
    task = crm.add_task(contact, "Send pricing follow-up", due_date, "Share pricing options and timeline.")

    assert contact.last_touch_at == note.created_at
    assert task.description == "Share pricing options and timeline."
    assert task.contact == contact
    assert list(db0.find(Task, TASK_TAG_OPEN, db0.as_tag(contact))) == [task]
    assert contact.next_task_due_at == due_date
    assert contact.open_task_count == 1
    assert crm.counts()["open_tasks"] == 1
    assert contact in crm.search_contacts(task_filter=TASK_FILTER_OPEN)

    crm.complete_task(contact, task)

    assert task.completed
    assert task.completed_at is not None
    assert list(db0.find(Task, TASK_TAG_OPEN, db0.as_tag(contact))) == []
    assert list(db0.find(Task, TASK_TAG_COMPLETED, db0.as_tag(contact))) == [task]
    assert contact.next_task_due_at is None
    assert contact.open_task_count == 0
    assert crm.counts()["open_tasks"] == 0
    assert crm.counts()["completed_tasks"] == 1
    assert contact.last_touch_at == task.completed_at


def test_overdue_and_reopen_task_filters(crm):
    contact = crm.add_contact("Grace Kim", "grace@example.com", "IT Manager", status=ContactStatus.prospect)
    overdue_task = crm.add_task(contact, "Schedule technical review", date.today() - timedelta(days=1))

    assert contact in crm.search_contacts(task_filter=TASK_FILTER_OVERDUE)
    assert crm.counts()["overdue_tasks"] == 1

    crm.complete_task(contact, overdue_task)

    assert contact not in crm.search_contacts(task_filter=TASK_FILTER_OVERDUE)
    assert crm.counts()["overdue_tasks"] == 0

    crm.reopen_task(contact, overdue_task)

    assert not overdue_task.completed
    assert contact in crm.search_contacts(task_filter=TASK_FILTER_OVERDUE)


def test_remove_note_updates_contact_and_search_text(crm):
    contact = crm.add_contact("Avery Stone", status=ContactStatus.lead)
    note = crm.add_note(contact, "Discussed current reporting workflow.")

    crm.remove_note(contact, note)

    assert contact.notes == []
    assert list(crm.search_contacts(query="reporting workflow")) == []


def test_task_rows_return_open_tasks_with_contacts_in_due_order(crm):
    today = date(2026, 5, 31)
    avery = crm.add_contact("Avery Stone", status=ContactStatus.lead)
    grace = crm.add_contact("Grace Kim", status=ContactStatus.prospect)
    later = crm.add_task(avery, "Send recap", today + timedelta(days=3))
    overdue = crm.add_task(grace, "Schedule technical review", today - timedelta(days=1))
    completed = crm.add_task(avery, "Already handled", today - timedelta(days=2))
    crm.complete_task(avery, completed)

    assert list(crm.task_rows(today=today)) == [(grace, overdue), (avery, later)]
    assert list(crm.task_rows(TASK_FILTER_OVERDUE, today=today)) == [(grace, overdue)]
