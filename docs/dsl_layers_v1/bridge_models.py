from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

try:
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    BaseModel = None
    Field = None


BridgeKind = Literal[
    "use_macro",
    "atomic",
    "trigger_workflow",
    "run_macro",
    "run_atomic",
]


@dataclass
class ExportBinding:
    target: str
    source: str


@dataclass
class BaseBridge:
    type: BridgeKind
    bind: dict[str, str] = field(default_factory=dict)
    export: list[ExportBinding] = field(default_factory=list)


@dataclass
class UseMacroBridge(BaseBridge):
    type: Literal["use_macro"] = "use_macro"
    name: str = ""


@dataclass
class AtomicBlockBridge(BaseBridge):
    type: Literal["atomic"] = "atomic"
    dsl: str = ""


@dataclass
class TriggerWorkflowBridge(BaseBridge):
    type: Literal["trigger_workflow"] = "trigger_workflow"
    name: str = ""


@dataclass
class RunMacroBridge(BaseBridge):
    type: Literal["run_macro"] = "run_macro"
    name: str = ""


@dataclass
class RunAtomicBridge(BaseBridge):
    type: Literal["run_atomic"] = "run_atomic"
    dsl: str = ""


BridgeDataclass = Union[
    UseMacroBridge,
    AtomicBlockBridge,
    TriggerWorkflowBridge,
    RunMacroBridge,
    RunAtomicBridge,
]


if BaseModel is not None:
    class ExportBindingModel(BaseModel):
        target: str
        source: str


    class BaseBridgeModel(BaseModel):
        type: BridgeKind
        bind: dict[str, str] = Field(default_factory=dict)
        export: list[ExportBindingModel] = Field(default_factory=list)


    class UseMacroBridgeModel(BaseBridgeModel):
        type: Literal["use_macro"] = "use_macro"
        name: str


    class AtomicBlockBridgeModel(BaseBridgeModel):
        type: Literal["atomic"] = "atomic"
        dsl: str


    class TriggerWorkflowBridgeModel(BaseBridgeModel):
        type: Literal["trigger_workflow"] = "trigger_workflow"
        name: str


    class RunMacroBridgeModel(BaseBridgeModel):
        type: Literal["run_macro"] = "run_macro"
        name: str


    class RunAtomicBridgeModel(BaseBridgeModel):
        type: Literal["run_atomic"] = "run_atomic"
        dsl: str


    BridgeModel = Union[
        UseMacroBridgeModel,
        AtomicBlockBridgeModel,
        TriggerWorkflowBridgeModel,
        RunMacroBridgeModel,
        RunAtomicBridgeModel,
    ]


    def bridge_json_schema() -> dict:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "DslBridge",
            "oneOf": [
                UseMacroBridgeModel.model_json_schema(),
                AtomicBlockBridgeModel.model_json_schema(),
                TriggerWorkflowBridgeModel.model_json_schema(),
                RunMacroBridgeModel.model_json_schema(),
                RunAtomicBridgeModel.model_json_schema(),
            ],
        }


if __name__ == "__main__":
    if BaseModel is None:
        print("pydantic is not installed")
    else:
        import json
        print(json.dumps(bridge_json_schema(), ensure_ascii=False, indent=2))
