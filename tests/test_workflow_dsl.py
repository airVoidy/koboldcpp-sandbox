from __future__ import annotations

from typing import Any

from kobold_sandbox.workflow_dsl import run_workflow


class _FakeResponse:
    def __init__(self, content: str, *, finish_reason: str = "stop") -> None:
        self._content = content
        self._finish_reason = finish_reason

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {
            "choices": [
                {
                    "message": {"content": self._content},
                    "finish_reason": self._finish_reason,
                }
            ]
        }


class _FakeHttpClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, _url: str, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append(json)
        return _FakeResponse("1")

    def close(self) -> None:
        return None


def test_verify_axioms_keeps_full_think_trace(monkeypatch) -> None:
    thread: list[dict[str, Any]] = []

    import kobold_sandbox.workflow_dsl as workflow_dsl

    monkeypatch.setattr(workflow_dsl.httpx, "Client", _FakeHttpClient)

    yaml_text = """
dsl: workflow/v2

let:
  axioms:
    - demoness has 4 descriptions
  hypotheses:
    - hair colors differ
  answer: "full answer"
  table: |
    | Trait | Value |
    | :--- | :--- |
    | Hair | Blue |

flow:
  - verify_axioms:
      items: concat($axioms, $hypotheses)
      answer: $answer
      table: $table
      worker: analyzer
      tag: verify
"""

    ctx = run_workflow(
        yaml_text=yaml_text,
        workers={"analyzer": "http://fake-worker"},
        on_thread=lambda role, name, content, extra=None: thread.append(
            {
                "role": role,
                "name": name,
                "content": content,
                "extra": extra or {},
            }
        ),
    )
    ctx.close()

    verifier_messages = [item for item in thread if item["role"] == "verifier"]
    assert len(verifier_messages) == 1

    message = verifier_messages[0]
    think = str(message["extra"].get("think", ""))
    content = str(message["content"])

    assert "Summary table:" in think
    assert "Verification:" in think
    assert "((Table matches truth) == 1) === 1" in think
    assert "((demoness has 4 descriptions) == 1) === 1" in think
    assert "((hair colors differ) == 1) === 1" in think
    assert "Table matches truth = 1" in content
    assert "demoness has 4 descriptions = 1" in content
    assert "hair colors differ = 1" in content


class _LengthThenStopHttpClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, _url: str, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append(json)
        if len(self.calls) == 1:
            return _FakeResponse("partial", finish_reason="length")
        return _FakeResponse(" tail", finish_reason="stop")

    def close(self) -> None:
        return None


class _MaxTokensThenStopHttpClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, _url: str, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append(json)
        if len(self.calls) == 1:
            return _FakeResponse("partial", finish_reason="max_tokens")
        return _FakeResponse(" tail", finish_reason="stop")

    def close(self) -> None:
        return None


class _ProbeGrammarHttpClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, _url: str, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append(json)
        if len(self.calls) == 1:
            return _FakeResponse("10", finish_reason="length")
        return _FakeResponse('"', finish_reason="stop")

    def close(self) -> None:
        return None


class _PromptOpenThinkHttpClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []

    def post(self, _url: str, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append(json)
        if len(self.calls) == 1:
            return _FakeResponse("<think>\nreasoning...", finish_reason="max_tokens")
        return _FakeResponse("</think>\nENTITIES: [demo]\nAXIOMS:\n- fact\nHYPOTHESES:\n- guess", finish_reason="stop")

    def close(self) -> None:
        return None


class _PromptCaptureHttpClient:
    last_instance: "_PromptCaptureHttpClient | None" = None

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.calls: list[dict[str, Any]] = []
        _PromptCaptureHttpClient.last_instance = self

    def post(self, _url: str, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append(json)
        return _FakeResponse("ok")

    def close(self) -> None:
        return None


def test_prompt_mode_auto_continues_on_token_limit(monkeypatch) -> None:
    import kobold_sandbox.workflow_dsl as workflow_dsl

    monkeypatch.setattr(workflow_dsl.httpx, "Client", _LengthThenStopHttpClient)

    ctx = workflow_dsl.WorkflowContext(workers={"analyzer": "http://fake-worker"})
    result = ctx.llm_call(
        "analyzer",
        prompt="claims($input)",
        mode="prompt",
        max_tokens=16,
    )
    http_client = ctx._http
    ctx.close()

    assert result == "partial tail"
    assert len(http_client.calls) == 2


def test_continue_mode_auto_continues_on_length(monkeypatch) -> None:
    import kobold_sandbox.workflow_dsl as workflow_dsl

    monkeypatch.setattr(workflow_dsl.httpx, "Client", _LengthThenStopHttpClient)

    ctx = workflow_dsl.WorkflowContext(workers={"analyzer": "http://fake-worker"})
    result = ctx.llm_call(
        "analyzer",
        messages=[{"role": "user", "content": "continue"}],
        mode="continue",
        max_tokens=16,
    )
    http_client = ctx._http
    ctx.close()

    assert result == "partial tail"
    assert len(http_client.calls) == 2


def test_continue_mode_auto_continues_on_max_tokens(monkeypatch) -> None:
    import kobold_sandbox.workflow_dsl as workflow_dsl

    monkeypatch.setattr(workflow_dsl.httpx, "Client", _MaxTokensThenStopHttpClient)

    ctx = workflow_dsl.WorkflowContext(workers={"analyzer": "http://fake-worker"})
    result = ctx.llm_call(
        "analyzer",
        messages=[{"role": "user", "content": "continue"}],
        mode="continue",
        max_tokens=16,
    )
    http_client = ctx._http
    ctx.close()

    assert result == "partial tail"
    assert len(http_client.calls) == 2


def test_probe_continue_supports_generation_grammar_and_capture_regex(monkeypatch) -> None:
    import kobold_sandbox.workflow_dsl as workflow_dsl

    monkeypatch.setattr(workflow_dsl.httpx, "Client", _ProbeGrammarHttpClient)

    ctx = workflow_dsl.WorkflowContext(workers={"generator": "http://fake-worker"})
    result = ctx.llm_call(
        "generator",
        messages=[
            {"role": "user", "content": "numbered answer"},
            {"role": "assistant", "content": "<think>\nline number:"},
        ],
        mode="probe_continue",
        grammar='root ::= digits term?\ndigits ::= [0-9]+\nterm ::= " " | "\\n" | "\\""',
        capture={"regex": "[0-9]+", "coerce": "int"},
        max_tokens=3,
    )
    http_client = ctx._http
    ctx.close()

    assert result == "10"
    assert len(http_client.calls) == 1
    assert "root ::= digits term?" in http_client.calls[0]["grammar"]
    assert "root ::= digits term?" in http_client.calls[0]["grammar_string"]


def test_slice_lines_treats_end_as_inclusive() -> None:
    yaml_text = """
dsl: workflow/v2
let:
  text: |
    line 1
    line 2
    line 3
flow:
  - set:
      "@result": slice_lines($text, 2, 3)
"""

    ctx = run_workflow(yaml_text=yaml_text, workers={})
    try:
        assert ctx.state["result"] == "line 2\nline 3"
    finally:
        ctx.close()


def test_prompt_mode_recovers_when_response_stops_inside_think(monkeypatch) -> None:
    import kobold_sandbox.workflow_dsl as workflow_dsl

    monkeypatch.setattr(workflow_dsl.httpx, "Client", _PromptOpenThinkHttpClient)

    ctx = workflow_dsl.WorkflowContext(workers={"analyzer": "http://fake-worker"})
    result = ctx.llm_call(
        "analyzer",
        prompt="claims($input)",
        mode="prompt",
        max_tokens=32,
    )
    http_client = ctx._http
    ctx.close()

    assert "ENTITIES: [demo]" in result
    assert "AXIOMS:" in result
    assert len(http_client.calls) == 2


def test_run_workflow_can_override_input_var(monkeypatch) -> None:
    import kobold_sandbox.workflow_dsl as workflow_dsl

    monkeypatch.setattr(workflow_dsl.httpx, "Client", _PromptCaptureHttpClient)

    yaml_text = """
dsl: workflow/v2

let:
  input: "from yaml"

flow:
  - generator -> $answer:
      prompt: $input
      max_tokens: 8
"""

    ctx = run_workflow(
        yaml_text=yaml_text,
        workers={"generator": "http://fake-worker"},
        initial_vars={"$input": "from request"},
    )
    http_client = _PromptCaptureHttpClient.last_instance
    ctx.close()

    assert http_client is not None
    assert http_client.calls[0]["messages"][0]["content"] == "from request"
