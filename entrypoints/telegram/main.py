"""Telegram polling entrypoint."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib import error, parse, request
from typing import Protocol

from .adapter import (
    TelegramResponse,
    TelegramUpdate,
    process_update,
    response_to_send_message_payload,
)


class TelegramBotClient(Protocol):
    """Minimal Telegram client facade for polling and sending replies."""

    def get_updates(self, offset: int = 0) -> list[dict[str, object]]:
        raise NotImplementedError

    def send_message(self, chat_id: int, text: str) -> None:
        raise NotImplementedError


@dataclass
class TelegramHTTPClient:
    """Tiny Telegram Bot API client using urllib."""

    token: str
    api_base: str = "https://api.telegram.org"
    timeout: float = 30.0

    def _open_json(self, url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram API error {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Telegram network error: {exc.reason}") from exc
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise RuntimeError("Telegram API returned a non-object response")
        return parsed

    def get_updates(self, offset: int = 0) -> list[dict[str, object]]:
        query = parse.urlencode({"timeout": 25, "offset": offset})
        payload = self._open_json(f"{self.api_base}/bot{self.token}/getUpdates?{query}")
        result = payload.get("result", [])
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, dict)]

    def send_message(self, chat_id: int, text: str) -> None:
        payload = {"chat_id": chat_id, "text": text}
        response = self._open_json(f"{self.api_base}/bot{self.token}/sendMessage", payload)
        if response.get("ok") is not True:
            raise RuntimeError(f"Telegram sendMessage failed: {response}")


def _load_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the Telegram bot")
    return token


def _extract_text_message(update: dict[str, object]) -> TelegramUpdate | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    chat = message.get("chat")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    message_id = message.get("message_id")
    if not isinstance(chat_id, int):
        return None
    if not isinstance(message_id, int):
        message_id = None
    return TelegramUpdate(text=text, chat_id=chat_id, message_id=message_id)


def run_polling(client: TelegramBotClient) -> None:
    """Run a thin polling loop over Telegram updates."""

    offset = 0
    while True:
        updates = client.get_updates(offset)
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = max(offset, update_id + 1)
            telegram_update = _extract_text_message(update)
            if telegram_update is None:
                continue
            response: TelegramResponse = process_update(telegram_update)
            payload = response_to_send_message_payload(response)
            if payload is not None:
                client.send_message(payload["chat_id"], payload["text"])


def main() -> int:
    """Start the Telegram polling bot."""

    token = _load_token()
    client = TelegramHTTPClient(token=token)
    run_polling(client)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

