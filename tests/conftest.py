"""Test fixtures for Simple CRM."""

from __future__ import annotations

import pytest
import dbzero as db0

from simple_crm.config import DATA_PREFIX
from simple_crm.models import CRM


@pytest.fixture()
def crm(tmp_path):
    db0.init(str(tmp_path / "dbzero"), prefix=DATA_PREFIX, autocommit=True)
    root = CRM()
    try:
        yield root
    finally:
        db0.close()

