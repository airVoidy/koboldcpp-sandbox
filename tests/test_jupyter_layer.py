"""
Tests for jupyter_layer — happy-path, no live kernel required.

Kernel is mocked so tests run in any CI environment without Jupyter installed.
Live kernel tests are marked @pytest.mark.live and skipped by default.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── helpers ──────────────────────────────────────────────────────────────────

def make_mock_kernel(ns: dict) -> MagicMock:
    """Return a mock KernelSession that serves variables from ns dict.

    ns is passed as globals so that globals() inside eval'd expressions
    mirrors the kernel namespace — matching real jupyter_client behaviour.
    """
    ks = MagicMock()

    def _run(code: str) -> dict:
        try:
            eval(compile(code, "<string>", "exec"), dict(ns))
            return {"status": "ok", "output": "", "error": ""}
        except Exception as e:
            return {"status": "error", "output": "", "error": str(e)}

    def _eval_json(expr: str) -> object:
        # Pass ns as globals so globals() inside the expression sees ns
        result = eval(expr, dict(ns))
        return json.loads(json.dumps(result))

    ks.run.side_effect = _run
    ks.eval_json.side_effect = _eval_json
    return ks


# ── JupyterScope ─────────────────────────────────────────────────────────────

class TestJupyterScope:
    def setup_method(self):
        from jupyter_layer.scope import JupyterScope

        # Simulate kernel namespace: df=..., df_clean=..., _private=..., In=...
        self.ns = {
            "df": [1, 2, 3],
            "df_clean": [2, 3],
            "result": {"score": 0.9},
            "_private": "skip",
            "In": ["skip"],
        }
        self.ks = make_mock_kernel(self.ns)
        self.scope = JupyterScope(self.ks)

    def test_list_ids_returns_public_names(self):
        ids = self.scope.list_ids()
        assert "df" in ids
        assert "df_clean" in ids
        assert "result" in ids
        # private names filtered
        assert "_private" not in ids
        assert "In" not in ids

    def test_list_ids_no_values_fetched(self):
        self.scope.list_ids()
        # eval_json called once for list_ids, never for individual values
        assert self.ks.eval_json.call_count == 1

    def test_fetch_returns_value(self):
        val = self.scope.fetch("result")
        assert val == {"score": 0.9}

    def test_fetch_list(self):
        val = self.scope.fetch("df")
        assert val == [1, 2, 3]

    def test_fetch_invalid_identifier(self):
        with pytest.raises(ValueError, match="identifier"):
            self.scope.fetch("not-valid!")

    def test_fetch_repr(self):
        self.ks.run.side_effect = lambda code: {
            "status": "ok",
            "output": "[1, 2, 3]\n",
            "error": "",
        }
        val = self.scope.fetch_repr("df")
        assert val == "[1, 2, 3]"


# ── Panel + JupyterObject ─────────────────────────────────────────────────────

class TestPanel:
    def setup_method(self):
        from jupyter_layer.panel import Panel, JupyterObject
        self.Panel = Panel
        self.JupyterObject = JupyterObject

    def test_standalone_add_and_list(self):
        panel = self.Panel("test")
        panel.add_value("x", 42)
        panel.add_value("y", [1, 2])
        assert panel.list_ids() == ["x", "y"]

    def test_get_returns_object(self):
        panel = self.Panel("test")
        panel.add_value("x", 42)
        obj = panel.get("x")
        assert obj.id == "x"
        assert obj.value == 42

    def test_get_missing_raises(self):
        panel = self.Panel("test")
        with pytest.raises(KeyError):
            panel.get("missing")

    def test_remove(self):
        panel = self.Panel("test")
        panel.add_value("x", 1)
        panel.remove("x")
        assert "x" not in panel

    def test_lazy_object_fetches_once(self):
        calls = []

        def fetcher():
            calls.append(1)
            return 99

        obj = self.JupyterObject(id="lazy", _fetch=fetcher)
        assert obj.value == 99
        _ = obj.value  # second access — no second call
        assert len(calls) == 1

    def test_invalidate_refetches(self):
        calls = []

        def fetcher():
            calls.append(1)
            return len(calls)

        obj = self.JupyterObject(id="refetch", _fetch=fetcher)
        assert obj.value == 1
        obj.invalidate()
        assert obj.value == 2
        assert len(calls) == 2

    def test_sub_panel(self):
        panel = self.Panel("root")
        sub = panel.sub_panel("embeddings")
        assert isinstance(sub, self.Panel)
        assert sub.name == "embeddings"
        # idempotent
        assert panel.sub_panel("embeddings") is sub

    def test_contains(self):
        panel = self.Panel("test")
        panel.add_value("a", 1)
        assert "a" in panel
        assert "b" not in panel

    def test_len(self):
        panel = self.Panel("test")
        panel.add_value("a", 1)
        panel.add_value("b", 2)
        assert len(panel) == 2


class TestPanelScopeSync:
    def setup_method(self):
        from jupyter_layer.panel import Panel
        from jupyter_layer.scope import JupyterScope
        self.Panel = Panel
        self.JupyterScope = JupyterScope

    def test_sync_from_scope_adds_lazy_objects(self):
        ns = {"alpha": 1, "beta": 2, "gamma": 3}
        ks = make_mock_kernel(ns)

        scope = self.JupyterScope(ks)
        panel = self.Panel("data", scope=scope)
        added = panel.sync_from_scope()

        assert set(added) == {"alpha", "beta", "gamma"}
        assert set(panel.list_ids()) == {"alpha", "beta", "gamma"}

    def test_sync_removes_stale_ids(self):
        ns_v1 = {"alpha": 1, "beta": 2}
        ns_v2 = {"alpha": 1}  # beta removed

        ks = make_mock_kernel(ns_v1)
        call_count = [0]

        def eval_json(expr):
            call_count[0] += 1
            ns = ns_v2 if call_count[0] > 1 else ns_v1
            return eval(expr, dict(ns))

        ks.eval_json.side_effect = eval_json

        from jupyter_layer.scope import JupyterScope
        scope = JupyterScope(ks)
        panel = self.Panel("data", scope=scope)
        panel.sync_from_scope()  # v1: alpha, beta
        panel.sync_from_scope()  # v2: alpha only
        assert panel.list_ids() == ["alpha"]

    def test_sync_without_scope_raises(self):
        panel = self.Panel("no_scope")
        with pytest.raises(RuntimeError, match="no scope"):
            panel.sync_from_scope()

    def test_lazy_object_fetches_from_kernel(self):
        ns = {"val": 777}
        ks = make_mock_kernel(ns)

        from jupyter_layer.scope import JupyterScope
        scope = JupyterScope(ks)
        panel = self.Panel("data", scope=scope)
        panel.sync_from_scope()

        obj = panel.get("val")
        # Value not yet fetched
        assert obj._fetched is False
        # Access triggers fetch
        result = obj.value
        assert result == 777
        assert obj._fetched is True


# ── LocalStore ────────────────────────────────────────────────────────────────

class TestLocalStore:
    def test_save_and_load_panel_meta(self, tmp_path):
        from jupyter_layer.store import LocalStore
        from jupyter_layer.panel import Panel

        panel = Panel("mydata", meta={"version": 1})
        panel.add_value("x", 1)
        panel.add_value("y", 2)

        store = LocalStore(tmp_path, "mydata")
        store.save_panel_meta(panel)

        loaded = store.load_panel_meta()
        assert loaded["name"] == "mydata"
        assert loaded["meta"] == {"version": 1}
        assert set(loaded["child_ids"]) == {"x", "y"}

    def test_save_and_load_object_meta(self, tmp_path):
        from jupyter_layer.store import LocalStore
        from jupyter_layer.panel import JupyterObject

        store = LocalStore(tmp_path, "mydata")
        obj = JupyterObject(id="embedding_v1", meta={"shape": [768]})
        store.save_object_meta(obj)

        loaded = store.load_object_meta("embedding_v1")
        assert loaded["id"] == "embedding_v1"
        assert loaded["meta"] == {"shape": [768]}

    def test_list_stored_ids(self, tmp_path):
        from jupyter_layer.store import LocalStore
        from jupyter_layer.panel import JupyterObject

        store = LocalStore(tmp_path, "mydata")
        for name in ["a", "b", "c"]:
            store.save_object_meta(JupyterObject(id=name, meta={}))

        ids = store.list_stored_ids()
        assert set(ids) == {"a", "b", "c"}

    def test_blob_roundtrip(self, tmp_path):
        from jupyter_layer.store import LocalStore

        store = LocalStore(tmp_path, "mydata")
        data = {"rows": 42, "cols": ["text", "label"]}
        store.save_blob("dataset_info", data)

        loaded = store.load_blob("dataset_info")
        assert loaded == data

    def test_load_missing_returns_none(self, tmp_path):
        from jupyter_layer.store import LocalStore

        store = LocalStore(tmp_path, "mydata")
        assert store.load_panel_meta() is None
        assert store.load_object_meta("ghost") is None
        assert store.load_blob("nowhere") is None

    def test_list_blobs(self, tmp_path):
        from jupyter_layer.store import LocalStore

        store = LocalStore(tmp_path, "mydata")
        store.save_blob("info", {"a": 1})
        store.save_blob("stats", {"b": 2})

        blobs = store.list_blobs()
        assert set(blobs) == {"info", "stats"}


# ── live kernel marker (skipped by default) ───────────────────────────────────

@pytest.mark.live
def test_live_kernel_roundtrip():
    """Requires: pip install jupyter_client ipykernel"""
    from jupyter_layer import KernelSession, JupyterScope, Panel

    with KernelSession() as ks:
        scope = JupyterScope(ks)
        scope.run("x = [1, 2, 3]")
        scope.run("y = {'hello': 'world'}")

        ids = scope.list_ids()
        assert "x" in ids
        assert "y" in ids

        panel = Panel("live_test", scope=scope)
        panel.sync_from_scope()

        assert panel.get("x").value == [1, 2, 3]
        assert panel.get("y").value == {"hello": "world"}
