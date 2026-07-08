"""Telegram notifier for NFR alerts.

Reads config from /etc/nfr/telegram.yaml or env vars (NFR_TELEGRAM_TOKEN,
NFR_TELEGRAM_CHAT_ID). Falls back to no-op if not configured.
"""
import os
import json
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

CONFIG_PATH = Path("/etc/nfr/telegram.yaml")


class TelegramConfig:
    """Telegram bot configuration loaded from file or env."""
    token: Optional[str] = None
    chat_id: Optional[str] = None
    enabled: bool = False

    @classmethod
    def load(cls) -> "TelegramConfig":
        cfg = cls()
        cfg.token = os.environ.get("NFR_TELEGRAM_TOKEN")
        cfg.chat_id = os.environ.get("NFR_TELEGRAM_CHAT_ID")
        if not cfg.token and CONFIG_PATH.exists():
            try:
                import yaml
                with open(CONFIG_PATH) as f:
                    data = yaml.safe_load(f) or {}
                cfg.token = data.get("token")
                cfg.chat_id = data.get("chat_id")
            except Exception:
                pass
        cfg.enabled = bool(cfg.token and cfg.chat_id)
        return cfg


class Notifier:
    """Send alerts to Telegram. No-op if not configured."""

    def __init__(self, cfg=None):
        self.cfg = cfg or TelegramConfig.load()

    def is_configured(self):
        return self.cfg.enabled

    def send(self, message, parse_mode="Markdown"):
        if not self.is_configured() or requests is None:
            return False
        try:
            url = "https://api.telegram.org/bot" + self.cfg.token + "/sendMessage"
            data = {
                "chat_id": self.cfg.chat_id,
                "text": message,
                "parse_mode": parse_mode,
            }
            r = requests.post(url, data=data, timeout=10)
            return r.status_code == 200
        except Exception:
            return False

    def notify_finding(self, finding):
        text = (
            "NFR Finding\n\n"
            "Cause: " + finding.primary_cause + "\n"
            "Confidence: " + str(int(finding.confidence * 100)) + "%\n"
            "Evidence: " + str(len(finding.evidence)) + " events\n"
            "Reasoning: " + finding.reasoning
        )
        return self.send(text)

    def test(self):
        return self.send("[OK] NFR test message - configuration OK")
