import io
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Lock
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import storage, routes_gmail, cert_render
from app.main import app


class ProjectFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage_patch = patch.object(storage, "DATA_DIR", Path(self.temp.name))
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.project = self.client.post(
            "/api/projects", data={"name": "Regression test", "mode": "emails_only"}
        ).json()
        self.base = f"/api/projects/{self.project['id']}"
        self.client.put(self.base + "/email-draft", json={"subject": "Hello", "html": "<p>Hello</p>"})

    @patch("app.routes_gmail.asyncio.sleep", new_callable=AsyncMock)
    @patch("app.routes_gmail.gmail_smtp.send_email")
    def test_duplicate_recipients_are_skipped_within_batch_and_on_retry(self, send, sleep):
        rows = [{"Email": "person@example.com"}, {"Email": " Person@EXAMPLE.com "}]
        response = self.client.post(self.base + "/send-all", json={"rows": rows})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sent"], 1)
        self.assertEqual(send.call_count, 1)
        response = self.client.post(self.base + "/send-all", json={"rows": rows})
        self.assertEqual(response.json()["sent"], 0)
        self.assertEqual(send.call_count, 1)

    def workbook_bytes(self, values):
        workbook = Workbook()
        for row in values:
            workbook.active.append(row)
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    def test_template_has_unique_email_and_default_name_columns(self):
        self.client.put(self.base + "/email-draft", json={"html": "{{Email}}", "subject": ""})
        response = self.client.get(self.base + "/template.xlsx")
        workbook = load_workbook(io.BytesIO(response.content))
        self.addCleanup(workbook.close)
        columns = [cell.value for cell in workbook.active[1]]
        self.assertEqual(columns.count("Email"), 1)
        self.assertIn("Name", columns)

    def test_recipient_import_does_not_require_first_column(self):
        content = self.workbook_bytes([["Optional", "Email", "Name"], [None, "person@example.com", "Person"]])
        response = self.client.post(self.base + "/generate", files={"file": ("rows.xlsx", content)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_missing_email_column_and_malformed_workbook_are_rejected(self):
        for content in [b"not a workbook", self.workbook_bytes([["Name"], ["Person"]])]:
            with self.subTest(content=content[:10]):
                response = self.client.post(self.base + "/generate", files={"file": ("rows.xlsx", content)})
                self.assertEqual(response.status_code, 400)

    def test_duplicate_names_do_not_overwrite_certificates(self):
        project = storage.load_project(self.project["id"])
        project.update(mode="certificates", background="background.png")
        storage.save_project(project)
        Image.new("RGB", (300, 200), "white").save(storage.project_path(project["id"], "background.png"))
        content = self.workbook_bytes([
            ["Name", "Email"], ["Same Name", "first@example.com"], ["Same Name", "second@example.com"]
        ])
        response = self.client.post(self.base + "/generate", files={"file": ("rows.xlsx", content)})
        self.assertEqual(response.status_code, 200)
        files = [row["_certificate_file"] for row in response.json()["rows"]]
        self.assertEqual(len(set(files)), 2)
        for filename in files:
            self.assertTrue(self.client.get(self.base + "/generated/" + filename).content.startswith(b"%PDF"))

    def test_paths_cannot_escape_project_or_requested_subfolder(self):
        for parts in [("generated", "../../outside.pdf"), ("fonts", "../project.json"), ("C:\\outside",)]:
            with self.subTest(parts=parts), self.assertRaises(ValueError):
                storage.project_path(self.project["id"], *parts)
        with self.assertRaises(ValueError):
            storage.project_path("..", "anything")

    def test_missing_project_returns_404(self):
        response = self.client.put("/api/projects/0000000000/email-draft", json={"subject": "", "html": ""})
        self.assertEqual(response.status_code, 404)

    @patch("app.routes_gmail.gmail_smtp.send_email")
    def test_concurrent_send_is_rejected(self, send):
        lock = routes_gmail._send_locks.setdefault(self.project["id"], Lock())
        lock.acquire()
        try:
            response = self.client.post(self.base + "/send-all", json={"rows": [{"Email": "person@example.com"}]})
            self.assertEqual(response.status_code, 409)
            send.assert_not_called()
        finally:
            lock.release()

    def test_preview_escapes_recipient_values_and_preserves_subject_text(self):
        self.client.put(self.base + "/email-draft", json={"subject": "Hi {{Name}}", "html": "<p>{{Name}} {{Optional}}</p>"})
        response = self.client.post(self.base + "/email-preview", json={"Name": '<img src=x onerror="alert(1)">', "Optional": None})
        self.assertEqual(response.status_code, 200)
        self.assertIn("&lt;img", response.json()["html"])
        self.assertNotIn("None", response.json()["html"])
        self.assertIn("<img", response.json()["subject"])

    def test_invalid_draft_and_image_are_rejected(self):
        response = self.client.put(self.base + "/email-draft", json={"subject": [], "html": 42})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(self.base + "/email-images", files={"file": ("photo.png", b"not an image")})
        self.assertEqual(response.status_code, 400)

    def test_repeated_image_names_have_distinct_cids(self):
        output = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(output, format="PNG")
        images = [self.client.post(self.base + "/email-images", files={"file": ("photo.png", output.getvalue())}).json() for _ in range(2)]
        self.assertNotEqual(images[0]["cid"], images[1]["cid"])
        for image in images:
            response = self.client.get(self.base + "/email-images/by-cid/" + image["cid"])
            self.assertEqual(response.content, output.getvalue())

    def test_invalid_background_font_and_fields_are_rejected(self):
        for endpoint, filename in [("background", "background.html"), ("fonts", "font.ttf")]:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(self.base + "/" + endpoint, files={"file": (filename, b"invalid")})
                self.assertEqual(response.status_code, 400)
        for fields in [[{"name": "Name"}], [{"name": "Name", "x": 20, "y": 20, "font": "../outside.ttf"}]]:
            with self.subTest(fields=fields):
                self.assertEqual(self.client.put(self.base + "/fields", json=fields).status_code, 400)

    def test_certificate_bold_italic_uses_matching_font_variant(self):
        background = Path(self.temp.name) / "background.png"
        Image.new("RGB", (300, 200), "white").save(background)
        fields = [{"name": "Name", "x": 150, "y": 100, "font": "arial.ttf", "bold": True, "italic": True}]
        with patch("app.cert_render.resolve_font", wraps=cert_render.resolve_font) as resolve:
            cert_render.render_certificate(background, fields, {"Name": "Person"}, Path(self.temp.name), Path(self.temp.name) / "preview.png")
            self.assertEqual(resolve.call_args.args[0], "arialbi.ttf")


if __name__ == "__main__":
    unittest.main()