from kobold_sandbox.gateway_runtime import _interpolate_text, _parse_messages
import time

from kobold_sandbox.gateway_runtime import GatewayJob, GatewayRuntime


def test_interpolate_text_supports_dollar_brace_and_dotted_paths() -> None:
    state = {
        "item": {
            "local_id": 3,
            "answer": "anime demoness",
        },
        "numbered_answer": "1. anime demoness",
    }

    text = "Блок #${item.local_id}: ${item.answer} / $numbered_answer"
    assert _interpolate_text(text, state) == "Блок #3: anime demoness / 1. anime demoness"


def test_parse_messages_interpolates_assistant_templates() -> None:
    state = {
        "item": {"local_id": 2, "answer": "green eyes"},
        "numbered_answer": "1. green eyes",
    }

    messages = _parse_messages(
        [
            {"user": "$numbered_answer"},
            {"assistant": "Блок #${item.local_id}: ${item.answer}"},
        ],
        state,
    )

    assert messages[0]["content"] == "1. green eyes"
    assert messages[1]["content"] == "Блок #2: green eyes"


def test_from_yaml_supports_on_as_list_handlers() -> None:
    runtime = GatewayRuntime.from_yaml(
        """
workflow: test_v3
version: 3
input: hello
jobs:
  - id: answer
    worker: generator
    payload: $input
job_templates:
  trim_probe:
    worker: generator
    payload: test
on:
  - job: answer
    event: done
    do: |
      MOV @handled, true
  - job: trim_probe
    event: done
    do: |
      MOV @templated, true
  - all_done: [answer]
    do: |
      MOV @all_done_seen, true
""".strip(),
        workers={"generator": "http://127.0.0.1:5001"},
        settings={},
    )

    try:
        assert "answer.done" in runtime._subs
        assert len(runtime._subs["answer.done"]) == 1
        assert "trim_probe.*.done" in runtime._subs
        assert len(runtime._subs["trim_probe.*.done"]) == 1
        assert len(runtime._all_done_subs) == 1
        assert runtime._all_done_subs[0].wait_for == ["answer"]
    finally:
        runtime.shutdown()


def test_template_subscription_matches_both_direct_and_wildcard_job_ids() -> None:
    runtime = GatewayRuntime.from_yaml(
        """
workflow: test_v3
version: 3
job_templates:
  table:
    worker: generator
    payload: test
on:
  - job: table
    event: done
    do: |
      MOV @handled, true
""".strip(),
        workers={"generator": "http://127.0.0.1:5001"},
        settings={},
    )
    try:
        assert "table.done" in runtime._subs
        assert "table.*.done" in runtime._subs
    finally:
        runtime.shutdown()


def test_completed_job_result_is_mirrored_into_workflow_state() -> None:
    runtime = GatewayRuntime(workers={"generator": "http://127.0.0.1:5001"}, settings={})
    try:
        runtime._execute_job = lambda job: "answer-text"  # type: ignore[method-assign]
        runtime.enqueue(GatewayJob(id="answer", worker="generator", payload="hello"))
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if runtime._wf_ctx.state.get("answer") == "answer-text":
                break
            time.sleep(0.05)
        assert runtime._wf_ctx.state.get("answer") == "answer-text"
        assert runtime.state.get("answer") == "answer-text"
    finally:
        runtime.shutdown()


def test_initial_jobs_resolve_config_refs_for_probe_fields() -> None:
    runtime = GatewayRuntime.from_yaml(
        """
workflow: test_v3
version: 3
input: hello
config:
  params_int:
    grammar: |
      root ::= digits
      digits ::= [0-9]+
    capture: "[0-9]+"
    coerce: int
jobs:
  - id: count_probe
    worker: generator
    mode: probe
    grammar: $config.params_int.grammar
    capture:
      regex: $config.params_int.capture
      coerce: $config.params_int.coerce
    stop: [" "]
    messages:
      - user: $input
      - assistant: "Count:"
""".strip(),
        workers={"generator": "http://127.0.0.1:5001"},
        settings={},
    )

    try:
        job = runtime.get_job("count_probe")
        assert job is not None
        assert isinstance(job.grammar, str)
        assert "root ::= digits" in job.grammar
        assert job.capture == "[0-9]+"
        assert job.coerce == "int"
        assert job.messages is not None
        assert job.messages[0]["content"] == "hello"
    finally:
        runtime.shutdown()


def test_template_job_infers_item_from_items_and_item_idx() -> None:
    runtime = GatewayRuntime.from_yaml(
        """
workflow: test_v3
version: 3
job_templates:
  start_probe:
    worker: generator
    mode: probe_continue
    messages:
      - user: hello
      - assistant: "Block #${item.local_id}"
""".strip(),
        workers={"generator": "http://127.0.0.1:5001"},
        settings={},
    )
    try:
        runtime.state["items"] = [{"local_id": 1}, {"local_id": 2}]
        job = runtime._instantiate_template("start_probe", "start_probe.1", {"item_idx": 1})
        assert job is not None
        assert job.context["item_idx"] == 1
        assert job.context["item"]["local_id"] == 2
        assert job.messages is not None
        assert job.messages[1]["content"] == "Block #2"
        skipped = runtime._instantiate_template("start_probe", "start_probe.9", {"item_idx": 9})
        assert skipped is None
    finally:
        runtime.shutdown()


