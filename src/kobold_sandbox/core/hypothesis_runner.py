from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import Any

from .checklist import HypothesisEntry, HypothesisResult


def load_entrypoint(entrypoint: str) -> Callable[[HypothesisEntry, Mapping[str, Any]], HypothesisResult]:
    module_name, separator, attr_name = entrypoint.partition(":")
    if not separator or not module_name or not attr_name:
        raise ValueError(f"Invalid entrypoint: {entrypoint}")
    module = importlib.import_module(module_name)
    target = getattr(module, attr_name, None)
    if target is None or not callable(target):
        raise ValueError(f"Entrypoint is not callable: {entrypoint}")
    return target


def run_hypothesis_entry(entry: HypothesisEntry, context: Mapping[str, Any]) -> HypothesisResult:
    runner = load_entrypoint(entry.entrypoint)
    result = runner(entry, context)
    if not isinstance(result, HypothesisResult):
        raise TypeError(f"Entrypoint {entry.entrypoint} returned {type(result).__name__}, expected HypothesisResult")
    return result
