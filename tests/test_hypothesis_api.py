from fastapi.testclient import TestClient

from kobold_sandbox.server import create_app


def test_hypothesis_api_evaluates_connected_component_with_auto_graph(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path)))

    response = client.post(
        "/hypotheses/evaluate-connected",
        json={
            "start_hypothesis_id": "house-1-red-yes",
            "hypotheses": [
                {
                    "hypothesis_id": "house-1-red-yes",
                    "title": "house-1 red",
                    "status": "hypothesis",
                    "related_cells": ["einstein-color:house-1:red"],
                    "consequences": ["house-1 fixed red"],
                },
                {
                    "hypothesis_id": "englishman-house-1",
                    "title": "englishman house-1",
                    "status": "hypothesis",
                    "related_cells": ["einstein-color:house-1:red", "einstein-nationality:house-1:englishman"],
                    "consequences": ["englishman-red-link"],
                },
                {
                    "hypothesis_id": "house-3-milk-yes",
                    "title": "house-3 milk",
                    "status": "confirmed",
                    "related_cells": ["einstein-drink:house-3:milk"],
                    "consequences": ["milk fixed"],
                },
            ],
            "atoms": [
                {
                    "hypothesis_id": "house-1-red-yes",
                    "atom_id": "a1",
                    "expression": "assert einstein_color_cell['house-1:red'] == 'yes'",
                    "variables": ["einstein_color_cell"],
                },
                {
                    "hypothesis_id": "englishman-house-1",
                    "atom_id": "a2",
                    "expression": "assert nationality_by_house['house-1'] == 'englishman'",
                    "variables": ["nationality_by_house"],
                },
                {
                    "hypothesis_id": "house-3-milk-yes",
                    "atom_id": "a3",
                    "expression": "assert drink_by_house['house-3'] == 'milk'",
                    "variables": ["drink_by_house"],
                },
            ],
            "context": {
                "einstein_color_cell": {"house-1:red": "yes"},
                "nationality_by_house": {"house-1": "englishman"},
                "drink_by_house": {"house-3": "milk"},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dependency_graph"]["adjacency"]["house-1-red-yes"] == ["englishman-house-1"]
    assert payload["reaction"]["checked_hypothesis_ids"] == ["house-1-red-yes", "englishman-house-1"]
    assert payload["reaction"]["affected_hypothesis_ids"] == ["house-1-red-yes", "englishman-house-1"]
    assert payload["reaction"]["affected_cells"] == [
        "einstein-color:house-1:red",
        "einstein-nationality:house-1:englishman",
    ]
