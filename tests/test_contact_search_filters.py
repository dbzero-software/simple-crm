from datetime import date, timedelta

import dbzero as db0

from simple_crm.models import (
    CONTACT_TAG_PREFIX,
    TASK_TAG_ARCHIVED_CONTACT,
    Contact,
    ContactStatus,
    TASK_FILTER_OPEN,
    TASK_FILTER_OVERDUE,
    Task,
)
from simple_crm.seed import seed_sample_data


def test_search_filters_by_company_status_tag_and_text(crm):
    northstar = crm.add_company("Northstar Analytics", "Analytics", "https://northstar.example")
    harbor = crm.add_company("Harbor Clinic", "Healthcare", "https://harbor.example")
    avery = crm.add_contact("Avery Stone", "avery@northstar.example", "Founder", northstar, ContactStatus.lead, "lead,technical")
    jon = crm.add_contact(
        "Jon Bell",
        "jon@harbor.example",
        "Operations Director",
        harbor,
        ContactStatus.active_customer,
        "customer,renewal",
    )
    crm.add_note(avery, "Needs pricing details for analytics rollout.")
    crm.add_note(jon, "Renewal date confirmed with operations.")

    assert list(crm.search_contacts(company=northstar)) == [avery]
    assert list(crm.search_contacts(status=ContactStatus.active_customer)) == [jon]
    assert list(crm.search_contacts(tag="technical")) == [avery]
    assert list(crm.search_contacts(query="renewal")) == [jon]
    assert list(crm.search_contacts(query="northstar")) == [avery]
    assert list(db0.find(Contact, "active_customer")) == [jon]
    assert list(db0.find(Contact, db0.as_tag(northstar))) == [avery]
    assert list(db0.find(f"{CONTACT_TAG_PREFIX}technical")) == [avery]


def test_contact_status_uses_dbzero_enum_values(crm):
    contact = crm.add_contact("Avery Stone", status=ContactStatus.lead)

    assert contact.status == ContactStatus.lead
    assert contact.status != "lead"
    assert list(crm.search_contacts(status=ContactStatus.lead)) == [contact]

    crm.change_contact_status(contact, ContactStatus.active_customer)

    assert contact.status == ContactStatus.active_customer
    assert list(crm.search_contacts(status=ContactStatus.active_customer)) == [contact]
    assert crm.counts()["active_customers"] == 1


def test_contact_status_rejects_strings(crm):
    try:
        crm.add_contact("Avery Stone", status="lead")
    except ValueError as exc:
        assert str(exc) == "Unknown contact status: 'lead'"
    else:
        raise AssertionError("string contact status should be rejected")


def test_search_companies_filters_by_company_text(crm):
    northstar = crm.add_company("Northstar Analytics", "Analytics", "https://northstar.example")
    harbor = crm.add_company("Harbor Clinic", "Healthcare", "https://harbor.example")

    assert list(crm.search_companies("analytics")) == [northstar]
    assert list(crm.search_companies("healthcare")) == [harbor]
    assert list(crm.search_companies("example")) == [northstar, harbor]


def test_paged_company_search_uses_requested_window(crm):
    for name in ["Atlas Legal", "Circuit Supply", "Harbor Clinic", "Meadow Foods", "Northstar Analytics"]:
        crm.add_company(name)

    first_page = crm.search_companies_page(page=1, page_size=2)
    second_page = crm.search_companies_page(page=2, page_size=2)

    assert first_page.total == 5
    assert first_page.page_count == 3
    assert len(first_page.items) == 2
    assert len(second_page.items) == 2
    assert set(first_page.items).isdisjoint(second_page.items)


def test_paged_contact_search_returns_metadata(crm):
    for index in range(12):
        crm.add_contact(f"Contact {index:02d}", status=ContactStatus.lead)

    page = crm.search_contacts_page(page=2, page_size=5)

    assert page.total == 12
    assert page.page == 2
    assert page.page_size == 5
    assert page.page_count == 3
    assert len(page.items) == 5
    assert page.has_previous
    assert page.has_next


def test_contact_retrieval_is_iterable_and_sorted_by_updated_index(crm):
    avery = crm.add_contact("Avery Stone", status=ContactStatus.lead)
    grace = crm.add_contact("Grace Kim", status=ContactStatus.lead)

    contacts = crm.search_contacts(status=ContactStatus.lead)
    companies = crm.search_companies()

    assert not isinstance(contacts, list)
    assert not isinstance(companies, list)
    assert list(contacts) == [grace, avery]

    crm.add_note(avery, "Recent follow-up note.")

    assert list(crm.search_contacts(status=ContactStatus.lead)) == [avery, grace]


def test_task_state_filters_and_archived_default(crm):
    active = crm.add_contact("Sam Chen", status=ContactStatus.lead, tags="lead")
    archived = crm.add_contact("Lena Ortiz", status=ContactStatus.inactive, tags="finance")
    open_task = crm.add_task(active, "Send pricing follow-up", date.today() + timedelta(days=3))
    overdue_task = crm.add_task(active, "Check contract status", date.today() - timedelta(days=2))
    archived_task = crm.add_task(archived, "Old task", date.today() - timedelta(days=5))
    crm.archive_contact(archived)

    assert list(db0.find(Task, TASK_TAG_ARCHIVED_CONTACT)) == [archived_task]
    assert crm.counts()["open_tasks"] == 2
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

    assert list(crm.search_contacts(company=northstar)) == []
    assert list(crm.search_contacts(company=harbor)) == [contact]
    assert contact.email == "avery@harbor.example"
    assert contact.title == "Advisor"


def test_remove_contact_tag_updates_contact_and_tag_filter(crm):
    contact = crm.add_contact("Avery Stone", tags="lead, technical")

    crm.remove_contact_tag(contact, "technical")

    assert contact.tags == {"lead"}
    assert list(crm.search_contacts(tag="technical")) == []
    assert list(crm.search_contacts(tag="lead")) == [contact]
