"""Sample data for the Simple CRM tutorial app."""

from __future__ import annotations

from datetime import date, timedelta

from simple_crm.models import CRM, Company, Contact, ContactStatus


def seed_sample_data(crm: CRM, today: date | None = None) -> dict[str, int]:
    """Populate the CRM with tutorial sample data.

    The operation is intentionally idempotent by sample contact email. Existing
    companies are reused, and missing sample contacts receive their demo notes
    and tasks.
    """
    today = today or date.today()
    created_companies = 0

    company_specs = [
        ("Northstar Analytics", "Analytics", "https://northstar.example"),
        ("Harbor Clinic", "Healthcare", "https://harbor.example"),
        ("Circuit Supply", "Industrial supply", "https://circuit.example"),
        ("Meadow Foods", "Food distribution", "https://meadow.example"),
        ("Atlas Legal", "Legal services", "https://atlas.example"),
    ]
    companies: dict[str, Company] = {}
    for name, industry, website in company_specs:
        if crm.find_company_by_name(name) is None:
            created_companies += 1
        companies[name] = crm.add_company(name, industry, website)

    specs = [
        ("Avery Stone", "avery@northstar.example", "Founder", companies["Northstar Analytics"], ContactStatus.lead, "lead,technical,needs-follow-up"),
        ("Mina Patel", "mina@northstar.example", "Data Lead", companies["Northstar Analytics"], ContactStatus.prospect, "prospect,technical"),
        ("Jon Bell", "jon@harbor.example", "Operations Director", companies["Harbor Clinic"], ContactStatus.active_customer, "customer,renewal"),
        ("Elena Ruiz", "elena@harbor.example", "Clinic Manager", companies["Harbor Clinic"], ContactStatus.partner, "partner,finance"),
        ("Sam Chen", "sam@circuit.example", "VP Sales", companies["Circuit Supply"], ContactStatus.lead, "lead,finance"),
        ("Priya Shah", "priya@circuit.example", "Implementation Lead", companies["Circuit Supply"], ContactStatus.prospect, "prospect,technical"),
        ("Noah Brooks", "noah@meadow.example", "Owner", companies["Meadow Foods"], ContactStatus.active_customer, "customer,renewal"),
        ("Lena Ortiz", "lena@meadow.example", "Finance Manager", companies["Meadow Foods"], ContactStatus.inactive, "finance"),
        ("Theo Martin", "theo@atlas.example", "Partner", companies["Atlas Legal"], ContactStatus.partner, "partner,customer"),
        ("Grace Kim", "grace@atlas.example", "IT Manager", companies["Atlas Legal"], ContactStatus.prospect, "prospect,technical,needs-follow-up"),
        ("Iris Walker", "iris@example.com", "Independent Consultant", None, ContactStatus.lead, "lead,needs-follow-up"),
        ("Marco Silva", "marco@example.com", "Advisor", None, ContactStatus.inactive, "partner"),
    ]

    contacts: list[Contact] = []
    created_contacts = 0
    created_tasks = 0
    for name, email, title, company, status, tags in specs:
        contact = _find_contact_by_email(crm, email)
        if contact is None:
            contact = crm.add_contact(name, email, title, company, status, tags)
            created_contacts += 1
        else:
            for tag in _split_tags(tags):
                crm.add_contact_tag(contact, tag)
        note_body = f"Initial discovery conversation with {name}."
        if all(note.body != note_body for note in contact.notes):
            crm.add_note(contact, note_body)
        contacts.append(contact)

    task_specs = [
        (0, "Send pricing follow-up", "Send pricing options and ask which plan fits their rollout timeline.", today - timedelta(days=2), False),
        (1, "Schedule technical review", "Find a time for their data lead to review integration requirements.", today + timedelta(days=4), False),
        (2, "Confirm renewal date", "Confirm the renewal date and who needs to approve the next term.", today + timedelta(days=8), False),
        (3, "Share implementation notes", "Send the implementation summary from the clinic workflow discussion.", today - timedelta(days=6), True),
        (4, "Check contract status", "Ask whether finance has reviewed the draft contract.", today - timedelta(days=1), False),
        (5, "Send recap from discovery call", "Send a short recap and next-step proposal from the discovery call.", today + timedelta(days=2), True),
        (6, "Follow up after trial period", "Check how the trial went and whether they need help rolling it out.", today + timedelta(days=10), False),
        (9, "Schedule technical review", "Book a technical review for access controls and reporting needs.", today - timedelta(days=3), False),
        (10, "Send pricing follow-up", "Send a concise pricing note for the independent consultant package.", today + timedelta(days=1), False),
    ]
    for contact_index, title, description, due_date, completed in task_specs:
        contact = contacts[contact_index]
        existing_task = _find_task(contact, title)
        if existing_task is None:
            task = crm.add_task(contact, title, due_date, description)
            created_tasks += 1
        else:
            task = existing_task
            if not getattr(task, "description", ""):
                task.description = description
        if completed:
            crm.complete_task(contact, task)

    return {
        "companies": len(companies),
        "contacts": len(contacts),
        "created_companies": created_companies,
        "created_contacts": created_contacts,
        "created_tasks": created_tasks,
    }


def _find_contact_by_email(crm: CRM, email: str) -> Contact | None:
    normalized = email.strip().lower()
    for contact in crm.contacts(include_archived=True):
        if contact.email.strip().lower() == normalized:
            return contact
    return None


def _find_task(contact: Contact, title: str):
    for task in contact.tasks:
        if task.title == title:
            return task
    return None


def _split_tags(tags: str) -> list[str]:
    return [tag.strip() for tag in tags.split(",") if tag.strip()]
