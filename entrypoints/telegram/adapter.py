"""Minimal Telegram adapter over the runtime contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from runtime.contract import CoreEvent, CoreResult
from runtime.handler import handle


@dataclass(frozen=True)
class TelegramUpdate:
    """Thin representation of an incoming Telegram message."""

    text: str
    chat_id: int | None = None
    message_id: int | None = None


@dataclass(frozen=True)
class TelegramResponse:
    """Thin representation of a Telegram reply."""

    chat_id: int | None
    text: str
    kind: str
    meta: dict[str, object]


@dataclass(frozen=True)
class TelegramBotCommand:
    """Telegram bot command definition for menu registration."""

    command: str
    description: str


def telegram_update_to_event(update: TelegramUpdate) -> CoreEvent:
    """Convert a Telegram update into the runtime input contract."""

    return CoreEvent(
        text=update.text,
        meta={
            "source": "telegram",
            "chat_id": update.chat_id,
            "message_id": update.message_id,
        },
    )


def _normalize_transport_command(text: str) -> str | None:
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    command = stripped.split()[0].split("@", 1)[0]
    if command == "/start":
        return "start"
    if command == "/help":
        return "help"
    return None


def telegram_bot_commands() -> list[TelegramBotCommand]:
    """Return the bot menu commands registered in Telegram."""

    return [
        TelegramBotCommand(command="start", description="Старт"),
        TelegramBotCommand(command="help", description="Помощь"),
        TelegramBotCommand(command="summary", description="Limiter: сводная по дате"),
        TelegramBotCommand(command="export", description="Limiter: Excel по дате"),
    ]


def _transport_command_response(command: str) -> TelegramResponse:
    if command == "start":
        text = (
            "Привет. Я принимаю текстовые запросы и передаю их в систему.\n"
            "Просто отправьте сообщение с вашим запросом."
        )
    else:
        text = (
            "Примеры запросов:\n"
            "- /summary 2026-04-02\n"
            "- /export 2026-04-02\n"
            "- сколько осталось на складе?\n"
            "- спланируй производство на завтра\n"
            "- проверь лимит по продукту"
        )
    return TelegramResponse(chat_id=None, text=text, kind="message", meta={"source": "telegram", "transport_command": command})


def core_result_to_telegram_response(result: CoreResult) -> str | dict[str, object]:
    """Convert runtime output into a Telegram-friendly response payload."""

    if result.type == "error":
        return f"[Ошибка] {result.content}"
    if result.type == "confirm":
        return f"[Подтверждение] {result.content}"
    if result.type == "clarify":
        return f"[Уточнение] {result.content}"
    return result.content


def process_update(update: TelegramUpdate) -> TelegramResponse:
    """Handle a Telegram update via the shared runtime handler."""

    command = _normalize_transport_command(update.text)
    if command is not None:
        return TelegramResponse(
            chat_id=update.chat_id,
            text=_transport_command_response(command).text,
            kind="message",
            meta={"source": "telegram", "transport_command": command},
        )

    result = handle(telegram_update_to_event(update))
    payload = core_result_to_telegram_response(result)
    text = payload if isinstance(payload, str) else str(payload)
    return TelegramResponse(
        chat_id=update.chat_id,
        text=text,
        kind=result.type,
        meta=dict(result.meta),
    )


def response_to_send_message_payload(response: TelegramResponse) -> dict[str, Any] | None:
    """Build a Telegram sendMessage payload for text-only responses."""

    if response.chat_id is None or not response.text.strip():
        return None
    return {"chat_id": response.chat_id, "text": response.text}

