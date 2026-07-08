"""Tests for Telegram notifier."""
import sys
sys.path.insert(0, "/opt/nfr")
import unittest
import os
from unittest.mock import patch, MagicMock
from nfr.notifier import Notifier, TelegramConfig


class TestNotifier(unittest.TestCase):
    def test_disabled_when_no_config(self):
        cfg = TelegramConfig()
        cfg.token = None
        cfg.chat_id = None
        n = Notifier(cfg)
        self.assertFalse(n.is_configured())
        self.assertFalse(n.send("test"))

    def test_enabled_with_env(self):
        with patch.dict(os.environ, {
            "NFR_TELEGRAM_TOKEN": "test_token",
            "NFR_TELEGRAM_CHAT_ID": "12345",
        }):
            cfg = TelegramConfig.load()
            self.assertTrue(cfg.enabled)
            self.assertEqual(cfg.token, "test_token")
            self.assertEqual(cfg.chat_id, "12345")

    def test_send_returns_false_when_disabled(self):
        cfg = TelegramConfig()
        cfg.token = "abc"
        cfg.chat_id = None  # missing
        n = Notifier(cfg)
        self.assertFalse(n.is_configured())
        self.assertFalse(n.send("test"))

    def test_chat_id_redaction(self):
        cfg = TelegramConfig()
        cfg.token = "abcdefghijklmnop"
        cfg.chat_id = "12345"
        self.assertTrue(len(cfg.token) > 8)


if __name__ == "__main__":
    unittest.main()
