from kobold_sandbox.atomic_table_object import KoboldGenerateSchema, NativeGenerateRequestSchema


def test_kobold_generate_schema_from_json_and_alias_access() -> None:
    schema = KoboldGenerateSchema.from_json(
        {
            "max_context_length": 2048,
            "max_length": 100,
            "prompt": "Niko the kobold...",
            "temperature": 0.5,
            "top_p": 0.9,
        }
    )

    assert schema.get("temperature") == 0.5
    assert schema.get("gen.temp") == 0.5
    assert schema.get("nucleus") == 0.9

    schema.set("gen.temp", 0.7)
    schema.set("nucleus", 0.95)

    assert schema.get("temperature") == 0.7
    assert schema.get("top_p") == 0.95


def test_kobold_generate_schema_table_rows_and_envelope() -> None:
    schema = KoboldGenerateSchema.from_json(
        {
            "prompt": "Example prompt",
            "temperature": 0.5,
        }
    )

    rows = schema.to_table_rows()
    temp_row = next(row for row in rows if row["field"] == "temperature")
    prompt_row = next(row for row in rows if row["field"] == "prompt")

    assert temp_row["group"] == "sampler"
    assert temp_row["path"] == "generate.params.temperature"
    assert "gen.temp" in temp_row["aliases"]
    assert prompt_row["value"] == "Example prompt"

    envelope = schema.to_envelope(meta_data={"source_message_ref": "msg_001"})
    assert envelope["table_data"]["schema_name"] == "kobold_generate"
    assert envelope["meta_data"]["source_message_ref"] == "msg_001"
    assert len(envelope["table_data"]["rows"]) == len(rows)


def test_kobold_generate_schema_to_json_by_alias() -> None:
    schema = KoboldGenerateSchema.from_json({"temperature": 0.5, "top_p": 0.9})
    aliased = schema.to_json(by_alias=True)

    assert aliased["gen.temp"] == 0.5
    assert aliased["sampler.top_p"] == 0.9


def test_native_generate_request_schema_matches_repo_endpoint_contract() -> None:
    schema = NativeGenerateRequestSchema.from_json(
        {
            "prompt": "Write 4 demoness descriptions.",
            "temperature": 0.35,
            "max_length": 256,
            "model": "local-model",
        }
    )

    assert schema.get("prompt") == "Write 4 demoness descriptions."
    assert schema.get("gen.temp") == 0.35
    assert schema.get("request.max_length") == 256

    rows = schema.to_table_rows()
    prompt_row = next(row for row in rows if row["field"] == "prompt")
    model_row = next(row for row in rows if row["field"] == "model")
    assert prompt_row["required"] is True
    assert prompt_row["path"] == "generate.request.prompt"
    assert model_row["group"] == "routing"

    payload = schema.to_json()
    assert payload == {
        "prompt": "Write 4 demoness descriptions.",
        "temperature": 0.35,
        "max_length": 256,
        "model": "local-model",
    }

    envelope = schema.to_envelope(meta_data={"endpoint": "/api/v1/generate"})
    assert envelope["table_data"]["schema_name"] == "native_generate_request"
    assert envelope["meta_data"]["endpoint"] == "/api/v1/generate"
