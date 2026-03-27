from kobold_sandbox.event_dsl import EmitStatement, OnStatement, compile_event_dsl, parse_event_dsl


SAMPLE_DSL = """
emit("task.input", {
  data: {
    text: "hello"
  }
})

emit("generate.request", {
  schema: "native_generate_request",
  defaults: "native_generate_defaults",
  data: {
    prompt: @task.input.text,
    model: "local-model",
    max_length: 256
  },
  checks: ["complete"]
})

on("generate.request", "response", {
  bind: "generate.response",
  schema: "native_generate_response",
  checks: ["complete"],
  emit: ["response.output_message"],
  project: ["response.table"]
})
""".strip()


def test_parse_event_dsl_returns_emit_and_on_statements() -> None:
    statements = parse_event_dsl(SAMPLE_DSL)

    assert len(statements) == 3
    assert isinstance(statements[0], EmitStatement)
    assert statements[0].name == "task.input"
    assert statements[0].spec["data"]["text"] == "hello"
    assert isinstance(statements[2], OnStatement)
    assert statements[2].source == "generate.request"
    assert statements[2].event == "response"
    assert statements[2].spec["bind"] == "generate.response"


def test_compile_event_dsl_expands_generate_flow_to_assembly() -> None:
    assembly = compile_event_dsl(SAMPLE_DSL)

    assert 'MOV  @task.input.text, "hello"' in assembly
    assert 'MOV  @generate.request.temperature, 0.2' in assembly
    assert 'MOV  @generate.request.prompt, @task.input.text' in assembly
    assert 'CALL @generate.request.check, check_complete, @generate.request, schema:"native_generate_request"' in assembly
    assert "GEN  @generate.call.raw, @task.input.text, worker:generator, temp:0.2, max:256" in assembly
    assert "CALL @generate.response, bind_native_generate_response, @generate.call.raw" in assembly
    assert 'CALL @generate.response.check, check_complete, @generate.response, schema:"native_generate_response"' in assembly
    assert "CALL @response.output_message, emit_output_message, @generate.response" in assembly
    assert "CALL @response.table, build_table_from_text, @generate.response.raw_text" in assembly
