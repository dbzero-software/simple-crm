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
        "selected_task": None,
        "query": "",
        "company": None,
        "status": None,
        "tag": None,
        "task_filter": TASK_FILTER_ALL,
        "list_view": "contacts",
        "task_list_filter": TASK_FILTER_OPEN,
        "page": 1,
        "page_size": 10,
    }

    ui.colors(primary="#2563eb", secondary="#0f766e", accent="#d97706", positive="#059669", negative="#dc2626")
    ui.add_head_html(
        """
        <style>
        :root {
            --crm-bg: #f4f6f8;
            --crm-surface: #ffffff;
            --crm-surface-soft: #f8fafc;
            --crm-text: #111827;
            --crm-muted: #667085;
            --crm-border: #d9e0e8;
            --crm-border-soft: #e7ecf2;
            --crm-primary: #1f5eff;
            --crm-primary-dark: #1747c7;
            --crm-shadow: 0 16px 42px rgba(15, 23, 42, 0.08);
            --crm-shadow-soft: 0 1px 2px rgba(15, 23, 42, 0.05), 0 10px 28px rgba(15, 23, 42, 0.05);
        }
        body {
            background:
                radial-gradient(circle at 12% -10%, rgba(31, 94, 255, 0.09), transparent 26rem),
                linear-gradient(180deg, #fbfcfe 0%, var(--crm-bg) 44%, #eef2f6 100%);
            color: var(--crm-text);
            font-feature-settings: "cv02", "cv03", "cv04", "cv11";
        }
        .q-page-container { background: transparent; }
        .crm-shell { min-height: 100vh; }
        .crm-layout {
            display: grid;
            grid-template-columns: minmax(268px, 304px) minmax(390px, 1fr) minmax(330px, 390px);
            gap: 18px;
            align-items: start;
            width: 100%;
            max-width: 1560px;
            margin: 0 auto;
        }
        .crm-topbar {
            background: rgba(255, 255, 255, 0.92);
            border-bottom: 1px solid rgba(217, 224, 232, 0.9);
            box-shadow: 0 1px 0 rgba(255, 255, 255, 0.8) inset, 0 10px 30px rgba(15, 23, 42, 0.05);
            backdrop-filter: blur(16px);
        }
        .crm-brand {
            min-width: 172px;
        }
        .crm-brand-mark {
            width: 34px;
            height: 34px;
            border-radius: 8px;
            background: linear-gradient(135deg, #1f5eff 0%, #0f766e 100%);
            box-shadow: 0 10px 22px rgba(31, 94, 255, 0.24);
            position: relative;
        }
        .crm-brand-mark::after {
            content: "";
            position: absolute;
            inset: 9px;
            border: 2px solid rgba(255, 255, 255, 0.92);
            border-radius: 5px;
        }
        .crm-panel, .crm-row, .crm-empty {
            background: rgba(255, 255, 255, 0.96);
            border: 1px solid var(--crm-border-soft);
            border-radius: 8px;
            box-shadow: var(--crm-shadow-soft);
        }
        .crm-panel { overflow: hidden; }
        .crm-row {
            position: relative;
            transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease, background 140ms ease;
        }
        .crm-row:hover {
            background: #ffffff;
            border-color: rgba(31, 94, 255, 0.32);
            box-shadow: var(--crm-shadow);
            transform: translateY(-1px);
        }
        .crm-row-selected {
            border-color: rgba(31, 94, 255, 0.72);
            box-shadow: 0 0 0 1px rgba(31, 94, 255, 0.55) inset, var(--crm-shadow-soft);
        }
        .crm-row-selected::before {
            content: "";
            position: absolute;
            left: 0;
            top: 12px;
            bottom: 12px;
            width: 3px;
            border-radius: 0 999px 999px 0;
            background: var(--crm-primary);
        }
        .crm-chip {
            border-radius: 999px;
            padding: 3px 9px;
            font-size: 12px;
            line-height: 17px;
            background: #eef4ff;
            color: #2447a9;
            border: 1px solid rgba(36, 71, 169, 0.11);
            font-weight: 600;
            max-width: 160px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .crm-chip-status { background: #eef4ff; color: #1d4ed8; border-color: #cfe0ff; }
        .crm-chip-muted { background: #f4f6f8; color: #526071; border-color: #e1e7ef; }
        .crm-chip-open { background: #fff7e6; color: #a15c07; border-color: #f7dfae; }
        .crm-chip-overdue { background: #fff1f2; color: #b42318; border-color: #ffd0d5; }
        .crm-chip-complete { background: #ecfdf3; color: #067647; border-color: #b7efc8; }
        .crm-metric {
            min-width: 132px;
            justify-content: flex-start;
            text-align: left;
            border: 1px solid var(--crm-border-soft);
            border-radius: 8px;
            box-shadow: var(--crm-shadow-soft);
            font-weight: 700;
            transition: border-color 140ms ease, box-shadow 140ms ease, transform 140ms ease;
        }
        .crm-metric:hover {
            border-color: rgba(31, 94, 255, 0.28);
            box-shadow: var(--crm-shadow);
            transform: translateY(-1px);
        }
        .crm-section-title {
            color: #2f3b4a;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0;
            text-transform: uppercase;
        }
        .crm-note, .crm-task {
            background: var(--crm-surface-soft);
            border: 1px solid var(--crm-border-soft);
            border-radius: 8px;
        }
        .crm-task { align-items: stretch; }
        .crm-empty {
            background:
                linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98));
        }
        .crm-action .q-btn {
            border-radius: 8px;
        }
        .crm-header-search .q-field__control,
        .crm-panel .q-field__control,
        .crm-dialog-card .q-field__control {
            border-radius: 8px;
            background: #ffffff;
        }
        .crm-header-search .q-field--outlined .q-field__control::before,
        .crm-panel .q-field--outlined .q-field__control::before,
        .crm-dialog-card .q-field--outlined .q-field__control::before {
            border-color: var(--crm-border);
        }
        .crm-header-search .q-field--focused .q-field__control::after,
        .crm-panel .q-field--focused .q-field__control::after,
        .crm-dialog-card .q-field--focused .q-field__control::after {
            border-color: var(--crm-primary);
            border-width: 1px;
        }
        .crm-dialog-card {
            border-radius: 8px;
            box-shadow: 0 24px 70px rgba(15, 23, 42, 0.22);
        }
        .crm-subtle-divider {
            background: linear-gradient(90deg, transparent, #dfe6ee 18%, #dfe6ee 82%, transparent);
        }
        @media (max-width: 1100px) {
            .crm-layout { grid-template-columns: minmax(240px, 300px) minmax(0, 1fr); }
            .crm-detail { grid-column: 1 / -1; }
        }
        @media (max-width: 760px) {
            .crm-layout { grid-template-columns: minmax(0, 1fr); gap: 12px; }
            .crm-page-padding { padding: 12px; }
            .crm-header-row { align-items: stretch; }
            .crm-brand { min-width: 100%; }
            .crm-header-search { width: 100%; }
            .crm-header-search .q-field { width: 100%; }
            .crm-metric { min-width: calc(50% - 6px); flex: 1 1 calc(50% - 6px); }
            .crm-row:hover { transform: none; }
        }
        </style>
        """
    )

    def selected_contact() -> Contact | None:
        contact = state["selected_contact"]
        return contact if isinstance(contact, Contact) else None

    def selected_task():
        contact = selected_contact()
        task = state["selected_task"]
        if contact is not None and task in contact.tasks:
            return task
        return None

    def refresh_all() -> None:
        refresh_header_search()
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

    def reset_page() -> None:
        state["page"] = 1

    def task_state(contact: Contact) -> tuple[str, str, str]:
        overdue_count = len(contact.overdue_tasks())
        if overdue_count:
            return (f"{overdue_count} overdue", "crm-chip-overdue", "text-red-700")
        if contact.open_task_count:
            return (f"{contact.open_task_count} open", "crm-chip-open", "text-amber-700")
        return ("No open tasks", "crm-chip-muted", "text-slate-500")

    def task_status(task) -> tuple[str, str, str]:
        if task.completed:
            return ("Completed", "crm-chip-complete", "text-green-700")
        if task.is_overdue():
            return ("Overdue", "crm-chip-overdue", "text-red-700")
        return ("Open", "crm-chip-open", "text-amber-700")

    def status_chip(status: str) -> None:
        ui.label(status_label(status)).classes("crm-chip crm-chip-status")

    def refresh_metrics() -> None:
        metrics_container.clear()
        counts = crm.counts()
        metrics = [
            ("Companies", counts["companies"], "#eff6ff", show_companies),
            ("Contacts", counts["contacts"], "#f0fdf4", lambda: show_contacts()),
            ("Active", counts["active_customers"], "#ecfdf5", lambda: show_contacts(status="active_customer")),
            ("Leads", counts["leads"], "#fefce8", lambda: show_contacts(status="lead")),
            ("Open tasks total", counts["open_tasks"], "#fffbeb", lambda: show_tasks(TASK_FILTER_OPEN)),
            ("Overdue", counts["overdue_tasks"], "#fef2f2", lambda: show_tasks(TASK_FILTER_OVERDUE)),
        ]
        with metrics_container:
            for label, value, background, on_click in metrics:
                ui.button(f"{value} {label}", on_click=lambda _, handler=on_click: handler()).props("flat no-caps").classes(
                    "crm-metric px-4 py-3 text-slate-900"
                ).style(f"background: {background};")

    def refresh_header_search() -> None:
        header_search_container.clear()
        label = "Search companies" if state["list_view"] == "companies" else "Search contacts"
        with header_search_container:
            ui.input(label, value=str(state["query"]), on_change=update_query).props("dense outlined clearable").classes(
                "w-[320px] max-w-full"
            )

    def show_contacts(status: str | None = None) -> None:
        state["list_view"] = "contacts"
        state["selected_task"] = None
        state["query"] = ""
        state["company"] = None
        state["status"] = status
        state["tag"] = None
        state["task_filter"] = TASK_FILTER_ALL
        reset_page()
        refresh_header_search()
        refresh_filters()
        refresh_contact_list()

    def show_companies() -> None:
        state["list_view"] = "companies"
        state["selected_task"] = None
        reset_page()
        refresh_header_search()
        refresh_contact_list()

    def show_tasks(task_filter: str) -> None:
        state["list_view"] = "tasks"
        state["task_list_filter"] = task_filter
        state["selected_task"] = None
        reset_page()
        refresh_header_search()
        refresh_contact_list()

    def show_company_contacts(company: Company) -> None:
        state["list_view"] = "contacts"
        state["selected_task"] = None
        state["query"] = ""
        state["company"] = company
        state["status"] = None
        state["tag"] = None
        state["task_filter"] = TASK_FILTER_ALL
        reset_page()
        refresh_header_search()
        refresh_filters()
        refresh_contact_list()

    def update_query(event) -> None:
        state["selected_task"] = None
        state["query"] = event.value or ""
        reset_page()
        if state["list_view"] != "companies":
            state["list_view"] = "contacts"
            refresh_header_search()
        refresh_contact_list()

    def refresh_filters() -> None:
        filters_container.clear()
        with filters_container:
            ui.label("Filters").classes("crm-section-title")

            company_filter_options = {"All companies": None, **{company.name: company for company in crm.companies()}}

            def update_company(label: str) -> None:
                state["list_view"] = "contacts"
                state["selected_task"] = None
                state["company"] = company_filter_options.get(label)
                reset_page()
                refresh_header_search()
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
                state["list_view"] = "contacts"
                state["selected_task"] = None
                reverse = {status_label(status): status for status in CONTACT_STATUSES}
                state["status"] = reverse.get(label)
                reset_page()
                refresh_header_search()
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
                state["list_view"] = "contacts"
                state["selected_task"] = None
                state["tag"] = None if label == "All tags" else label
                reset_page()
                refresh_header_search()
                refresh_contact_list()

            ui.select(
                tag_options,
                label="Tag",
                value=state["tag"] or "All tags",
                on_change=lambda e: update_tag(e.value),
            ).props("dense outlined").classes("w-full")

            def update_task_filter(label: str) -> None:
                state["list_view"] = "contacts"
                state["selected_task"] = None
                state["task_filter"] = task_filter_from_label(label)
                reset_page()
                refresh_header_search()
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
            ui.label("New contact").classes("crm-section-title")
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
                state["selected_task"] = None
                ui.notify("Contact added", position="top", type="positive")
                refresh_all()

            ui.button("Add contact", icon="person_add", on_click=create_contact).props("color=primary unelevated").classes("w-full")

    def refresh_contact_list() -> None:
        list_container.clear()
        if state["list_view"] == "companies":
            render_company_list()
            return
        if state["list_view"] == "tasks":
            render_task_list(str(state["task_list_filter"]))
            return
        page_result = crm.search_contacts_page(
            query=str(state["query"]),
            company=state["company"] if state["company"] is not None else None,
            status=state["status"] if isinstance(state["status"], str) else None,
            tag=state["tag"] if isinstance(state["tag"], str) else None,
            task_filter=str(state["task_filter"]),
            page=int(state["page"]),
            page_size=int(state["page_size"]),
        )
        contacts = page_result.items
        selected = selected_contact()

        with list_container:
            if page_result.total == 0 and not any([state["query"], state["company"], state["status"], state["tag"]]):
                render_empty_contacts()
                return

            render_list_heading(f"{page_result.total} contacts")
            if not contacts:
                ui.label("No contacts match the current filters.").classes("crm-empty w-full p-4 text-sm text-gray-500")
                return
            for contact in contacts:
                is_selected = selected is contact
                row_class = "crm-row-selected" if is_selected else ""
                with ui.column().classes(f"crm-row {row_class} w-full p-4 gap-3 cursor-pointer").on(
                    "click", lambda _, c=contact: select_contact(c)
                ):
                    with ui.row().classes("w-full items-start justify-between gap-3"):
                        with ui.column().classes("gap-0 min-w-0"):
                            ui.label(contact.name).classes("text-base font-semibold text-slate-950")
                            company_name = contact.company.name if contact.company else "No company"
                            ui.label(f"{company_name} · {contact.title or 'No title'}").classes("text-xs text-slate-500 break-words")
                        status_chip(contact.status)
                    with ui.row().classes("items-center gap-2 flex-wrap"):
                        for tag in sorted(contact.tags):
                            ui.label(tag).classes("crm-chip")
                    task_label, task_chip_class, task_text_class = task_state(contact)
                    with ui.row().classes("items-center gap-2 flex-wrap text-xs text-slate-500"):
                        ui.label(f"Last touch: {format_date(contact.last_touch_at)}")
                        ui.label(f"Next: {format_date(contact.next_task_due_at)}").classes(task_text_class)
                        ui.label(task_label).classes(f"crm-chip {task_chip_class}")
            render_pagination(page_result)

    def render_list_heading(label: str) -> None:
        counts = crm.counts()
        with ui.column().classes("crm-panel w-full p-4 gap-2"):
            with ui.row().classes("w-full items-center justify-between gap-3"):
                ui.label(label).classes("text-sm font-semibold text-slate-700")
                if counts["overdue_tasks"]:
                    ui.label(f"{counts['overdue_tasks']} overdue").classes("crm-chip crm-chip-overdue")
                else:
                    ui.label("No overdue tasks").classes("crm-chip crm-chip-complete")
            ui.label(f"{counts['open_tasks']} open tasks · {counts['active_customers']} active customers").classes("text-xs text-slate-500")

    def render_empty_contacts() -> None:
        with ui.column().classes("crm-empty w-full p-6 gap-4"):
            ui.label("Start with sample CRM data").classes("text-lg font-semibold text-slate-950")
            ui.label("Load a realistic set of companies, contacts, notes, and follow-up tasks, or add your first contact from the form.").classes(
                "text-sm text-slate-500"
            )
            with ui.row().classes("items-center gap-2 flex-wrap"):
                ui.button("Seed data", icon="dataset", on_click=seed_data).props("color=primary unelevated")
                ui.button("Add contact", icon="person_add", on_click=lambda: ui.notify("Use the New contact form on this page.", position="top")).props(
                    "flat color=primary"
                )

    def render_company_list() -> None:
        page_result = crm.search_companies_page(str(state["query"]), page=int(state["page"]), page_size=int(state["page_size"]))
        companies = page_result.items
        with list_container:
            render_list_heading(f"{page_result.total} companies")
            if not companies:
                ui.label("No companies yet.").classes("crm-empty w-full p-4 text-sm text-gray-500")
                return
            for company in companies:
                contacts = crm.search_contacts(company=company, include_archived=True)
                with ui.column().classes("crm-row w-full p-4 gap-2"):
                    ui.button(company.name, on_click=lambda _, c=company: show_company_contacts(c)).props("flat dense no-caps").classes(
                        "self-start text-base font-semibold text-slate-950 px-0"
                    )
                    ui.label(company.industry or "No industry").classes("text-xs text-slate-500")
                    ui.label(company.website or "No website").classes("text-xs text-slate-500")
                    ui.label(f"{len(contacts)} contacts").classes("text-xs text-slate-500")
            render_pagination(page_result)

    def render_task_list(task_filter: str) -> None:
        today = date.today()
        page_result = crm.task_rows_page(task_filter, today=today, page=int(state["page"]), page_size=int(state["page_size"]))
        rows = page_result.items
        label = "overdue tasks" if task_filter == TASK_FILTER_OVERDUE else "open tasks"
        with list_container:
            render_list_heading(f"{page_result.total} {label}")
            if not rows:
                ui.label(f"No {label}.").classes("crm-empty w-full p-4 text-sm text-gray-500")
                return
            for contact, task in rows:
                task_label, task_chip_class, color = task_status(task)
                company_name = contact.company.name if contact.company else "No company"
                with ui.column().classes("crm-row w-full p-4 gap-2"):
                    ui.button(task.title, on_click=lambda _, c=contact, t=task: select_task(c, t)).props("flat dense no-caps").classes(
                        f"self-start text-base font-semibold {color} px-0"
                    )
                    ui.label(f"{contact.name} · {company_name}").classes("text-xs text-slate-500")
                    description = getattr(task, "description", "")
                    if description:
                        ui.label(description).classes("text-xs text-slate-700")
                    ui.label(f"{task_label} · Due: {format_date(task.due_date)}").classes(f"crm-chip {task_chip_class}")
            render_pagination(page_result)

    def render_pagination(page_result) -> None:
        if page_result.page_count <= 1:
            return

        def go_to_page(page: int) -> None:
            state["page"] = page
            refresh_contact_list()

        with ui.row().classes("w-full items-center justify-end gap-2 pt-2"):
            ui.button("Previous", icon="chevron_left", on_click=lambda: go_to_page(page_result.page - 1)).props(
                "flat dense" if page_result.has_previous else "flat dense disable"
            )
            ui.label(f"Page {page_result.page} of {page_result.page_count}").classes("text-xs text-gray-600")
            ui.button("Next", icon="chevron_right", on_click=lambda: go_to_page(page_result.page + 1)).props(
                "flat dense" if page_result.has_next else "flat dense disable"
            )

    def select_contact(contact: Contact) -> None:
        state["selected_contact"] = contact
        state["selected_task"] = None
        refresh_contact_list()
        refresh_detail()

    def select_task(contact: Contact, task) -> None:
        state["selected_contact"] = contact
        state["selected_task"] = task
        refresh_contact_list()
        refresh_detail()

    def refresh_detail() -> None:
        detail_container.clear()
        contact = selected_contact()
        task = selected_task()
        with detail_container:
            if contact is None:
                with ui.column().classes("crm-empty w-full p-4 gap-2"):
                    ui.label("Select a contact").classes("text-lg font-semibold text-slate-950")
                    ui.label("Notes, tags, and follow-up tasks appear here.").classes("text-sm text-slate-500")
                return

            if task is not None:
                render_task_detail(contact, task)
                return

            render_contact_header(contact)
            render_status_editor(contact)
            render_tag_editor(contact)
            render_note_panel(contact)
            render_task_panel(contact)

    def render_contact_header(contact: Contact) -> None:
        company_name = contact.company.name if contact.company else "No company"
        task_label, task_chip_class, _ = task_state(contact)
        with ui.column().classes("crm-panel w-full p-4 gap-3"):
            with ui.row().classes("w-full items-start justify-between gap-3"):
                with ui.column().classes("gap-1 min-w-0"):
                    ui.label(contact.name).classes("text-xl font-semibold text-slate-950")
                    ui.label(contact.email or "No email").classes("text-sm text-slate-500 break-words")
                    ui.label(f"{company_name} · {contact.title or 'No title'}").classes("text-sm text-slate-500 break-words")
                status_chip(contact.status)
            with ui.row().classes("items-center gap-2 flex-wrap"):
                ui.label(f"Last touch {format_date(contact.last_touch_at)}").classes("crm-chip crm-chip-muted")
                ui.label(f"Next {format_date(contact.next_task_due_at)}").classes(f"crm-chip {task_chip_class}")
                ui.label(task_label).classes(f"crm-chip {task_chip_class}")
            with ui.row().classes("items-center gap-2 flex-wrap pt-1"):
                ui.button("Edit", icon="edit", on_click=lambda: edit_contact_basics(contact)).props("flat dense color=primary")
                ui.button("Archive", icon="archive", on_click=lambda: archive_selected(contact)).props("flat dense color=negative")

    def render_task_detail(contact: Contact, task) -> None:
        state_label, state_chip_class, state_class = task_status(task)
        company_name = contact.company.name if contact.company else "No company"

        with ui.column().classes("crm-panel w-full p-4 gap-3"):
            with ui.row().classes("w-full items-start justify-between gap-3"):
                with ui.column().classes("gap-1 min-w-0"):
                    ui.label(task.title).classes("text-lg font-semibold text-slate-950")
                    ui.label(f"{contact.name} · {company_name}").classes("text-sm text-slate-500")
                    ui.label(f"Due: {format_date(task.due_date)}").classes(f"text-sm {state_class}")
                ui.label(state_label).classes(f"crm-chip {state_chip_class}")
            ui.button("Contact", icon="person", on_click=lambda: select_contact(contact)).props("flat color=primary").classes("self-start")

        with ui.column().classes("crm-panel w-full p-4 gap-3"):
            ui.label("Description").classes("crm-section-title")
            ui.label(getattr(task, "description", "") or "No description.").classes("text-sm text-slate-800")
            if task.completed:
                ui.button("Reopen", icon="undo", on_click=lambda: reopen_task(contact, task)).props("size=sm").classes("self-start")
            else:
                ui.button("Mark done", icon="check", on_click=lambda: complete_task(contact, task)).props(
                    "size=sm color=positive unelevated"
                ).classes("self-start")

    def render_status_editor(contact: Contact) -> None:
        with ui.column().classes("crm-panel w-full p-4 gap-3"):
            ui.label("Relationship").classes("crm-section-title")
            status_select = ui.select(
                [status_label(status) for status in CONTACT_STATUSES],
                label="Relationship status",
                value=status_label(contact.status),
            ).props("dense outlined").classes("w-full")

            def save_status() -> None:
                reverse_status = {status_label(status): status for status in CONTACT_STATUSES}
                crm.change_contact_status(contact, reverse_status[status_select.value])
                refresh_all()

            ui.button("Save status", icon="save", on_click=save_status).props("size=sm color=primary unelevated").classes("self-start")

    def render_tag_editor(contact: Contact) -> None:
        with ui.column().classes("crm-panel w-full p-4 gap-3"):
            ui.label("Tags").classes("crm-section-title")
            with ui.row().classes("items-center gap-2 flex-wrap"):
                if not contact.tags:
                    ui.label("No tags yet.").classes("text-sm text-slate-500 italic")
                for tag in sorted(contact.tags):
                    with ui.row().classes("items-center gap-1 crm-chip"):
                        ui.label(tag)
                        ui.button(icon="close", on_click=lambda _, t=tag: remove_tag(contact, t)).props("flat dense round size=xs")
            tag_input = ui.input("Add tag").props("dense outlined").classes("w-full")

            def add_tag() -> None:
                crm.add_contact_tag(contact, tag_input.value or "")
                refresh_all()

            ui.button("Add tag", icon="sell", on_click=add_tag).props("size=sm color=primary unelevated").classes("self-start")

    def render_note_panel(contact: Contact) -> None:
        with ui.column().classes("crm-panel w-full p-4 gap-3"):
            ui.label("Notes").classes("crm-section-title")
            note_input = ui.textarea("New note").props("outlined autogrow").classes("w-full")

            def add_note() -> None:
                try:
                    crm.add_note(contact, note_input.value or "")
                except ValueError as exc:
                    notify_error(str(exc))
                    return
                refresh_all()

            ui.button("Add note", icon="note_add", on_click=add_note).props("size=sm color=primary unelevated").classes("self-start")
            if not contact.notes:
                ui.label("No notes yet.").classes("text-sm text-slate-500 italic")
            for note in sorted(contact.notes, key=lambda item: item.created_at, reverse=True):
                with ui.column().classes("crm-note w-full p-3 gap-1"):
                    ui.label(format_date(note.created_at)).classes("text-xs text-slate-500")
                    ui.label(note.body).classes("text-sm text-slate-800")

    def render_task_panel(contact: Contact) -> None:
        with ui.column().classes("crm-panel w-full p-4 gap-3"):
            ui.label("Tasks").classes("crm-section-title")
            task_title = ui.input("Task title").props("dense outlined").classes("w-full")
            task_description = ui.textarea("Task description").props("outlined autogrow").classes("w-full")
            due_date = ui.input("Due date", placeholder="YYYY-MM-DD").props("dense outlined").classes("w-full")

            def add_task() -> None:
                try:
                    crm.add_task(contact, task_title.value or "", parse_due_date(due_date.value), task_description.value or "")
                except ValueError as exc:
                    notify_error(str(exc))
                    return
                refresh_all()

            ui.button("Add task", icon="add_task", on_click=add_task).props("size=sm color=primary unelevated").classes("self-start")
            if not contact.tasks:
                ui.label("No tasks yet.").classes("text-sm text-slate-500 italic")
            for task in sorted(contact.tasks, key=lambda item: (item.completed, item.due_date or date.max, item.created_at)):
                state_label, state_chip_class, color = task_status(task)
                with ui.row().classes("crm-task w-full items-center justify-between gap-3 p-3"):
                    with ui.column().classes("gap-1 min-w-0"):
                        ui.label(task.title).classes(f"text-sm font-semibold {color}")
                        description = getattr(task, "description", "")
                        if description:
                            ui.label(description).classes("text-xs text-slate-700")
                        ui.label(f"{state_label} · Due: {format_date(task.due_date)}").classes(f"crm-chip {state_chip_class}")
                    if task.completed:
                        ui.button("Reopen", icon="undo", on_click=lambda _, t=task: reopen_task(contact, t)).props("flat size=sm")
                    else:
                        ui.button("Mark done", icon="check", on_click=lambda _, t=task: complete_task(contact, t)).props(
                            "flat size=sm color=positive"
                        )

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

        with ui.dialog() as dialog, ui.card().classes("crm-dialog-card w-[460px] max-w-full"):
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

    def add_company() -> None:
        with ui.dialog() as dialog, ui.card().classes("crm-dialog-card w-[420px] max-w-full"):
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

    with ui.header().classes("crm-topbar text-slate-950"):
        with ui.row().classes("crm-header-row w-full items-center gap-3 px-5 py-3 flex-wrap"):
            with ui.row().classes("crm-brand items-center gap-3"):
                ui.element("div").classes("crm-brand-mark")
                ui.label("Simple CRM").classes("text-lg font-bold")
            header_search_container = ui.row().classes("crm-header-search items-center")
            ui.space()
            with ui.row().classes("items-center gap-2 flex-wrap"):
                ui.button("Add company", icon="business", on_click=add_company).props("outline color=primary")
                ui.button("Seed data", icon="dataset", on_click=seed_data).props("color=primary unelevated")

    with ui.column().classes("crm-shell crm-page-padding w-full p-5"):
        with ui.element("div").classes("crm-layout"):
            left_panel = ui.column().classes("crm-panel w-full p-4 gap-5")
            main_panel = ui.column().classes("w-full min-w-0 gap-4")
            detail_panel = ui.column().classes("crm-detail w-full gap-3")

    with left_panel:
        filters_container = ui.column().classes("w-full gap-3")
        ui.separator().classes("crm-subtle-divider")
        contact_form_container = ui.column().classes("w-full gap-3")
    with main_panel:
        metrics_container = ui.row().classes("w-full gap-3 flex-wrap")
        list_container = ui.column().classes("w-full gap-3")
    with detail_panel:
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
