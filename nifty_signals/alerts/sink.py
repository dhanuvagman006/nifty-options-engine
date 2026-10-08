"""Alert sinks: console, JSONL file, generic webhook, Telegram."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from ..config import AlertConfig
from ..engine.signals import Signal

log = logging.getLogger(__name__)


class Sink:
    def emit(self, sig: Signal, line: str) -> None:  # pragma: no cover - interface
        raise NotImplementedError


class ConsoleSink(Sink):
    def emit(self, sig: Signal, line: str) -> None:
        print(line, flush=True)


class FileSink(Sink):
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def emit(self, sig: Signal, line: str) -> None:
        rec = sig.to_dict()
        rec["line"] = line
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")


class WebhookSink(Sink):
    def __init__(self, url: str):
        self.url = url

    def emit(self, sig: Signal, line: str) -> None:
        import requests

        try:
            requests.post(self.url, json={"text": line, **sig.to_dict()}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("webhook failed: %s", exc)


class TelegramSink(Sink):
    def __init__(self, token: str, chat_id: str):
        self.url = f"https://api.telegram.org/bot{token}/sendMessage"
        self.chat_id = chat_id

    def emit(self, sig: Signal, line: str) -> None:
        import requests

        try:
            requests.post(self.url, json={"chat_id": self.chat_id, "text": line}, timeout=10)
        except Exception as exc:  # noqa: BLE001
            log.warning("telegram failed: %s", exc)


class Dispatcher:
    def __init__(self, cfg: AlertConfig):
        self.cfg = cfg
        self.sinks: list[Sink] = []
        if cfg.console:
            self.sinks.append(ConsoleSink())
        if cfg.file:
            self.sinks.append(FileSink(cfg.file))
        if cfg.webhook_url:
            self.sinks.append(WebhookSink(cfg.webhook_url))
        if cfg.telegram_token and cfg.telegram_chat_id:
            self.sinks.append(TelegramSink(cfg.telegram_token, cfg.telegram_chat_id))

    def dispatch(self, sig: Signal) -> None:
        line = sig.line(self.cfg.verbose)
        for s in self.sinks:
            try:
                s.emit(sig, line)
            except Exception as exc:  # noqa: BLE001
                log.warning("sink %s failed: %s", type(s).__name__, exc)
