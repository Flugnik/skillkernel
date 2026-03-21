from runtime.contract import CoreEvent
from runtime.handler import handle


def test_runtime_handle_returns_core_result():
    result = handle(CoreEvent(text="привет", meta={"source": "cli"}))

    assert result.type in {"message", "clarify", "confirm", "error"}
    assert isinstance(result.content, str)

