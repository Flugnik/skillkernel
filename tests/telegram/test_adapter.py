from entrypoints.telegram.adapter import (
    TelegramUpdate,
    core_result_to_telegram_response,
    process_update,
    response_to_send_message_payload,
    telegram_bot_commands,
    telegram_update_to_event,
)
from entrypoints.telegram.main import TelegramHTTPClient
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

    assert response == "[Ошибка] bad request"


def test_core_result_to_telegram_response_marks_confirm():
    result = CoreResult(type="confirm", content="approve plan", meta={})

    response = core_result_to_telegram_response(result)

    assert response == "[Подтверждение] approve plan"


def test_core_result_to_telegram_response_marks_clarify():
    result = CoreResult(type="clarify", content="need more detail", meta={})

    response = core_result_to_telegram_response(result)

    assert response == "[Уточнение] need more detail"


def test_process_update_smoke():
    response = process_update(TelegramUpdate(text="привет", chat_id=42))

    assert response.chat_id == 42
    assert response.text
    assert response.kind in {"message", "clarify", "confirm"}


def test_process_update_handles_start_as_transport_command():
    response = process_update(TelegramUpdate(text="/start", chat_id=42))

    assert response.chat_id == 42
    assert response.kind == "message"
    assert "текстовые запросы" in response.text


def test_process_update_handles_help_as_transport_command():
    response = process_update(TelegramUpdate(text="/help", chat_id=42))

    assert response.chat_id == 42
    assert response.kind == "message"
    assert "/summary 2026-04-02" in response.text
    assert "/export 2026-04-02" in response.text


def test_telegram_bot_commands_include_limiter_menu_items():
    commands = telegram_bot_commands()

    assert [(command.command, command.description) for command in commands] == [
        ("start", "Старт"),
        ("help", "Помощь"),
        ("summary", "Limiter: сводная по дате"),
        ("export", "Limiter: Excel по дате"),
    ]


def test_telegram_confirm_yes_executes_pending_limiter_plan(tmp_path, monkeypatch):
    pending_path = tmp_path / "pending_plans.json"
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("SKILLKERNEL_CONFIG", "")
    monkeypatch.setattr("core.config.load_config", lambda: __import__("core.config", fromlist=["PlatformConfig"]).PlatformConfig(pending_store_path=str(pending_path), log_dir=str(log_dir)))

    from runtime import handler as runtime_handler
    from core.confirm_manager import ConfirmManager
    from core.models import Action, ActionPlan, ActionType

    runtime_handler._DISPATCHER._confirm_manager = ConfirmManager(store_path=str(pending_path))
    plan = ActionPlan(
        skill_name="limiter",
        event_id="evt-1",
        actions=[Action(action_type=ActionType.noop, params={})],
        preview_text="preview",
        requires_confirmation=True,
    )
    runtime_handler._DISPATCHER._confirm_manager.store_plan(plan)

    response = process_update(TelegramUpdate(text="да", chat_id=42))

    assert response.kind == "message"
    assert response.chat_id == 42
    assert "Plan confirmed and executed." in response.text or "Executed" in response.text


def test_telegram_confirm_no_rejects_pending_limiter_plan(tmp_path, monkeypatch):
    pending_path = tmp_path / "pending_plans.json"
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("SKILLKERNEL_CONFIG", "")
    monkeypatch.setattr("core.config.load_config", lambda: __import__("core.config", fromlist=["PlatformConfig"]).PlatformConfig(pending_store_path=str(pending_path), log_dir=str(log_dir)))

    from runtime import handler as runtime_handler
    from core.confirm_manager import ConfirmManager
    from core.models import Action, ActionPlan, ActionType

    runtime_handler._DISPATCHER._confirm_manager = ConfirmManager(store_path=str(pending_path))
    plan = ActionPlan(
        skill_name="limiter",
        event_id="evt-2",
        actions=[Action(action_type=ActionType.noop, params={})],
        preview_text="preview",
        requires_confirmation=True,
    )
    runtime_handler._DISPATCHER._confirm_manager.store_plan(plan)

    response = process_update(TelegramUpdate(text="отмена", chat_id=42))

    assert response.kind == "message"
    assert response.chat_id == 42
    assert "rejected" in response.text.lower() or "отмен" in response.text.lower()


def test_telegram_confirm_yes_without_pending_plan_returns_clear_message(tmp_path, monkeypatch):
    pending_path = tmp_path / "pending_plans.json"
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("SKILLKERNEL_CONFIG", "")
    monkeypatch.setattr("core.config.load_config", lambda: __import__("core.config", fromlist=["PlatformConfig"]).PlatformConfig(pending_store_path=str(pending_path), log_dir=str(log_dir)))

    from runtime import handler as runtime_handler
    from core.confirm_manager import ConfirmManager

    runtime_handler._DISPATCHER._confirm_manager = ConfirmManager(store_path=str(pending_path))

    response = process_update(TelegramUpdate(text="да", chat_id=42))

    assert response.kind == "message"
    assert response.chat_id == 42
    assert "нет активного заказа" in response.text.lower()


def test_response_to_send_message_payload_returns_text_only_payload():
    response = process_update(TelegramUpdate(text="привет", chat_id=42))

    payload = response_to_send_message_payload(response)

    assert payload == {"chat_id": 42, "text": response.text}


def test_response_to_send_message_payload_skips_missing_chat():
    response = process_update(TelegramUpdate(text="hello", chat_id=None))

    payload = response_to_send_message_payload(response)

    assert payload is None


def test_telegram_http_client_uses_httpx_for_get_updates(monkeypatch):
    calls = []

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "result": [{"update_id": 1}, {"update_id": 2}]}

    def fake_get(url, timeout):
        calls.append(("get", url, timeout))
        return DummyResponse()

    monkeypatch.setattr("entrypoints.telegram.main.httpx.get", fake_get)

    client = TelegramHTTPClient(token="token", api_base="https://example.invalid", timeout=12.5)

    updates = client.get_updates(offset=41)

    assert updates == [{"update_id": 1}, {"update_id": 2}]
    assert calls == [("get", "https://example.invalid/bottoken/getUpdates?timeout=25&offset=41", 12.5)]


def test_telegram_http_client_uses_httpx_for_send_message(monkeypatch):
    calls = []

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_post(url, json, timeout):
        calls.append(("post", url, json, timeout))
        return DummyResponse()

    monkeypatch.setattr("entrypoints.telegram.main.httpx.post", fake_post)

    client = TelegramHTTPClient(token="token", api_base="https://example.invalid", timeout=8.0)

    client.send_message(chat_id=123, text="hello")

    assert calls == [
        (
            "post",
            "https://example.invalid/bottoken/sendMessage",
            {"chat_id": 123, "text": "hello"},
            8.0,
        )
    ]

