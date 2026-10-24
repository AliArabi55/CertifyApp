import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import auth_store, storage


class AuthStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_dir = Path(self.temp.name) / "projects"
        self.data_dir.mkdir()
        self.storage_patch = patch.object(storage, "DATA_DIR", self.data_dir)
        self.storage_patch.start()
        self.addCleanup(self.storage_patch.stop)
        self.database_patch = patch.object(auth_store, "DB_PATH", Path(self.temp.name) / "accounts.sqlite3")
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        auth_store.init_db()
        auth_store.create_user("owner-id", "owner@example.com", "hash-a", False, 1)
        auth_store.create_user("other-id", "other@example.com", "hash-b", False, 1)

    def test_project_is_only_visible_to_its_owner(self):
        project = auth_store.create_project("owner-id", "Private", "emails_only")

        self.assertEqual([project], auth_store.list_projects("owner-id"))
        self.assertEqual([], auth_store.list_projects("other-id"))
        self.assertTrue(auth_store.owns_project("owner-id", project["id"]))
        self.assertFalse(auth_store.owns_project("other-id", project["id"]))

    def test_owner_can_claim_unassigned_legacy_projects(self):
        project = storage.create_project("Legacy", "emails_only")

        auth_store.claim_legacy_projects("owner-id")

        self.assertTrue(auth_store.owns_project("owner-id", project["id"]))
        self.assertFalse(auth_store.owns_project("other-id", project["id"]))

    def test_sessions_store_only_token_digests_and_validate_csrf(self):
        token = auth_store.create_action_token("owner-id", "verify", 500)
        auth_store.verify_action_token(token, "verify", 100)
        session_token, csrf_token = auth_store.create_session("owner-id", 500)

        session_user = auth_store.get_session_user(session_token, 100)

        self.assertIsNotNone(session_user)
        self.assertTrue(auth_store.csrf_valid(session_user, csrf_token))
        self.assertFalse(auth_store.csrf_valid(session_user, "wrong-token"))
        self.assertFalse(auth_store.get_session_user(session_token, 501))


if __name__ == "__main__":
    unittest.main()