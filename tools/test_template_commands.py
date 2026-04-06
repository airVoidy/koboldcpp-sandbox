"""Basic tests for template command system.

Run: python tools/test_template_commands.py
"""
import sys
import json
import shutil
from pathlib import Path

# Setup
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kobold_sandbox.server import create_app
import tempfile

PASS = 0
FAIL = 0


def test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [ok] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} -- {detail}")


def main():
    global PASS, FAIL

    # Use temp dir but copy templates from real root
    tmpdir = Path(tempfile.mkdtemp(prefix="pchat_test_"))
    real_root = Path(__file__).resolve().parent.parent / "root"
    real_tpl = real_root / "templates"
    tmp_tpl = tmpdir / "root" / "templates"
    if real_tpl.is_dir():
        shutil.copytree(str(real_tpl), str(tmp_tpl))
    try:
        app = create_app(str(tmpdir))
        # Find workspace — it's created inside create_app closure
        # We need to call endpoints through the app, but simpler to test via HTTP
        # Instead, test the template loading directly

        print("=== Template Structure ===")
        tpl_dir = tmpdir / "root" / "templates"
        test("card/commands/pick.py exists", (tpl_dir / "card" / "commands" / "pick.py").is_file())
        test("card/commands/put.py exists", (tpl_dir / "card" / "commands" / "put.py").is_file())
        test("card/commands/cd.py exists", (tpl_dir / "card" / "commands" / "cd.py").is_file())
        test("card/commands/cat.py exists", (tpl_dir / "card" / "commands" / "cat.py").is_file())
        test("card/commands/rm.py exists", (tpl_dir / "card" / "commands" / "rm.py").is_file())
        test("cards/commands/list.py exists", (tpl_dir / "cards" / "commands" / "list.py").is_file())
        test("cards/commands/mk.py exists", (tpl_dir / "cards" / "commands" / "mk.py").is_file())
        test("cards/commands/post.py exists", (tpl_dir / "cards" / "commands" / "post.py").is_file())

        print("\n=== Schema Inheritance ===")
        for name in ("card", "cards", "channel", "message", "channels"):
            schema_path = tpl_dir / name / "schema.json"
            if schema_path.is_file():
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
                inherits = schema.get("inherits", "(none)")
                test(f"{name} schema ok (inherits: {inherits})", True)
            else:
                test(f"{name} schema exists", False, "missing")

        print("\n=== Precompiled .pyc ===")
        pyc_count = len(list(tpl_dir.rglob("*.pyc")))
        test(f".pyc files generated ({pyc_count})", pyc_count >= 8)

        print("\n=== Command Loading ===")
        # Test that modules can be loaded and have execute()
        import importlib.util
        for py_file in sorted(tpl_dir.rglob("*.py")):
            rel = py_file.relative_to(tpl_dir)
            spec = importlib.util.spec_from_file_location(f"test_{py_file.stem}", str(py_file))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(mod)
                    has_execute = hasattr(mod, "execute") and callable(mod.execute)
                    test(f"{rel} has execute()", has_execute)
                except Exception as e:
                    test(f"{rel} loads", False, str(e))

        print("\n=== HTTP Endpoint Test ===")
        # Test via actual HTTP using TestClient
        try:
            from fastapi.testclient import TestClient
            client = TestClient(app)

            # Create a channel
            r = client.post("/api/pchat/exec", json={"cmd": "/mkchannel test_ch", "user": "tester", "scope": "test"})
            test("mkchannel returns ok", r.json().get("ok"), r.text[:100])

            # Select it
            r = client.post("/api/pchat/exec", json={"cmd": "/select test_ch", "user": "tester", "scope": "CMD"})
            test("select returns ok", r.json().get("ok"), r.text[:100])

            # Post a message (should use template command)
            r = client.post("/api/pchat/exec", json={"cmd": "/post hello from test", "user": "tester", "scope": "channel:test_ch"})
            data = r.json()
            test("post returns ok", data.get("ok"), r.text[:100])
            test("post created message", "msg" in data.get("path", ""), data.get("path", ""))

            # Cat the message
            r = client.post("/api/pchat/exec", json={"cmd": "/cat", "user": "tester", "scope": "channel:test_ch"})
            test("cat returns data", r.json().get("meta") is not None, r.text[:100])

            # List messages
            r = client.post("/api/pchat/exec", json={"cmd": "/list", "user": "tester", "scope": "channel:test_ch"})
            children = r.json().get("children", [])
            test("list shows messages", len(children) >= 1, f"got {len(children)} children")

            # Put a field
            r = client.post("/api/pchat/exec", json={"cmd": "/put description test channel", "user": "tester", "scope": "channel:test_ch"})
            test("put returns ok", r.json().get("ok"), r.text[:100])

            # View state
            r = client.post("/api/pchat/view", json={"channel": "test_ch", "user": "tester", "msg_limit": 50})
            state = r.json()
            test("view returns channels", len(state.get("channels", [])) >= 1)
            test("view returns messages", len(state.get("messages", [])) >= 1)

        except ImportError:
            print("  [skip] fastapi.testclient not available")

        print(f"\n{'='*40}")
        print(f"Results: {PASS} passed, {FAIL} failed")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return FAIL == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
