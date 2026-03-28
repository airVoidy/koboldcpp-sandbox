"""Tests for async GEN with implicit await and endpoint locking."""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from unittest.mock import patch

from kobold_sandbox.assembly_dsl import execute
from kobold_sandbox.workflow_dsl import WorkflowContext, build_default_builtins

# Real _atomic_apply_function for non-generate calls
from kobold_sandbox.workflow_dsl import _atomic_apply_function as _real_apply


def _make_ctx(**vars_) -> WorkflowContext:
    ctx = WorkflowContext(
        workers={
            "generator": "http://gen:5001",
            "analyzer": "http://ana:5002",
        },
        settings={},
        builtins=build_default_builtins(),
        on_thread=lambda *a, **kw: None,
    )
    for k, v in vars_.items():
        ctx.set(f"${k}", v)
    return ctx


def _mock_gen_only(response_fn):
    """Create a mock that intercepts 'generate' calls, passes through everything else."""
    def mock(ctx, fn_name, pos_args, kw_args):
        if fn_name == "generate":
            return response_fn(ctx, fn_name, pos_args, kw_args)
        return _real_apply(ctx, fn_name, pos_args, kw_args)
    return mock


class TestAsyncGenBasic:
    def test_two_async_gen_resolve_on_read(self):
        """Two GEN on different endpoints run async, resolve on first read."""
        code = """\
GEN @answer1, "prompt1", worker:generator
GEN @answer2, "prompt2", worker:analyzer
MOV @ready, true
CALL @len1, len, @answer1
CALL @len2, len, @answer2
"""
        ctx = _make_ctx()

        def gen_response(ctx_, fn, pos, kw):
            time.sleep(0.05)
            return f"response to {pos[0]}" if pos else "empty"

        with patch("kobold_sandbox.assembly_dsl._atomic_apply_function",
                    side_effect=_mock_gen_only(gen_response)):
            result = execute(code, ctx)

        assert result.error is None
        assert result.state.get("ready") is True
        assert result.state.get("answer1") == "response to prompt1"
        assert result.state.get("answer2") == "response to prompt2"
        assert result.state.get("len1") == len("response to prompt1")

    def test_async_gen_idle_work_before_await(self):
        """Instructions between async GEN and first read execute immediately."""
        code = """\
GEN @answer, "slow prompt", worker:generator
MOV @idle_done, true
CALL @result, len, @answer
"""
        ctx = _make_ctx()

        def gen_response(ctx_, fn, pos, kw):
            time.sleep(0.1)
            return "slow response"

        with patch("kobold_sandbox.assembly_dsl._atomic_apply_function",
                    side_effect=_mock_gen_only(gen_response)):
            result = execute(code, ctx)

        assert result.error is None
        assert result.state.get("idle_done") is True
        assert result.state.get("result") == len("slow response")


class TestAsyncProbeStaysSynchronous:
    def test_probe_is_blocking(self):
        """GEN with mode:probe should be synchronous (no Future)."""
        code = 'GEN @n, "test", mode:probe, capture:"[0-9]+", coerce:int, worker:analyzer'
        ctx = _make_ctx()

        def gen_response(ctx_, fn, pos, kw):
            return "42"

        with patch("kobold_sandbox.assembly_dsl._atomic_apply_function",
                    side_effect=_mock_gen_only(gen_response)):
            result = execute(code, ctx)

        assert result.error is None
        assert result.state.get("n") == 42
        assert not isinstance(result.state.get("n"), Future)


class TestEndpointLocking:
    def test_same_endpoint_serialized(self):
        """Two GEN to same endpoint should not overlap."""
        ctx = WorkflowContext(
            workers={"generator": "http://same:5001", "analyzer": "http://same:5001"},
            settings={},
            builtins=build_default_builtins(),
            on_thread=lambda *a, **kw: None,
        )

        overlap_detected = []
        active_lock = threading.Lock()
        active_count = [0]

        def gen_response(ctx_, fn, pos, kw):
            with active_lock:
                active_count[0] += 1
                if active_count[0] > 1:
                    overlap_detected.append(True)
            time.sleep(0.1)
            with active_lock:
                active_count[0] -= 1
            return "response"

        code = """\
GEN @a, "prompt1", worker:generator
GEN @b, "prompt2", worker:analyzer
CALL @x, len, @a
CALL @y, len, @b
"""
        with patch("kobold_sandbox.assembly_dsl._atomic_apply_function",
                    side_effect=_mock_gen_only(gen_response)):
            result = execute(code, ctx)

        assert result.error is None
        assert len(overlap_detected) == 0, "Same endpoint should serialize, no overlap"

    def test_different_endpoints_parallel(self):
        """Two GEN to different endpoints can run in parallel."""
        ctx = _make_ctx()  # gen:5001 + ana:5002 = different

        max_concurrent = [0]
        active_lock = threading.Lock()
        active_count = [0]

        def gen_response(ctx_, fn, pos, kw):
            with active_lock:
                active_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], active_count[0])
            time.sleep(0.1)
            with active_lock:
                active_count[0] -= 1
            return "response"

        code = """\
GEN @a, "prompt1", worker:generator
GEN @b, "prompt2", worker:analyzer
CALL @x, len, @a
CALL @y, len, @b
"""
        with patch("kobold_sandbox.assembly_dsl._atomic_apply_function",
                    side_effect=_mock_gen_only(gen_response)):
            result = execute(code, ctx)

        assert result.error is None
        assert max_concurrent[0] >= 2, "Different endpoints should run in parallel"


class TestAsyncWithEach:
    def test_each_with_gen(self):
        code = """\
MOV @items, @data
EACH @item, @items, :end
  GEN @item.response, @item.prompt, worker:generator
  CALL @item.len, len, @item.response
:end
NOP
"""
        ctx = _make_ctx(data=[{"prompt": "hello"}, {"prompt": "world"}])

        def gen_response(ctx_, fn, pos, kw):
            return f"reply to {pos[0]}" if pos else ""

        with patch("kobold_sandbox.assembly_dsl._atomic_apply_function",
                    side_effect=_mock_gen_only(gen_response)):
            result = execute(code, ctx)

        assert result.error is None
        items = result.state.get("items", [])
        assert items[0]["response"] == "reply to hello"
        assert items[1]["response"] == "reply to world"
        assert items[0]["len"] == len("reply to hello")


class TestAsyncContextLifecycle:
    def test_close_shuts_down_executor(self):
        ctx = _make_ctx()
        assert not ctx._executor._shutdown
        ctx.close()
        assert ctx._executor._shutdown

    def test_child_shares_executor(self):
        ctx = _make_ctx()
        child = ctx.child()
        assert child._executor is ctx._executor
        assert child._endpoint_locks is ctx._endpoint_locks
        ctx.close()