def test_then_with_item_idx_zero_is_preserved() -> None:
    runtime = GatewayRuntime(workers={"generator": "http://127.0.0.1:5001"}, settings={})
    try:
        runtime.state["items"] = [{"local_id": 1}]
        runtime._templates["trim_probe"] = {
            "worker": "generator",
            "mode": "probe_continue",
            "messages": [
                {"user": "x"},
                {"assistant": "Block #${item.local_id}"},
            ],
        }
        parent = GatewayJob(
            id="start_probe.0",
            worker="generator",
            payload="x",
            context={"item_idx": 0, "item": {"local_id": 1}},
        )
        runtime._jobs[parent.id] = parent
        runtime._process_then({"enqueue": "trim_probe", "with": {"item_idx": "$item_idx"}}, event=type("E", (), {"job_id": parent.id})())
        job = runtime.get_job("trim_probe.0")
        assert job is not None
        assert job.context["item_idx"] == 0
        assert job.context["item"]["local_id"] == 1
    finally:
        runtime.shutdown()


def test_then_enqueue_template_uses_item_idx_suffix_for_job_id() -> None:
    runtime = GatewayRuntime(workers={"generator": "http://127.0.0.1:5001"}, settings={})
    try:
        runtime.state["items"] = [{"local_id": 1}]
        runtime._templates["start_probe"] = {
            "worker": "generator",
            "mode": "probe_continue",
            "messages": [{"user": "x"}],
        }
        runtime._process_then({"enqueue": "start_probe", "with": {"item_idx": 0}}, event=type("E", (), {"job_id": "count_probe"})())
        job = runtime.get_job("start_probe.0")
        assert job is not None
        assert job.context["item_idx"] == 0
    finally:
        runtime.shutdown()


def test_initial_job_supports_payload_template_text_and_context() -> None:
    runtime = GatewayRuntime.from_yaml(
        """
workflow: test_v3
version: 3
context:
  user_prompt: hello
payload_templates:
  user_instruct:
    mode: text
    template: "INPUT: ${input}"
jobs:
  - id: answer
    worker: generator
    payload_from: user_instruct
    payload_args:
      input: $context.user_prompt
""".strip(),
        workers={"generator": "http://127.0.0.1:5001"},
        settings={},
    )
    try:
        job = runtime.get_job("answer")
        assert job is not None
        assert job.payload == "INPUT: hello"
        assert job.messages is None
        assert runtime.state["context"]["user_prompt"] == "hello"
    finally:
        runtime.shutdown()


def test_template_job_supports_payload_template_chat() -> None:
    runtime = GatewayRuntime.from_yaml(
        """
workflow: test_v3
version: 3
context:
  user_prompt: hello
payload_templates:
  user_chat:
    mode: chat
    messages:
      - role: ${role}
        content: ${input}
job_templates:
  answer_probe:
    worker: generator
    payload_from: user_chat
    payload_args:
      role: user
      input: $context.user_prompt
""".strip(),
        workers={"generator": "http://127.0.0.1:5001"},
        settings={},
    )
    try:
        job = runtime._instantiate_template("answer_probe", "answer_probe", {})
        assert job is not None
        assert job.payload == ""
        assert job.messages == [{"role": "user", "content": "hello"}]
    finally:
        runtime.shutdown()


def test_payload_template_args_support_builtin_expressions() -> None:
    runtime = GatewayRuntime.from_yaml(
        """
workflow: test_v3
version: 3
context:
  user_prompt: hello
payload_templates:
  user_instruct:
    mode: text
    template: ${input}
jobs:
  - id: claims
    worker: generator
    payload_from: user_instruct
    payload_args:
      input: claims($context.user_prompt)
""".strip(),
        workers={"generator": "http://127.0.0.1:5001"},
        settings={},
    )
    try:
        job = runtime.get_job("claims")
        assert job is not None
        assert "hello" in job.payload
        assert "AXIOMS" in job.payload or "ENTITIES" in job.payload or "Текст" in job.payload
    finally:
        runtime.shutdown()


def test_table_done_handler_enqueues_end_line_probe_jobs() -> None:
    runtime = GatewayRuntime.from_yaml(
        """
workflow: test_v3
version: 3
job_templates:
  table:
    worker: generator
    payload: dummy
  end_line_probe:
    worker: generator
    mode: probe
    messages:
      - user: x
      - assistant: "line number:"
on:
  - job: table
    event: done
    do: |
      CALL @entity_nodes, parse_table_rows, @table
      MOV @root.entities, @entity_nodes
    then:
      - enqueue: end_line_probe
        for_each: entity_nodes
""".strip(),
        workers={"generator": "http://127.0.0.1:5001"},
        settings={},
    )
    try:
        table_job = GatewayJob(id="table", worker="generator", payload="dummy")
        table_job.status = type("S", (), {"value": "done"})()  # unused placeholder
        runtime._jobs["table"] = table_job
        runtime.state["table"] = "| # | name | detail |\n|---|---|---|\n| 1 | a | x |\n| 2 | b | y |"
        runtime._wf_ctx.vars["table"] = runtime.state["table"]
        runtime._fire_event(type("E", (), {"job_id": "table", "event_type": "done", "result": runtime.state["table"], "error": None, "timestamp": 0})())
        assert runtime.get_job("end_line_probe.0") is not None
        assert runtime.get_job("end_line_probe.1") is not None
    finally:
        runtime.shutdown()
