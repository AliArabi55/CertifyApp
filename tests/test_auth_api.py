import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import auth_mail, auth_store, storage
from app.main import app


class AccountFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name) / "projects"
        self.data_dir.mkdir()
        self.patches = [
            patch.object(storage, "DATA_DIR", self.data_dir),
            patch.object(auth_store, "DB_PATH", Path(self.temp.name) / "accounts.sqlite3"),
            patch.object(auth_mail, "is_configured", return_value=True),
            patch.dict(
                os.environ,
                {
                    "CERTIFY_OWNER_EMAIL": "owner@example.com",
                    "CERTIFY_COOKIE_SECURE": "0",
                },
            ),
        ]
        for replacement in self.patches:
            replacement.start()
            self.addCleanup(replacement.stop)
        auth_store.init_db()
        sender = patch("app.routes_auth.auth_mail.send_action_email")
        self.send_email = sender.start()
        self.addCleanup(sender.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def _register_and_verify(self, email, password="strong-password-123"):
        response = self.client.post(
            "/api/auth/register", json={"email": email, "password": password}
        )
        self.assertEqual(response.status_code, 202)
        token = self.send_email.call_args.args[3]
        response = self.client.post("/api/auth/verify", json={"token": token})
        self.assertEqual(response.status_code, 200)
        return response

    def _login(self, email, password="strong-password-123"):
        response = self.client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_account_requires_email_verification_and_creates_session(self):
        response = self.client.post(
            "/api/auth/register",
            json={"email": "owner@example.com", "password": "strong-password-123"},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.send_email.call_args.args[2], "verify")
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"email": "owner@example.com", "password": "strong-password-123"},
            ).status_code,
            403,
        )

        self.client.post("/api/auth/verify", json={"token": self.send_email.call_args.args[3]})
        login = self.client.post(
            "/api/auth/login",
            json={"email": "owner@example.com", "password": "strong-password-123"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue(self.client.cookies.get("certify_session"))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.assertEqual(self.client.get("/api/projects").json(), [])

    def test_owner_claims_legacy_projects_and_other_accounts_do_not(self):
        legacy = storage.create_project("Existing project", "emails_only")
        self._register_and_verify("owner@example.com")
        owner_session = self._login("owner@example.com")
        owner = auth_store.get_user_by_email("owner@example.com")
        self.assertTrue(auth_store.owns_project(owner["id"], legacy["id"]))

        self.client.post("/api/auth/logout", headers={"X-CSRF-Token": owner_session["csrf_token"]})
        self._register_and_verify("other@example.com")
        self._login("other@example.com")
        other = auth_store.get_user_by_email("other@example.com")
        self.assertFalse(auth_store.owns_project(other["id"], legacy["id"]))
        self.assertEqual(self.client.get("/api/projects").json(), [])

    def test_password_reset_is_single_use_and_changes_password(self):
        self._register_and_verify("person@example.com")
        self._login("person@example.com")
        response = self.client.post(
            "/api/auth/password-reset-request", json={"email": "person@example.com"}
        )
        self.assertEqual(response.status_code, 202)
        token = self.send_email.call_args.args[3]
        csrf_token = self.client.get("/api/auth/me").json()["csrf_token"]
        self.client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})

        reset = self.client.post(
            "/api/auth/password-reset",
            json={"token": token, "password": "another-password-456"},
        )
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/auth/password-reset",
                json={"token": token, "password": "another-password-456"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"email": "person@example.com", "password": "another-password-456"},
            ).status_code,
            200,
        )

    def test_registration_fails_closed_without_mail_configuration(self):
        with patch("app.routes_auth.auth_mail.is_configured", return_value=False):
            response = self.client.post(
                "/api/auth/register",
                json={"email": "person@example.com", "password": "strong-password-123"},
            )
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()