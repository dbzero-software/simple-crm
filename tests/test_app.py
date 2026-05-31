from __future__ import annotations

import importlib

import dbzero as db0

from simple_crm.models import CRM


def test_app_imports_without_starting_server():
    module = importlib.import_module("app")

    assert hasattr(module, "crm_page")
    assert hasattr(module, "initialize_crm")


def test_initialize_crm_opens_durable_root(tmp_path):
    module = importlib.import_module("app")

    crm = module.initialize_crm(tmp_path / "dbzero")
    try:
        assert isinstance(crm, CRM)
        company = crm.add_company("Northstar Analytics")
        assert crm.find_company_by_name("northstar analytics") is company
    finally:
        db0.close()


def test_parse_due_date_reports_expected_format():
    module = importlib.import_module("app")

    try:
        module.parse_due_date("tomorrow")
    except ValueError as exc:
        assert str(exc) == "Use YYYY-MM-DD for due dates."
    else:
        raise AssertionError("invalid date should raise ValueError")
