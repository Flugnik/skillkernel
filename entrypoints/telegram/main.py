"""Telegram polling entrypoint."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from urllib import parse
from typing import Protocol

import httpx

from .adapter import (
    TelegramBotCommand,
    TelegramResponse,
    TelegramUpdate,
    telegram_bot_commands,
    process_update,
    response_to_send_message_payload,
)


class TelegramBotClient(Protocol):
    """Minimal Telegram client facade for polling and sending replies."""

    def get_updates(self, offset: int = 0) -> list[dict[str, object]]:
        raise NotImplementedError

    def send_message(self, chat_id: int, text: str) -> None:
        raise NotImplementedError

    def set_my_commands(self, commands: list[TelegramBotCommand]) -> None:
        raise NotImplementedError

    def set_chat_menu_button(self) -> None:
        raise NotImplementedError


@dataclass
class TelegramHTTPClient:
    """Tiny Telegram Bot API client using httpx."""

    token: str
    api_base: str = "https://api.telegram.org"
    timeout: float = 30.0

    def _open_json(self, url: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        try:
            if payload is None:
                response = httpx.get(url, timeout=self.timeout)
            else:
                response = httpx.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"Telegram network error: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            raise RuntimeError(f"Telegram API error {exc.response.status_code}: {detail}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Telegram network error: {exc}") from exc
        parsed = response.json()
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

    def set_my_commands(self, commands: list[TelegramBotCommand]) -> None:
        payload = {"commands": [{"command": command.command, "description": command.description} for command in commands]}
        response = self._open_json(f"{self.api_base}/bot{self.token}/setMyCommands", payload)
        if response.get("ok") is not True:
            raise RuntimeError(f"Telegram setMyCommands failed: {response}")

    def set_chat_menu_button(self) -> None:
        payload = {"menu_button": {"type": "commands"}}
        response = self._open_json(f"{self.api_base}/bot{self.token}/setChatMenuButton", payload)
        if response.get("ok") is not True:
            raise RuntimeError(f"Telegram setChatMenuButton failed: {response}")


def _log(message: str) -> None:
    print(f"[telegram] {message}", flush=True)


def _is_retryable_error(exc: Exception) -> bool:
    return isinstance(exc, (RuntimeError, TimeoutError))


def _backoff_seconds(attempt: int) -> float:
    return min(5.0, 0.5 * (2 ** max(0, attempt - 1)))


def _load_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the Telegram bot")
    return token


def _register_bot_menu(client: TelegramBotClient) -> None:
    client.set_my_commands(telegram_bot_commands())
    client.set_chat_menu_button()


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
    retry_attempt = 0
    _log("starting bot")
    _log("starting polling")
    while True:
        try:
            updates = client.get_updates(offset)
            retry_attempt = 0
        except KeyboardInterrupt:
            _log("shutdown requested")
            return
        except Exception as exc:  # pragma: no cover - defensive transport guard
            if not _is_retryable_error(exc):
                raise
            retry_attempt += 1
            delay = _backoff_seconds(retry_attempt)
            _log(f"polling error: {exc}; retrying in {delay:.1f}s")
            time.sleep(delay)
            continue
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = max(offset, update_id + 1)
            telegram_update = _extract_text_message(update)
            if telegram_update is None:
                continue
            _log(f"incoming text message chat_id={telegram_update.chat_id}")
            response: TelegramResponse = process_update(telegram_update)
            _log(f"core result type={response.kind}")
            payload = response_to_send_message_payload(response)
            if payload is not None:
                try:
                    client.send_message(payload["chat_id"], payload["text"])
                except KeyboardInterrupt:
                    _log("shutdown requested")
                    return
                except Exception as exc:  # pragma: no cover - defensive transport guard
                    if not _is_retryable_error(exc):
                        raise
                    retry_attempt += 1
                    delay = _backoff_seconds(retry_attempt)
                    _log(f"send error: {exc}; retrying in {delay:.1f}s")
                    time.sleep(delay)
                    continue


def main() -> int:
    """Start the Telegram polling bot."""

    token = _load_token()
    _log("booting Telegram bot")
    client = TelegramHTTPClient(token=token)
    try:
        _register_bot_menu(client)
        run_polling(client)
    except KeyboardInterrupt:
        _log("shutdown requested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

