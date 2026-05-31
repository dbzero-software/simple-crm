from datetime import date, timedelta

from simple_crm.models import TASK_FILTER_OPEN, TASK_FILTER_OVERDUE
from simple_crm.seed import seed_sample_data


def test_search_filters_by_company_status_tag_and_text(crm):
    northstar = crm.add_company("Northstar Analytics", "Analytics", "https://northstar.example")
    harbor = crm.add_company("Harbor Clinic", "Healthcare", "https://harbor.example")
    avery = crm.add_contact("Avery Stone", "avery@northstar.example", "Founder", northstar, "lead", "lead,technical")
    jon = crm.add_contact("Jon Bell", "jon@harbor.example", "Operations Director", harbor, "active_customer", "customer,renewal")
    crm.add_note(avery, "Needs pricing details for analytics rollout.")
    crm.add_note(jon, "Renewal date confirmed with operations.")

    assert crm.search_contacts(company=northstar) == [avery]
    assert crm.search_contacts(status="active_customer") == [jon]
    assert crm.search_contacts(tag="technical") == [avery]
    assert crm.search_contacts(query="renewal") == [jon]
    assert crm.search_contacts(query="northstar") == [avery]


def test_task_state_filters_and_archived_default(crm):
    active = crm.add_contact("Sam Chen", status="lead", tags="lead")
    archived = crm.add_contact("Lena Ortiz", status="inactive", tags="finance")
    open_task = crm.add_task(active, "Send pricing follow-up", date.today() + timedelta(days=3))
    overdue_task = crm.add_task(active, "Check contract status", date.today() - timedelta(days=2))
    crm.add_task(archived, "Old task", date.today() - timedelta(days=5))
    crm.archive_contact(archived)

    assert active in crm.search_contacts(task_filter=TASK_FILTER_OPEN)
    assert active in crm.search_contacts(task_filter=TASK_FILTER_OVERDUE)
    assert archived not in crm.search_contacts(query="Lena")
    assert archived in crm.search_contacts(query="Lena", include_archived=True)

    crm.complete_task(active, overdue_task)
    assert active not in crm.search_contacts(task_filter=TASK_FILTER_OVERDUE)
    assert active in crm.search_contacts(task_filter=TASK_FILTER_OPEN)

    crm.complete_task(active, open_task)
    assert active not in crm.search_contacts(task_filter=TASK_FILTER_OPEN)


def test_seed_sample_data_is_idempotent_and_useful(crm):
    first = seed_sample_data(crm, today=date(2026, 5, 31))
    second = seed_sample_data(crm, today=date(2026, 5, 31))

    assert first == {
        "companies": 5,
        "contacts": 12,
        "created_companies": 5,
        "created_contacts": 12,
        "created_tasks": 9,
    }
    assert second == {
        "companies": 5,
        "contacts": 12,
        "created_companies": 0,
        "created_contacts": 0,
        "created_tasks": 0,
    }
    assert crm.counts(today=date(2026, 5, 31))["overdue_tasks"] >= 1
    assert crm.search_contacts(tag="needs-follow-up")


def test_seed_sample_data_does_not_skip_when_northstar_already_exists(crm):
    crm.add_company("Northstar Analytics", "User-created", "https://custom.example")

    result = seed_sample_data(crm, today=date(2026, 5, 31))

    assert result == {
        "companies": 5,
        "contacts": 12,
        "created_companies": 4,
        "created_contacts": 12,
        "created_tasks": 9,
    }
    assert len(crm.contacts(include_archived=True)) == 12
    assert crm.search_contacts(query="Avery Stone")


def test_update_contact_basics_moves_company_filter(crm):
    northstar = crm.add_company("Northstar Analytics")
    harbor = crm.add_company("Harbor Clinic")
    contact = crm.add_contact("Avery Stone", "avery@example.com", "Founder", northstar)

    crm.update_contact_basics(contact, "Avery Stone", "avery@harbor.example", "Advisor", harbor)

    assert crm.search_contacts(company=northstar) == []
    assert crm.search_contacts(company=harbor) == [contact]
    assert contact.email == "avery@harbor.example"
    assert contact.title == "Advisor"
