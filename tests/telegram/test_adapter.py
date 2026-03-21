from entrypoints.telegram.adapter import (
    TelegramUpdate,
    core_result_to_telegram_response,
    process_update,
    response_to_send_message_payload,
    telegram_update_to_event,
)
from runtime.contract import CoreResult


def test_update_to_core_event_sets_telegram_source():
    update = TelegramUpdate(text="/days", chat_id=123, message_id=7)

    event = telegram_update_to_event(update)

    assert event.text == "/days"
    assert event.meta["source"] == "telegram"
    assert event.meta["chat_id"] == 123
    assert event.meta["message_id"] == 7


def test_core_result_to_telegram_response_returns_text_for_message():
    result = CoreResult(type="message", content="pong", meta={"plan_id": "p-1"})

    response = core_result_to_telegram_response(result)

    assert response == "pong"


def test_core_result_to_telegram_response_returns_string_when_plain_message():
    result = CoreResult(type="message", content="pong", meta={})

    response = core_result_to_telegram_response(result)

    assert response == "pong"


def test_core_result_to_telegram_response_marks_error():
    result = CoreResult(type="error", content="bad request", meta={})

    response = core_result_to_telegram_response(result)

    assert response == "[error] bad request"


def test_process_update_smoke():
    response = process_update(TelegramUpdate(text="привет", chat_id=42))

    assert response.chat_id == 42
    assert response.text
    assert response.kind in {"message", "clarify", "confirm"}


def test_response_to_send_message_payload_returns_text_only_payload():
    response = process_update(TelegramUpdate(text="привет", chat_id=42))

    payload = response_to_send_message_payload(response)

    assert payload == {"chat_id": 42, "text": response.text}


def test_response_to_send_message_payload_skips_missing_chat():
    response = process_update(TelegramUpdate(text="hello", chat_id=None))

    payload = response_to_send_message_payload(response)

    assert payload is None

