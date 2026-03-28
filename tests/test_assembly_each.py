"""Tests for EACH opcode, capture/coerce in GEN, and dsl_builtins registration."""
from __future__ import annotations

from unittest.mock import patch

from kobold_sandbox.assembly_dsl import (
    AsmResult,
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
# EACH opcode
# ---------------------------------------------------------------------------

class TestEachOpcode:
    def test_each_iterates_list_of_dicts(self):
        code = """\
MOV @items, @data
EACH @item, @items, +1
  MOV @item.visited, true
"""
        ctx = _make_ctx(data=[{"name": "a"}, {"name": "b"}])
        result = execute(code, ctx)
        assert result.error is None
        items = result.state.get("items")
        assert isinstance(items, list)
        assert len(items) == 2
        assert items[0]["visited"] is True
        assert items[1]["visited"] is True

    def test_each_simple_accumulation(self):
        code = """\
MOV @sum, 0
MOV @items, @data
EACH @item, @items, +2
  CALL @val, len, @item
  CALL @sum, add, @sum, @val
"""
        ctx = _make_ctx(data=[{"a": 1, "b": 2}, {"x": 10}])
        result = execute(code, ctx)
        assert result.error is None
        # len of dict with 2+_index keys = 3, len of dict with 1+_index = 2 → 5
        assert result.state.get("sum") == 5

    def test_each_empty_list(self):
        code = """\
MOV @items, @data
EACH @item, @items, +1
  MOV @item, "modified"
"""
        ctx = _make_ctx(data=[])
        result = execute(code, ctx)
        assert result.error is None

    def test_each_with_dict_items(self):
        code = """\
MOV @items, @entities
EACH @entity, @items, +1
  MOV @entity.processed, true
"""
        entities = [
            {"name": "Alice", "score": 10},
            {"name": "Bob", "score": 20},
        ]
        ctx = _make_ctx(entities=entities)
        result = execute(code, ctx)
        assert result.error is None
        items = result.state.get("items")
        assert items[0]["processed"] is True
        assert items[1]["processed"] is True
        assert items[0]["name"] == "Alice"

    def test_each_index_on_dicts(self):
        code = """\
MOV @items, @data
EACH @item, @items, +1
  MOV @last_idx, @item._index
"""
        ctx = _make_ctx(data=[{"v": "a"}, {"v": "b"}, {"v": "c"}])
        result = execute(code, ctx)
        assert result.error is None
        assert result.state.get("last_idx") == 2

    def test_each_nested(self):
        """EACH inside EACH with dict items."""
        code = """\
MOV @outer, @rows
MOV @count, 0
EACH @row, @outer, +3
  MOV @cols, @row.items
  EACH @col, @cols, +1
    CALL @count, add, @count, 1
"""
        ctx = _make_ctx(rows=[
            {"items": [{"x": 1}, {"x": 2}]},
            {"items": [{"x": 3}, {"x": 4}, {"x": 5}]},
        ])
        result = execute(code, ctx)
        assert result.error is None
        assert result.state.get("count") == 5


# ---------------------------------------------------------------------------
# parse_program: EACH is recognised
# ---------------------------------------------------------------------------

class TestEachParsing:
    def test_each_parsed(self):
        code = "EACH @item, @list, +2\n  MOV @item.x, 1\n  MOV @item.y, 2"
        instructions, _ = parse_program(code)
        assert instructions[0].opcode == "EACH"
        assert instructions[0].args == ["@item", "@list", "+2"]


# ---------------------------------------------------------------------------
# GEN capture/coerce (mocked LLM)
# ---------------------------------------------------------------------------

class TestGenCaptureCoerce:
    def test_gen_probe_capture_int(self):
        from kobold_sandbox.assembly_dsl import _exec_gen, Instruction

        inst = Instruction(
            opcode="GEN",
            args=["@result", '"test prompt"'],
            flags={"mode": "probe", "capture": '"[0-9]+"', "coerce": "int"},
        )
        ctx = _make_ctx()

        with patch("kobold_sandbox.assembly_dsl._atomic_apply_function", return_value="  42\n"):
            _exec_gen(ctx, inst)

        assert ctx.get("$result") == 42

    def test_gen_probe_capture_no_coerce(self):
        from kobold_sandbox.assembly_dsl import _exec_gen, Instruction

        inst = Instruction(
            opcode="GEN",
            args=["@val", '"prompt"'],
            flags={"mode": "probe", "capture": '"[a-z]+"'},
        )
        ctx = _make_ctx()
        with patch("kobold_sandbox.assembly_dsl._atomic_apply_function", return_value="  hello world "):
            _exec_gen(ctx, inst)

        assert ctx.get("$val") == "hello"

    def test_gen_normal_mode_no_capture(self):
        """Non-probe mode should not apply capture/coerce."""
        from kobold_sandbox.assembly_dsl import _exec_gen, Instruction

        inst = Instruction(
            opcode="GEN",
            args=["@val", '"prompt"'],
            flags={"mode": "prompt", "capture": '"[0-9]+"', "coerce": "int"},
        )
        ctx = _make_ctx()
        with patch("kobold_sandbox.assembly_dsl._atomic_apply_function", return_value="result 42"):
            _exec_gen(ctx, inst)

        assert ctx.get("$val") == "result 42"


# ---------------------------------------------------------------------------
# dsl_builtins registration
# ---------------------------------------------------------------------------

class TestDslBuiltins:
    def test_numbered_builtin(self):
        code = 'MOV @text, "hello world"\nCALL @result, numbered, @text'
        ctx = _make_ctx()
        result = execute(code, ctx)
        assert result.error is None
        assert result.state.get("result") == "1. hello world"

    def test_slice_lines_builtin(self):
        # Use \\n so assembly sees literal \n which _asm_resolve converts to newline
        code = 'MOV @text, "line1\\nline2\\nline3\\nline4"\nCALL @result, slice_lines, @text, 2, 3'
        ctx = _make_ctx()
        result = execute(code, ctx)
        assert result.error is None
        assert result.state.get("result") == "line2\nline3"

    def test_check_status_builtin(self):
        code = """\
CALL @s1, check_status, "PASS: looks good"
CALL @s2, check_status, "FAIL: missing detail"
CALL @s3, check_status, "maybe later"
"""
        ctx = _make_ctx()
        result = execute(code, ctx)
        assert result.error is None
        assert result.state.get("s1") == "pass"
        assert result.state.get("s2") == "fail"
        assert result.state.get("s3") == "pending"

    def test_char_indexed_builtin(self):
        code = 'CALL @result, char_indexed, "Hi"'
        ctx = _make_ctx()
        result = execute(code, ctx)
        assert result.error is None
        val = result.state.get("result")
        assert "[0:H]" in val
        assert "[1:i]" in val

    def test_concat_builtin(self):
        code = """\
MOV @a, @list1
MOV @b, @list2
CALL @result, concat, @a, @b
"""
        ctx = _make_ctx(list1=["x", "y"], list2=["z"])
        result = execute(code, ctx)
        assert result.error is None
        assert result.state.get("result") == ["x", "y", "z"]

    def test_parse_sections_builtin(self):
        code = 'MOV @text, "ENTITIES: [Alice, Bob]\\nAXIOMS:\\n- Alice is tall\\n- Bob is short\\nHYPOTHESES:\\n- Alice likes Bob"\nCALL @parsed, parse_sections, @text'
        ctx = _make_ctx()
        result = execute(code, ctx)
        assert result.error is None
        parsed = result.state.get("parsed")
        assert parsed["entities"] == ["Alice", "Bob"]
        assert len(parsed["axioms"]) == 2
        assert len(parsed["hypotheses"]) == 1

    def test_create_span_annotation_builtin(self):
        code = """\
MOV @entity, @ent
MOV @constraint, @con
CALL @ann, create_span_annotation, @entity, @constraint, 5, 15
"""
        ctx = _make_ctx(
            ent={"answer": "The amber-eyed demoness stood proud", "_message_ref": "msg_001"},
            con={"name": "eye_color", "tags": ["appearance", "eyes", "color"], "probe_prompt": "eye color"},
        )
        result = execute(code, ctx)
        assert result.error is None
        ann = result.state.get("ann")
        assert ann["source"]["char_start"] == 5
        assert ann["source"]["char_end"] == 15
        assert ann["tags"] == ["appearance", "eyes", "color"]


# ---------------------------------------------------------------------------
# load_library_functions
# ---------------------------------------------------------------------------

class TestLoadLibraryFunctions:
    def test_load_fn_from_pages(self):
        pages = [
            {
                "blocks": [
                    {
                        "text": 'fn double(@x) -> @result:\n  CALL @result, add, @x, @x',
                    }
                ]
            }
        ]
        fns = load_library_functions(pages)
        assert "double" in fns
        assert fns["double"].params == ["@x"]
        assert fns["double"].outputs == ["@result"]

    def test_execute_with_library_fn(self):
        pages = [
            {
                "blocks": [
                    {
                        "text": 'fn double(@x) -> @result:\n  CALL @result, add, @x, @x',
                    }
                ]
            }
        ]
        lib_fns = load_library_functions(pages)

        code = "CALL @val, double, 5"
        ctx = _make_ctx()
        result = execute(code, ctx, extra_functions=lib_fns)
        assert result.error is None
        assert result.state.get("val") == 10

    def test_empty_pages(self):
        assert load_library_functions(None) == {}
        assert load_library_functions([]) == {}

    def test_malformed_fn_skipped(self):
        pages = [
            {"blocks": [{"text": "this is not a function"}]},
            {"blocks": [{"text": 'fn valid(@x) -> @y:\n  MOV @y, @x'}]},
        ]
        fns = load_library_functions(pages)
        assert "valid" in fns
        assert len(fns) == 1
