"""Tests for DSL function library: save, load, execute fn definitions."""
from __future__ import annotations

from fastapi.testclient import TestClient

from kobold_sandbox.assembly_dsl import (
    AsmFunction,
    execute,
    load_library_functions,
    parse_program,
)
from kobold_sandbox.workflow_dsl import WorkflowContext, build_default_builtins


def _make_ctx(**vars_) -> WorkflowContext:
    ctx = WorkflowContext(
        workers={"generator": "http://mock:5001", "analyzer": "http://mock:5001"},
        settings={},
        builtins=build_default_builtins(),
        on_thread=lambda *a, **kw: None,
    )
    for k, v in vars_.items():
        ctx.set(f"${k}", v)
    return ctx


# ---------------------------------------------------------------------------
# fn/save endpoint
# ---------------------------------------------------------------------------

class TestFnSaveEndpoint:
    def test_save_valid_fn(self, tmp_path):
        from kobold_sandbox.server import create_app
        client = TestClient(create_app(str(tmp_path)))

        resp = client.post("/api/dsl/fn/save", json={
            "slug": "fn-double",
            "title": "double",
            "source": "fn double(@x) -> @result:\n  CALL @result, add, @x, @x",
            "tags": ["math"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is True
        assert "double" in data["fn_names"]
        assert data["fn_params"]["double"] == ["@x"]
        assert data["fn_outputs"]["double"] == ["@result"]
        assert data["page"]["page_kind"] == "function_page"

    def test_save_invalid_fn(self, tmp_path):
        from kobold_sandbox.server import create_app
        client = TestClient(create_app(str(tmp_path)))

        resp = client.post("/api/dsl/fn/save", json={
            "slug": "fn-bad",
            "title": "bad",
            "source": "this is not assembly",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] is False
        assert data["error"] is not None

    def test_save_multiple_fns(self, tmp_path):
        from kobold_sandbox.server import create_app
        client = TestClient(create_app(str(tmp_path)))

        source = (
            "fn greet(@name) -> @msg:\n"
            "  MOV @msg, @name\n"
            "\n"
            "fn farewell(@name) -> @msg:\n"
            "  MOV @msg, @name\n"
        )
        resp = client.post("/api/dsl/fn/save", json={
            "slug": "fn-greetings",
            "title": "greetings",
            "source": source,
        })
        data = resp.json()
        assert data["saved"] is True
        assert len(data["fn_names"]) == 2


# ---------------------------------------------------------------------------
# Library fn round-trip: define → load → execute
# ---------------------------------------------------------------------------

class TestFnLibraryRoundTrip:
    def test_define_and_execute_prompt_template(self):
        """Define a prompt template as DSL fn, load it, execute it."""
        source = (
            'fn make_prompt(@text) -> @prompt:\n'
            '  MOV @prefix, "Analyze this: "\n'
            '  CALL @prompt, concat, @prefix, @text\n'
        )
        pages = [{"blocks": [{"text": source}]}]
        lib_fns = load_library_functions(pages)

        assert "make_prompt" in lib_fns

        code = 'CALL @result, make_prompt, "hello world"'
        ctx = _make_ctx()
        result = execute(code, ctx, extra_functions=lib_fns)
        assert result.error is None
        # concat of string + string gives list ["Analyze this: ", "hello world"]
        val = result.state.get("result")
        assert val is not None

    def test_library_fn_with_each(self):
        """Library fn used inside EACH loop."""
        source = 'fn inc(@x) -> @result:\n  CALL @result, add, @x, 1\n'
        pages = [{"blocks": [{"text": source}]}]
        lib_fns = load_library_functions(pages)

        code = """\
MOV @items, @data
EACH @item, @items, +1
  CALL @item.incremented, inc, @item.value
"""
        ctx = _make_ctx(data=[{"value": 10}, {"value": 20}])
        result = execute(code, ctx, extra_functions=lib_fns)
        assert result.error is None
        items = result.state.get("items")
        assert items[0]["incremented"] == 11
        assert items[1]["incremented"] == 21

    def test_library_fn_overrides_builtin(self):
        """Library fn with same name as builtin takes priority."""
        # Custom 'numbered' that adds prefix ">> "
        source = 'fn custom_num(@text) -> @result:\n  CALL @result, numbered, @text\n'
        pages = [{"blocks": [{"text": source}]}]
        lib_fns = load_library_functions(pages)

        code = 'CALL @val, custom_num, "test"'
        ctx = _make_ctx()
        result = execute(code, ctx, extra_functions=lib_fns)
        assert result.error is None
        assert result.state.get("val") == "1. test"


# ---------------------------------------------------------------------------
# probe annotation endpoint (regex fallback, no LLM)
# ---------------------------------------------------------------------------

class TestProbeAnnotationEndpoint:
    def test_probe_regex_fallback(self, tmp_path):
        from kobold_sandbox.server import create_app
        client = TestClient(create_app(str(tmp_path)))

        message = {
            "message_id": "msg_test_001",
            "containers": [
                {
                    "kind": "text",
                    "name": "main_text",
                    "data": {
                        "text": "Demoness with glowing amber eyes and flowing silver hair in a proud anime pose."
                    }
                }
            ],
        }
        constraints = [
            {"name": "eye_color", "tags": ["appearance", "eyes"], "probe_prompt": "amber eyes"},
            {"name": "hair_color", "tags": ["appearance", "hair"], "probe_prompt": "silver hair"},
        ]

        resp = client.post("/api/dsl/annotations/probe", json={
            "message": message,
            "constraints": constraints,
            "workers": {},  # empty = regex fallback
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert data["annotations_added"] == 2

        result_msg = data["message"]
        annotations = result_msg["annotations"]
        assert len(annotations) == 2

        eye_ann = annotations[0]
        assert eye_ann["source"]["char_start"] >= 0
        assert eye_ann["source"]["char_end"] > eye_ann["source"]["char_start"]
        assert "appearance" in eye_ann["tags"]
        assert "eyes" in eye_ann["tags"]

        hair_ann = annotations[1]
        assert hair_ann["meta"]["label"] == "hair_color"

    def test_probe_no_match(self, tmp_path):
        from kobold_sandbox.server import create_app
        client = TestClient(create_app(str(tmp_path)))

        message = {
            "message_id": "msg_test_002",
            "containers": [
                {"kind": "text", "name": "main_text", "data": {"text": "A simple text."}}
            ],
        }
        constraints = [
            {"name": "missing", "tags": ["test"], "probe_prompt": "nonexistent phrase"},
        ]

        resp = client.post("/api/dsl/annotations/probe", json={
            "message": message,
            "constraints": constraints,
            "workers": {},
        })
        data = resp.json()
        assert data["annotations_added"] == 0

    def test_probe_preserves_existing_annotations(self, tmp_path):
        from kobold_sandbox.server import create_app
        client = TestClient(create_app(str(tmp_path)))

        message = {
            "message_id": "msg_test_003",
            "containers": [
                {"kind": "text", "name": "main_text", "data": {"text": "amber eyes glow"}}
            ],
            "annotations": [
                {"kind": "existing", "tags": ["old"]}
            ],
        }
        constraints = [
            {"name": "eye", "tags": ["eyes"], "probe_prompt": "amber"},
        ]

        resp = client.post("/api/dsl/annotations/probe", json={
            "message": message,
            "constraints": constraints,
            "workers": {},
        })
        data = resp.json()
        # Should have old annotation + new one
        assert len(data["message"]["annotations"]) == 2
