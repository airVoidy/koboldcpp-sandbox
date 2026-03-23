from fastapi.testclient import TestClient

from kobold_sandbox.assertions import ClaimStatus, TabularAssertionBoard
from kobold_sandbox.constraints import ConstraintSpec, Eq, Item, Const
from kobold_sandbox.reactive import AtomRuntime, ReactiveAtom, evaluate_atom
from kobold_sandbox.server import create_app


def test_reactive_atom_from_claim_can_pass_and_fail() -> None:
    board = TabularAssertionBoard(
        name="einstein-color",
        rows=("house-1",),
        columns=("red",),
    )
    claim = board.seed_claim(
        "house-1",
        "red",
        "yes",
        formal_constraint=ConstraintSpec(Eq(Item("einstein_color_cell", "house-1:red"), Const("yes"))),
        status=ClaimStatus.HYPOTHESIS,
    )
    board.attach_atomic_constraint(
        "house-1",
        "red",
        ConstraintSpec(Eq(Item("einstein_color_cell", "house-1:red"), Const("yes"))),
    )

    atom = ReactiveAtom.from_claim(claim)

    passed = evaluate_atom(atom, {"einstein_color_cell": {"house-1:red": "yes"}})
    failed = evaluate_atom(atom, {"einstein_color_cell": {"house-1:red": "no"}})

    assert passed.passed is True
    assert failed.passed is False
    assert failed.error == "assertion failed"


def test_atom_runtime_can_re_evaluate_registered_atoms() -> None:
    runtime = AtomRuntime()
    atom = runtime.register(
        ReactiveAtom(
            atom_id="a1",
            expression="assert grid['r1c1'] == 7",
            variables=("grid",),
        )
    )

    ok = runtime.evaluate(atom.atom_id, {"grid": {"r1c1": 7}})
    bad = runtime.evaluate(atom.atom_id, {"grid": {"r1c1": 3}})

    assert ok.passed is True
    assert bad.passed is False


def test_atom_api_evaluates_single_and_batch(tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)

    single = client.post(
        "/atoms/evaluate",
        json={
            "atom_id": "single-1",
            "expression": "assert board['x'] == 1",
            "variables": ["board"],
            "context": {"board": {"x": 1}},
        },
    )
    batch = client.post(
        "/atoms/evaluate-batch",
        json={
            "atoms": [
                {"atom_id": "a", "expression": "assert board['x'] == 1", "variables": ["board"]},
                {"atom_id": "b", "expression": "assert board['y'] == 2", "variables": ["board"]},
            ],
            "context": {"board": {"x": 1, "y": 0}},
        },
    )

    assert single.status_code == 200
    assert single.json()["passed"] is True
    assert batch.status_code == 200
    assert batch.json()["results"][0]["passed"] is True
    assert batch.json()["results"][1]["passed"] is False


def test_reactive_reset_clears_task_and_chat_state(tmp_path) -> None:
    app = create_app(str(tmp_path))
    client = TestClient(app)
    session_id = "reset-case"

    create_task = client.post(
        "/api/reactive/task",
        json={
            "session_id": session_id,
            "task_id": "task-reset",
            "entities": {},
            "pipeline": [],
            "extractors": [],
            "constraints": [],
        },
    )
    chat = client.post(
        "/api/reactive/chat/send",
        json={"session_id": session_id, "message": "test message", "settings": {}},
    )
    reset = client.post(f"/api/reactive/reset?session_id={session_id}", json={})
    get_task = client.get(f"/api/reactive/task?session_id={session_id}")
    next_entity = client.post("/api/reactive/chat/next-entity", json={"session_id": session_id})

    assert create_task.status_code == 200
    assert chat.status_code == 200
    assert reset.status_code == 200
    assert reset.json()["reactive_task_cleared"] is True
    assert reset.json()["reactive_chat_cleared"] is True
    assert get_task.status_code == 404
    assert next_entity.status_code == 404
