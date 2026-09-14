import sys
import tempfile
import unittest
from email import message_from_string
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import gmail_smtp


class MailFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env_patch = patch.object(gmail_smtp, "ENV_PATH", Path(self.temp.name) / ".env")
        env_patch.start()
        self.addCleanup(env_patch.stop)

    @patch("app.gmail_smtp.smtplib.SMTP_SSL")
    def test_connect_send_disconnect_with_plain_text_alternative(self, smtp):
        gmail_smtp._write_env({"OTHER_SETTING": "keep"})
        gmail_smtp.connect("sender@example.com", "abcdefghijklmnop")
        self.assertTrue(gmail_smtp.is_connected())
        gmail_smtp.send_email("Sender", "recipient@example.com", "Hello", "<p>Hello <b>Person</b></p>")
        message = message_from_string(smtp.return_value.__enter__.return_value.sendmail.call_args.args[2])
        types = [part.get_content_type() for part in message.walk()]
        self.assertIn("text/plain", types)
        self.assertIn("text/html", types)
        self.assertEqual(smtp.call_args.kwargs["timeout"], 30)
        self.assertIsNotNone(smtp.call_args.kwargs["context"])
        gmail_smtp.disconnect()
        self.assertFalse(gmail_smtp.is_connected())
        self.assertEqual(gmail_smtp._read_env(), {"OTHER_SETTING": "keep"})

    @patch("app.gmail_smtp.smtplib.SMTP_SSL")
    def test_missing_credentials_fail_without_network(self, smtp):
        with self.assertRaises(RuntimeError):
            gmail_smtp.send_email("Sender", "recipient@example.com", "Hello", "<p>Hello</p>")
        smtp.assert_not_called()


if __name__ == "__main__":
    unittest.main()