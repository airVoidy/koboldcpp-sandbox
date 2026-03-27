from pathlib import Path

from typer.testing import CliRunner

import kobold_sandbox.cli as cli_module
from kobold_sandbox.llm_continue import LLMResult


def test_continue_generate_uses_llm_continue_with_expected_options(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_llm_call_with_continue(base_url, messages, **kwargs):
        captured["base_url"] = base_url
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        return LLMResult(
            raw="raw",
            answer="answer text",
            think="",
            continues=1,
            finish_reason="stop",
            prompt_mode="instruct",
            latency_ms=12,
        )

    monkeypatch.setattr(cli_module, "llm_call_with_continue", fake_llm_call_with_continue)
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("hello from file", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        cli_module.app,
        [
            "continue-generate",
            "--prompt-file",
            str(prompt_file),
            "--stop",
            "END_DSL",
            "--stop",
            "\n###",
            "--max-continue",
            "3",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert '"answer": "answer text"' in result.stdout
    assert captured["base_url"] == "http://127.0.0.1:5001"
    assert captured["messages"] == [{"role": "user", "content": "hello from file"}]
    assert captured["kwargs"] == {
        "temperature": 0.2,
        "max_tokens": 256,
        "no_think": True,
        "max_continue": 3,
        "continue_on_length": True,
        "stop": ["END_DSL", "\n###"],
        "prompt_mode": "instruct",
    }
