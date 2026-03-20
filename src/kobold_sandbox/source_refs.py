from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class SourceRef:
    file: str
    version: str
    sentence_id: str | None
    fragment_id: str | None
    token_refs: list[str]
    char_span: list[int] | None
    surface_text: str
    source_kind: str
    interpretation_level: str

    def to_dict(self) -> dict:
        return asdict(self)


def infer_source_kind(file_name: str, sentence_kind: str | None = None) -> str:
    if sentence_kind == "question":
        return "question"
    if sentence_kind == "setup":
        return "historical"
    if sentence_kind in {"structural", "ordering", "adjacency", "choice", "observation", "negative_constraint"}:
        return "condition"
    if file_name == "question.txt":
        return "question"
    return "historical"


def load_sentence_records(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["sentences"]


def load_fragment_records(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["fragments"]


def build_sentence_lookup(sentences: list[dict]) -> dict[str, dict]:
    return {sentence["id"]: sentence for sentence in sentences}


def build_fragment_lookup(fragments: list[dict]) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for fragment in fragments:
        lookup[normalize_text(fragment["text"])] = fragment
    return lookup
