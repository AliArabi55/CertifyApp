import io
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import uvicorn
from openpyxl import Workbook
from PIL import Image
from playwright.sync_api import sync_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import gmail_smtp, storage
from app.main import app


class BrowserFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        for target, attribute, value in [(storage, "DATA_DIR", cls.root), (gmail_smtp, "ENV_PATH", cls.root / ".env")]:
            replacement = patch.object(target, attribute, value)
            replacement.start()
            cls.addClassCleanup(replacement.stop)
        smtp_patch = patch("app.gmail_smtp.smtplib.SMTP_SSL")
        cls.smtp = smtp_patch.start()
        cls.addClassCleanup(smtp_patch.stop)
        gmail_smtp._write_env({"GMAIL_ADDRESS": "test@example.com", "GMAIL_APP_PASSWORD": "fake-test-password"})
        ready = threading.Event()

        class TestServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets)
                ready.set()

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        cls.addClassCleanup(listener.close)
        cls.url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        cls.server = TestServer(uvicorn.Config(app, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={"sockets": [listener]}, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.stop_server)
        if not ready.wait(10):
            raise RuntimeError("Test server failed to start")
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        cls.browser = cls.playwright.chromium.launch(channel=os.environ.get("CERTIFY_BROWSER_CHANNEL", "msedge"), headless=True)
        cls.addClassCleanup(cls.browser.close)

    @classmethod
    def stop_server(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=10)

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.dialogs = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("dialog", self.handle_dialog)
        self.page.goto(self.url)
        self.page.locator("#projectNameInput").fill("Browser test")
        self.page.locator('[data-mode="emails_only"]').click()
        expect(self.page.locator("#step-2")).to_be_visible()
        self.project_id = self.page.evaluate("state.projectId")
        workbook = Workbook()
        workbook.active.append(["Email", "Name", "LinkedIn_Share_Link"])
        workbook.active.append(["person@example.com", '<img src=x onerror="alert(1)">', "https://www.linkedin.com/"])
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()
        self.page.locator("#excelFileInput").set_input_files({"name": "recipients.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "buffer": output.getvalue()})
        self.page.locator("#generateBtn").click()
        expect(self.page.locator("#generatedCount")).to_have_text("1 recipient(s) loaded.")
        self.page.locator('[data-step="3"]').click()

    def handle_dialog(self, dialog):
        self.dialogs.append(dialog.message)
        dialog.accept()

    def test_compose_preview_uses_current_content_and_safe_recipient_text(self):
        self.assertEqual(self.page.locator("#generatedTableBody img").count(), 0)
        self.page.locator("#subjectInput").fill("Latest {{Name}}")
        editor = self.page.locator("#emailEditor .ql-editor")
        editor.fill("Hello {{Name}}")
        editor.press("Control+a")
        self.page.locator(".ql-bold").click()
        self.page.locator("#previewEmailBtn").click()
        expect(self.page.locator("#previewSubject")).to_contain_text("Latest")
        expect(self.page.frame_locator("#previewFrame").locator("strong")).to_contain_text("Hello <img")
        self.assertEqual(self.page.frame_locator("#previewFrame").locator("img").count(), 0)
        self.assertEqual(self.errors, [])

    def test_inline_image_and_merge_link_survive_mode_switch(self):
        self.page.locator("#emailEditor .ql-editor").fill("Message")
        self.page.locator("#insertLinkedInBtn").click()
        self.assertIn("{{LinkedIn_Share_Link}}", self.page.evaluate("getDraftHtml()"))
        output = io.BytesIO()
        Image.new("RGB", (30, 20), "red").save(output, format="PNG")
        self.page.locator("#emailImageInput").set_input_files({"name": "image.png", "mimeType": "image/png", "buffer": output.getvalue()})
        self.page.locator("#uploadEmailImageBtn").click()
        expect(self.page.locator("#emailEditor img")).to_have_count(1)
        self.page.wait_for_function("document.querySelector('#emailEditor img').naturalWidth > 0")
        self.page.locator("#htmlModeBtn").click()
        source = self.page.locator("#htmlTextarea").input_value()
        self.assertIn('src="cid:', source)
        self.assertIn("{{LinkedIn_Share_Link}}", source)
        self.page.locator("#visualModeBtn").click()
        self.assertIn('src="cid:', self.page.evaluate("getDraftHtml()"))
        self.assertEqual(self.errors, [])

    def test_html_mode_preserves_source_and_send_saves_latest_draft(self):
        self.page.locator("#htmlModeBtn").click()
        source = '<table><tr><td style="color:red">Latest {{Name}}</td></tr></table>'
        self.page.locator("#htmlTextarea").fill(source)
        self.page.locator("#subjectInput").fill("Latest subject")
        self.page.locator('[data-step="4"]').click()
        self.page.locator("#testToInput").fill("test@example.com")
        self.page.locator("#sendTestBtn").click()
        self.page.wait_for_function("document.querySelector('#sendTestBtn').disabled === false")
        self.page.wait_for_function("document.querySelector('#editorStatus').textContent.includes('Saved')")
        project = storage.load_project(self.project_id)
        self.assertEqual(project["email_draft"], {"subject": "Latest subject", "html": source})
        self.assertEqual(self.errors, [])

    def test_mobile_composer_fits_viewport(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.locator("#emailEditor .ql-editor").fill("A readable message on mobile")
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
        self.page.screenshot(path=str(self.root / "mobile-composer.png"), full_page=True)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()