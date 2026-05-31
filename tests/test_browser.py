from __future__ import annotations

import socket
import subprocess
import sys
import time
import os
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright
from playwright.sync_api import Error as PlaywrightError
import pytest


def test_browser_follow_up_workflow(tmp_path):
    port = _free_port()
    dbzero_root = tmp_path / "dbzero"
    base_url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "app.py",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--dbzero-root",
            str(dbzero_root),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "NICEGUI_SCREEN_TEST_PORT": str(port)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_http(base_url, process)
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except PlaywrightError as exc:
                message = str(exc)
                if "error while loading shared libraries" in message:
                    pytest.skip(f"Chromium system dependencies are missing: {message.splitlines()[-1]}")
                raise
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(base_url, wait_until="networkidle")

            expect(page.get_by_text("Start with sample CRM data")).to_be_visible()
            expect(page.get_by_role("button", name="Add contact").first).to_be_visible()
            page.get_by_role("button", name="Seed data").first.click()
            expect(page.get_by_text("Avery Stone")).to_be_visible()
            expect(page.get_by_text("12 contacts", exact=True)).to_be_visible()
            page.get_by_role("button", name="5 Companies").click()
            page.get_by_role("button", name="Northstar Analytics").click()
            expect(page.get_by_text("2 contacts", exact=True).first).to_be_visible()
            expect(page.get_by_text("Mina Patel")).to_be_visible()
            page.get_by_role("button", name="7 Open tasks total").click()
            expect(page.get_by_text("7 open tasks", exact=True)).to_be_visible()
            expect(page.get_by_text("Avery Stone · Northstar Analytics")).to_be_visible()
            pricing_description = "Send pricing options and ask which plan fits their rollout timeline."
            page.get_by_role("button", name="Send pricing follow-up").first.click()
            expect(page.get_by_text("Description", exact=True)).to_be_visible()
            assert page.get_by_text(pricing_description).count() >= 2
            page.get_by_role("button", name="12 Contacts").click()
            expect(page.get_by_text("12 contacts", exact=True)).to_be_visible()

            page.get_by_text("Avery Stone").first.click()
            page.get_by_label("New note").fill("Browser smoke test note.")
            page.get_by_role("button", name="Add note").click()
            expect(page.get_by_text("Browser smoke test note.")).to_be_visible()

            page.get_by_label("Task title").fill("Browser follow-up")
            page.get_by_label("Task description").fill("Confirm the browser-created follow-up details.")
            page.get_by_label("Due date").fill("2026-06-15")
            page.get_by_role("button", name="Add task").click()
            expect(page.get_by_text("Browser follow-up")).to_be_visible()
            expect(page.get_by_text("Confirm the browser-created follow-up details.")).to_be_visible()
            expect(page.get_by_text("Open · Due: 2026-06-15")).to_be_visible()
            page.get_by_role("button", name="Mark done").last.click()
            expect(page.get_by_role("button", name="Reopen")).to_be_visible()
            page.get_by_role("button", name="Reopen").last.click()
            expect(page.get_by_role("button", name="Mark done")).to_be_visible()

            mobile = browser.new_page(viewport={"width": 390, "height": 844})
            mobile.goto(base_url, wait_until="networkidle")
            expect(mobile.get_by_text("Simple CRM")).to_be_visible()
            expect(mobile.get_by_text("12 contacts", exact=True)).to_be_visible()
            expect(mobile.get_by_text("Avery Stone").first).to_be_visible()
            row_width = mobile.locator(".crm-row").first.bounding_box()["width"]
            assert row_width > 300
            expect(mobile.get_by_text("Select a contact")).to_be_visible()
            mobile.get_by_text("Avery Stone").first.click()
            expect(mobile.get_by_text("Relationship", exact=True)).to_be_visible()

            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_http(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"app process exited early:\n{output}")
        try:
            with urlopen(base_url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    output = process.stdout.read() if process.stdout else ""
    raise TimeoutError(f"app did not start in time:\n{output}")
