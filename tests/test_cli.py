from entrypoints.cli.adapter import process_text
from entrypoints.cli.main import main


def test_cli_smoke_process_text():
    result = process_text("привет")

    assert result.type in {"message", "clarify", "confirm", "error"}
    assert isinstance(result.content, str)


def test_cli_main_smoke(capsys):
    exit_code = main(["привет"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "[" in captured.out
