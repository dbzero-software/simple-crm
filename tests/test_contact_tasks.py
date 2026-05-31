from datetime import date, timedelta

from simple_crm.models import TASK_FILTER_OPEN, TASK_FILTER_OVERDUE


def test_follow_up_loop_updates_contact_and_metrics(crm):
    company = crm.add_company("Northstar Analytics", "Analytics", "https://northstar.example")
    contact = crm.add_contact(
        "Avery Stone",
        "avery@northstar.example",
        "Founder",
        company,
        "lead",
        "lead, technical",
    )

    note = crm.add_note(contact, "Discussed current reporting workflow.")
    due_date = date.today() + timedelta(days=2)
    task = crm.add_task(contact, "Send pricing follow-up", due_date)

    assert contact.last_touch_at == note.created_at
    assert contact.next_task_due_at == due_date
    assert contact.open_task_count == 1
    assert crm.counts()["open_tasks"] == 1
    assert contact in crm.search_contacts(task_filter=TASK_FILTER_OPEN)

    crm.complete_task(contact, task)

    assert task.completed
    assert task.completed_at is not None
    assert contact.next_task_due_at is None
    assert contact.open_task_count == 0
    assert crm.counts()["open_tasks"] == 0
    assert crm.counts()["completed_tasks"] == 1
    assert contact.last_touch_at == task.completed_at


def test_overdue_and_reopen_task_filters(crm):
    contact = crm.add_contact("Grace Kim", "grace@example.com", "IT Manager", status="prospect")
    overdue_task = crm.add_task(contact, "Schedule technical review", date.today() - timedelta(days=1))

    assert contact in crm.search_contacts(task_filter=TASK_FILTER_OVERDUE)
    assert crm.counts()["overdue_tasks"] == 1

    crm.complete_task(contact, overdue_task)

    assert contact not in crm.search_contacts(task_filter=TASK_FILTER_OVERDUE)
    assert crm.counts()["overdue_tasks"] == 0

    crm.reopen_task(contact, overdue_task)

    assert not overdue_task.completed
    assert contact in crm.search_contacts(task_filter=TASK_FILTER_OVERDUE)


def test_checkpoint_records_current_counts(crm):
    crm.add_company("Atlas Legal", "Legal services", "https://atlas.example")
    contact = crm.add_contact("Theo Martin", status="partner")
    task = crm.add_task(contact, "Check contract status")
    crm.complete_task(contact, task)

    checkpoint = crm.create_checkpoint("after first partner")

    assert checkpoint.label == "after first partner"
    assert checkpoint.counts["companies"] == 1
    assert checkpoint.counts["contacts"] == 1
    assert checkpoint.counts["completed_tasks"] == 1

