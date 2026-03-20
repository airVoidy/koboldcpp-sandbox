from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WorkerRef:
    worker_type: str
    worker_id: str


@dataclass(frozen=True)
class ArgumentRef:
    arg_type: str
    arg_id: str


@dataclass
class WorkerCell:
    ref: WorkerRef
    domain: set[str]
    facts: dict[str, Any] = field(default_factory=dict)
    links: set[WorkerRef] = field(default_factory=set)
    neighbor_refs: dict[str, WorkerRef] = field(default_factory=dict)
    operations: list[str] = field(default_factory=list)
    attached_rule_ids: list[str] = field(default_factory=list)


@dataclass
class ArgumentEnvelope:
    ref: ArgumentRef
    subtype: str
    values: set[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleBinding:
    binding_id: str
    rule_id: str
    worker_ref: WorkerRef
    argument_ref: ArgumentRef


def attach_operation_to_worker(worker: WorkerCell, operation_id: str) -> None:
    if operation_id not in worker.operations:
        worker.operations.append(operation_id)


def connect_worker_neighbors(
    workers: dict[WorkerRef, WorkerCell],
    refs: tuple[WorkerRef, ...],
    *,
    left_key: str = "left",
    right_key: str = "right",
) -> None:
    for index, ref in enumerate(refs):
        worker = workers[ref]
        if index > 0:
            worker.neighbor_refs[left_key] = refs[index - 1]
            worker.links.add(refs[index - 1])
        if index + 1 < len(refs):
            worker.neighbor_refs[right_key] = refs[index + 1]
            worker.links.add(refs[index + 1])


def attach_argument_to_worker(
    worker: WorkerCell,
    argument: ArgumentEnvelope,
    *,
    rule_id: str,
) -> RuleBinding:
    if rule_id not in worker.attached_rule_ids:
        worker.attached_rule_ids.append(rule_id)
    attach_operation_to_worker(worker, rule_id)
    worker.facts.setdefault("argument_refs", []).append(argument.ref)
    return RuleBinding(
        binding_id=f"{rule_id}::{worker.ref.worker_id}::{argument.ref.arg_id}",
        rule_id=rule_id,
        worker_ref=worker.ref,
        argument_ref=argument.ref,
    )
