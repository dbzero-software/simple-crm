"""NiceGUI entrypoint for the Simple CRM tutorial app."""

from __future__ import annotations

import argparse
import secrets
from datetime import date, datetime
from pathlib import Path

import dbzero as db0
from nicegui import app as nicegui_app
from nicegui import ui

from simple_crm.config import DATA_PREFIX, DEFAULT_DBZERO_ROOT
from simple_crm.models import (
    CONTACT_STATUSES,
    CRM,
    Company,
    Contact,
    TASK_FILTER_ALL,
    TASK_FILTER_OPEN,
    TASK_FILTER_OVERDUE,
)
from simple_crm.seed import seed_sample_data

TASK_FILTER_LABELS = {
    TASK_FILTER_ALL: "All contacts",
    TASK_FILTER_OPEN: "Open tasks",
    TASK_FILTER_OVERDUE: "Overdue tasks",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple CRM")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=8081, help="Listen port")
    parser.add_argument("--dbzero-root", default=str(DEFAULT_DBZERO_ROOT), help="dbzero storage directory")
    args, _ = parser.parse_known_args()
    return args


ARGS = parse_args()
CRM_ROOT: CRM | None = None


def initialize_crm(dbzero_root: str | Path = DEFAULT_DBZERO_ROOT) -> CRM:
    """Initialize dbzero and return the durable CRM singleton."""
    root = Path(dbzero_root)
    root.mkdir(parents=True, exist_ok=True)
    db0.init(str(root), prefix=DATA_PREFIX, autocommit=True)
    return CRM()


@nicegui_app.on_startup
def startup() -> None:
    global CRM_ROOT  # pylint: disable=global-statement
    CRM_ROOT = initialize_crm(ARGS.dbzero_root)


@nicegui_app.on_shutdown
def shutdown() -> None:
    db0.close()


def get_crm() -> CRM:
    if CRM_ROOT is None:
        raise RuntimeError("CRM is not initialized.")
    return CRM_ROOT


def parse_due_date(value: str | None) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Use YYYY-MM-DD for due dates.") from exc


def format_date(value: date | datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d")


def status_label(status: str) -> str:
    return status.replace("_", " ").title()


def task_filter_from_label(label: str) -> str:
    for value, option_label in TASK_FILTER_LABELS.items():
        if option_label == label:
            return value
    return TASK_FILTER_ALL


@ui.page("/")
def crm_page() -> None:
    crm = get_crm()
    state: dict[str, object] = {
        "selected_contact": None,
        "query": "",
        "company": None,
        "status": None,
        "tag": None,
        "task_filter": TASK_FILTER_ALL,
    }

    ui.colors(primary="#2563eb", secondary="#0f766e", accent="#d97706", positive="#059669", negative="#dc2626")
    ui.add_head_html(
        """
        <style>
        body { background: #f8fafc; }
        .crm-shell { min-height: 100vh; }
        .crm-panel { background: white; border: 1px solid #e5e7eb; border-radius: 6px; }
        .crm-row { border: 1px solid #e5e7eb; border-radius: 6px; background: white; }
        .crm-row-selected { border-color: #2563eb; box-shadow: 0 0 0 1px #2563eb inset; }
        .crm-chip { border-radius: 999px; padding: 2px 8px; font-size: 12px; background: #eef2ff; color: #3730a3; }
        </style>
        """
    )

    def selected_contact() -> Contact | None:
        contact = state["selected_contact"]
        return contact if isinstance(contact, Contact) else None

    def refresh_all() -> None:
        refresh_metrics()
        refresh_filters()
        refresh_contact_form()
        refresh_contact_list()
        refresh_detail()

    def notify_error(message: str) -> None:
        ui.notify(message, position="top", type="negative")

    def company_options() -> dict[str, object | None]:
        options: dict[str, object | None] = {"No company": None}
        for company in crm.companies():
            options[company.name] = company
        return options

    def refresh_metrics() -> None:
        metrics_container.clear()
        counts = crm.counts()
        metrics = [
            ("Companies", counts["companies"], "#eff6ff"),
            ("Contacts", counts["contacts"], "#f0fdf4"),
            ("Active", counts["active_customers"], "#ecfdf5"),
            ("Leads", counts["leads"], "#fefce8"),
            ("Open tasks", counts["open_tasks"], "#fffbeb"),
            ("Overdue", counts["overdue_tasks"], "#fef2f2"),
        ]
        with metrics_container:
            for label, value, background in metrics:
                with ui.column().classes("crm-panel px-4 py-3 gap-0 min-w-[112px]").style(f"background: {background};"):
                    ui.label(str(value)).classes("text-xl font-semibold text-gray-900")
                    ui.label(label).classes("text-xs text-gray-600")

    def refresh_filters() -> None:
        filters_container.clear()
        with filters_container:
            ui.label("Filters").classes("text-sm font-semibold text-gray-700")

            def update_query(event) -> None:
                state["query"] = event.value or ""
                refresh_contact_list()

            ui.input("Search", value=str(state["query"]), on_change=update_query).props("dense outlined clearable").classes("w-full")

            company_filter_options = {"All companies": None, **{company.name: company for company in crm.companies()}}

            def update_company(label: str) -> None:
                state["company"] = company_filter_options.get(label)
                refresh_contact_list()

            current_company = state["company"]
            current_company_label = current_company.name if isinstance(current_company, Company) else "All companies"
            if current_company is None:
                current_company_label = "All companies"
            ui.select(list(company_filter_options.keys()), label="Company", value=current_company_label, on_change=lambda e: update_company(e.value)).props(
                "dense outlined"
            ).classes("w-full")

            status_options = ["All statuses", *[status_label(status) for status in CONTACT_STATUSES]]

            def update_status(label: str) -> None:
                reverse = {status_label(status): status for status in CONTACT_STATUSES}
                state["status"] = reverse.get(label)
                refresh_contact_list()

            current_status = state["status"]
            ui.select(
                status_options,
                label="Status",
                value=status_label(current_status) if isinstance(current_status, str) else "All statuses",
                on_change=lambda e: update_status(e.value),
            ).props("dense outlined").classes("w-full")

            tag_options = ["All tags", *crm.available_tags()]

            def update_tag(label: str) -> None:
                state["tag"] = None if label == "All tags" else label
                refresh_contact_list()

            ui.select(
                tag_options,
                label="Tag",
                value=state["tag"] or "All tags",
                on_change=lambda e: update_tag(e.value),
            ).props("dense outlined").classes("w-full")

            def update_task_filter(label: str) -> None:
                state["task_filter"] = task_filter_from_label(label)
                refresh_contact_list()

            ui.select(
                list(TASK_FILTER_LABELS.values()),
                label="Task view",
                value=TASK_FILTER_LABELS[state["task_filter"]],
                on_change=lambda e: update_task_filter(e.value),
            ).props("dense outlined").classes("w-full")

    def refresh_contact_form() -> None:
        contact_form_container.clear()
        with contact_form_container:
            ui.label("New contact").classes("text-sm font-semibold text-gray-700")
            name_input = ui.input("Name").props("dense outlined").classes("w-full")
            email_input = ui.input("Email").props("dense outlined").classes("w-full")
            title_input = ui.input("Title").props("dense outlined").classes("w-full")
            contact_company_options = company_options()
            company_select = ui.select(list(contact_company_options.keys()), label="Company", value="No company").props("dense outlined").classes("w-full")
            status_select = ui.select([status_label(status) for status in CONTACT_STATUSES], label="Status", value="Lead").props("dense outlined").classes("w-full")
            tags_input = ui.input("Tags").props("dense outlined").classes("w-full")

            def create_contact() -> None:
                try:
                    reverse_status = {status_label(status): status for status in CONTACT_STATUSES}
                    contact = crm.add_contact(
                        name_input.value or "",
                        email_input.value or "",
                        title_input.value or "",
                        contact_company_options.get(company_select.value),
                        reverse_status.get(status_select.value, "lead"),
                        tags_input.value or "",
                    )
                except ValueError as exc:
                    notify_error(str(exc))
                    return
                state["selected_contact"] = contact
                ui.notify("Contact added", position="top", type="positive")
                refresh_all()

            ui.button("Add contact", icon="person_add", on_click=create_contact).props("color=primary unelevated").classes("w-full")

    def refresh_contact_list() -> None:
        list_container.clear()
        contacts = crm.search_contacts(
            query=str(state["query"]),
            company=state["company"] if state["company"] is not None else None,
            status=state["status"] if isinstance(state["status"], str) else None,
            tag=state["tag"] if isinstance(state["tag"], str) else None,
            task_filter=str(state["task_filter"]),
        )
        selected = selected_contact()

        with list_container:
            ui.label(f"{len(contacts)} contacts").classes("text-sm text-gray-600")
            if not contacts:
                ui.label("No contacts match the current filters.").classes("text-sm text-gray-500 italic")
                return
            for contact in contacts:
                is_selected = selected is contact
                row_class = "crm-row-selected" if is_selected else ""
                with ui.column().classes(f"crm-row {row_class} w-full p-3 gap-2 cursor-pointer").on(
                    "click", lambda _, c=contact: select_contact(c)
                ):
                    with ui.row().classes("w-full items-start justify-between gap-3"):
                        with ui.column().classes("gap-0"):
                            ui.label(contact.name).classes("text-base font-semibold text-gray-900")
                            company_name = contact.company.name if contact.company else "No company"
                            ui.label(f"{company_name} · {contact.title or 'No title'}").classes("text-xs text-gray-600")
                        ui.label(status_label(contact.status)).classes("text-xs font-medium text-blue-700")
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        for tag in sorted(contact.tags):
                            ui.label(tag).classes("crm-chip")
                    with ui.row().classes("items-center gap-4 text-xs text-gray-600"):
                        ui.label(f"Last touch: {format_date(contact.last_touch_at)}")
                        ui.label(f"Next: {format_date(contact.next_task_due_at)}")
                        ui.label(f"Open: {contact.open_task_count}")

    def select_contact(contact: Contact) -> None:
        state["selected_contact"] = contact
        refresh_contact_list()
        refresh_detail()

    def refresh_detail() -> None:
        detail_container.clear()
        contact = selected_contact()
        with detail_container:
            if contact is None:
                ui.label("Select a contact").classes("text-lg font-semibold text-gray-900")
                ui.label("Choose a contact from the list to view notes, tasks, tags, and follow-up actions.").classes(
                    "text-sm text-gray-600"
                )
                return

            with ui.row().classes("w-full items-start justify-between gap-3"):
                with ui.column().classes("gap-0"):
                    ui.label(contact.name).classes("text-lg font-semibold text-gray-900")
                    ui.label(contact.email or "No email").classes("text-sm text-gray-600")
                    company_name = contact.company.name if contact.company else "No company"
                    ui.label(f"{company_name} · {contact.title or 'No title'}").classes("text-sm text-gray-600")
                with ui.row().classes("items-center gap-1"):
                    ui.button("Edit", icon="edit", on_click=lambda: edit_contact_basics(contact)).props("flat color=primary")
                    ui.button("Archive", icon="archive", on_click=lambda: archive_selected(contact)).props("flat color=negative")

            ui.separator()
            render_status_editor(contact)
            render_tag_editor(contact)
            ui.separator()
            render_note_panel(contact)
            ui.separator()
            render_task_panel(contact)

    def render_status_editor(contact: Contact) -> None:
        status_select = ui.select(
            [status_label(status) for status in CONTACT_STATUSES],
            label="Relationship status",
            value=status_label(contact.status),
        ).props("dense outlined").classes("w-full")

        def save_status() -> None:
            reverse_status = {status_label(status): status for status in CONTACT_STATUSES}
            crm.change_contact_status(contact, reverse_status[status_select.value])
            refresh_all()

        ui.button("Save status", icon="save", on_click=save_status).props("size=sm color=primary unelevated")

    def render_tag_editor(contact: Contact) -> None:
        ui.label("Tags").classes("text-sm font-semibold text-gray-700")
        with ui.row().classes("items-center gap-2 flex-wrap"):
            for tag in sorted(contact.tags):
                with ui.row().classes("items-center gap-1 crm-chip"):
                    ui.label(tag)
                    ui.button(icon="close", on_click=lambda _, t=tag: remove_tag(contact, t)).props("flat dense round size=xs")
        tag_input = ui.input("Add tag").props("dense outlined").classes("w-full")

        def add_tag() -> None:
            crm.add_contact_tag(contact, tag_input.value or "")
            refresh_all()

        ui.button("Add tag", icon="sell", on_click=add_tag).props("size=sm color=primary unelevated")

    def render_note_panel(contact: Contact) -> None:
        ui.label("Notes").classes("text-sm font-semibold text-gray-700")
        note_input = ui.textarea("New note").props("outlined autogrow").classes("w-full")

        def add_note() -> None:
            try:
                crm.add_note(contact, note_input.value or "")
            except ValueError as exc:
                notify_error(str(exc))
                return
            refresh_all()

        ui.button("Add note", icon="note_add", on_click=add_note).props("size=sm color=primary unelevated")
        if not contact.notes:
            ui.label("No notes yet.").classes("text-sm text-gray-500 italic")
        for note in sorted(contact.notes, key=lambda item: item.created_at, reverse=True):
            with ui.column().classes("w-full p-2 bg-gray-50 rounded gap-1"):
                ui.label(format_date(note.created_at)).classes("text-xs text-gray-500")
                ui.label(note.body).classes("text-sm text-gray-800")

    def render_task_panel(contact: Contact) -> None:
        ui.label("Tasks").classes("text-sm font-semibold text-gray-700")
        task_title = ui.input("Task title").props("dense outlined").classes("w-full")
        due_date = ui.input("Due date", placeholder="YYYY-MM-DD").props("dense outlined").classes("w-full")

        def add_task() -> None:
            try:
                crm.add_task(contact, task_title.value or "", parse_due_date(due_date.value))
            except ValueError as exc:
                notify_error(str(exc))
                return
            refresh_all()

        ui.button("Add task", icon="add_task", on_click=add_task).props("size=sm color=primary unelevated")
        if not contact.tasks:
            ui.label("No tasks yet.").classes("text-sm text-gray-500 italic")
        for task in sorted(contact.tasks, key=lambda item: (item.completed, item.due_date or date.max, item.created_at)):
            overdue = not task.completed and task.due_date is not None and task.due_date < date.today()
            color = "text-green-700" if task.completed else "text-red-700" if overdue else "text-amber-700"
            with ui.row().classes("w-full items-center justify-between gap-2 p-2 bg-gray-50 rounded"):
                with ui.column().classes("gap-0"):
                    ui.label(task.title).classes(f"text-sm font-medium {color}")
                    ui.label(f"Due: {format_date(task.due_date)}").classes("text-xs text-gray-500")
                if task.completed:
                    ui.button("Reopen", icon="undo", on_click=lambda _, t=task: reopen_task(contact, t)).props("flat size=sm")
                else:
                    ui.button("Done", icon="check", on_click=lambda _, t=task: complete_task(contact, t)).props("flat size=sm color=positive")

    def remove_tag(contact: Contact, tag: str) -> None:
        crm.remove_contact_tag(contact, tag)
        refresh_all()

    def complete_task(contact: Contact, task) -> None:
        crm.complete_task(contact, task)
        refresh_all()

    def reopen_task(contact: Contact, task) -> None:
        crm.reopen_task(contact, task)
        refresh_all()

    def archive_selected(contact: Contact) -> None:
        crm.archive_contact(contact)
        state["selected_contact"] = None
        refresh_all()

    def edit_contact_basics(contact: Contact) -> None:
        contact_company_options = company_options()
        current_company_label = contact.company.name if contact.company else "No company"
        if current_company_label not in contact_company_options:
            contact_company_options[current_company_label] = contact.company

        with ui.dialog() as dialog, ui.card().classes("w-[460px] max-w-full"):
            ui.label("Edit contact").classes("text-lg font-semibold")
            name = ui.input("Name", value=contact.name).props("dense outlined").classes("w-full")
            email = ui.input("Email", value=contact.email).props("dense outlined").classes("w-full")
            title = ui.input("Title", value=contact.title).props("dense outlined").classes("w-full")
            company_select = ui.select(
                list(contact_company_options.keys()),
                label="Company",
                value=current_company_label,
            ).props("dense outlined").classes("w-full")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                def save() -> None:
                    try:
                        crm.update_contact_basics(
                            contact,
                            name.value or "",
                            email.value or "",
                            title.value or "",
                            contact_company_options.get(company_select.value),
                        )
                    except ValueError as exc:
                        notify_error(str(exc))
                        return
                    dialog.close()
                    refresh_all()

                ui.button("Save", icon="save", on_click=save).props("color=primary unelevated")
        dialog.open()

    def seed_data() -> None:
        result = seed_sample_data(crm)
        created = result["created_companies"] + result["created_contacts"] + result["created_tasks"]
        if created:
            message = (
                f"Seeded {result['created_contacts']} contacts, "
                f"{result['created_companies']} companies, and {result['created_tasks']} tasks"
            )
        else:
            message = "Sample data was already present"
        ui.notify(message, position="top", type="positive")
        refresh_all()

    def create_checkpoint() -> None:
        checkpoint = crm.create_checkpoint(f"Checkpoint {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        ui.notify(f"Saved {checkpoint.label}", position="top", type="positive")
        refresh_metrics()

    def add_company() -> None:
        with ui.dialog() as dialog, ui.card().classes("w-[420px] max-w-full"):
            ui.label("Add company").classes("text-lg font-semibold")
            name = ui.input("Name").props("dense outlined").classes("w-full")
            industry = ui.input("Industry").props("dense outlined").classes("w-full")
            website = ui.input("Website").props("dense outlined").classes("w-full")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=dialog.close).props("flat")

                def save() -> None:
                    try:
                        crm.add_company(name.value or "", industry.value or "", website.value or "")
                    except ValueError as exc:
                        notify_error(str(exc))
                        return
                    dialog.close()
                    refresh_all()

                ui.button("Save", icon="save", on_click=save).props("color=primary unelevated")
        dialog.open()

    with ui.header().classes("bg-white text-gray-900 border-b border-gray-200"):
        with ui.row().classes("w-full items-center gap-3 px-4 py-2"):
            ui.label("Simple CRM").classes("text-lg font-semibold")
            ui.space()
            ui.button("Add company", icon="business", on_click=add_company).props("flat")
            ui.button("Seed data", icon="dataset", on_click=seed_data).props("flat")
            ui.button("Checkpoint", icon="bookmark_add", on_click=create_checkpoint).props("flat")

    with ui.row().classes("crm-shell w-full flex-nowrap items-start gap-4 p-4"):
        with ui.column().classes("crm-panel w-[300px] shrink-0 p-4 gap-5"):
            filters_container = ui.column().classes("w-full gap-3")
            ui.separator()
            contact_form_container = ui.column().classes("w-full gap-3")
        with ui.column().classes("flex-grow min-w-0 gap-4"):
            metrics_container = ui.row().classes("w-full gap-3")
            list_container = ui.column().classes("w-full gap-2")
        with ui.column().classes("crm-panel w-[380px] shrink-0 p-4 gap-3"):
            detail_container = ui.column().classes("w-full gap-3")

    refresh_all()


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="Simple CRM",
        host=ARGS.host,
        port=ARGS.port,
        reload=False,
        show=False,
        show_welcome_message=False,
        storage_secret=secrets.token_hex(32),
    )
