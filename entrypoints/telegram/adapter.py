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


def core_result_to_telegram_response(result: CoreResult) -> str | dict[str, object]:
    """Convert runtime output into a Telegram-friendly response payload."""

    if result.type == "error":
        return f"[error] {result.content}"
    return result.content


def process_update(update: TelegramUpdate) -> TelegramResponse:
    """Handle a Telegram update via the shared runtime handler."""

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

