from __future__ import annotations

import json
import re
from pathlib import Path

from .source_refs import (
    SourceRef,
    build_fragment_lookup,
    build_sentence_lookup,
    infer_source_kind,
    load_fragment_records,
    load_sentence_records,
    normalize_text,
)


WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in WORD_RE.findall(normalize_text(text))}


def _best_sentence_match(payload_text: str, ordered_sentences: list[dict]) -> dict | None:
    payload_tokens = _tokenize(payload_text)
    if not payload_tokens:
        return None

    best_sentence = None
    best_score = 0.0
    for candidate in ordered_sentences:
        candidate_tokens = _tokenize(candidate["text"])
        if not candidate_tokens:
            continue
        score = len(payload_tokens & candidate_tokens) / len(payload_tokens)
        if score > best_score:
            best_score = score
            best_sentence = candidate

    if best_score >= 0.6:
        return best_sentence
    return None


def _build_source_ref(
    *,
    file_name: str,
    surface_text: str,
    token_refs: list[str] | None,
    fragment_lookup: dict[str, dict],
    sentence_lookup: dict[str, dict],
    interpretation_level: str,
    source_kind: str | None = None,
) -> dict:
    fragment = fragment_lookup.get(normalize_text(surface_text))
    sentence_id = None
    fragment_id = None
    sentence_kind = None
    if fragment is not None:
        fragment_id = fragment["id"]
        sentence_id = fragment["sentence_id"]
        sentence = sentence_lookup.get(sentence_id)
        sentence_kind = sentence["kind"] if sentence else None

    ref = SourceRef(
        file=file_name,
        version="v0",
        sentence_id=sentence_id,
        fragment_id=fragment_id,
        token_refs=token_refs or [],
        char_span=None,
        surface_text=surface_text,
        source_kind=source_kind or infer_source_kind(file_name, sentence_kind),
        interpretation_level=interpretation_level,
    )
    return ref.to_dict()


def _normalize_object_like(
    payload: dict,
    *,
    fragment_lookup: dict[str, dict],
    sentence_lookup: dict[str, dict],
) -> bool:
    old_source = payload.pop("source", None)
    current_ref = payload.get("source_ref")
    source_data = old_source or current_ref
    if source_data is None:
        return False

    surface_text = source_data.get("fragment") or source_data.get("surface_text") or payload.get("surface", "")
    payload["source_ref"] = _build_source_ref(
        file_name=source_data.get("file", "question.txt"),
        surface_text=surface_text,
        token_refs=source_data.get("token_refs"),
        fragment_lookup=fragment_lookup,
        sentence_lookup=sentence_lookup,
        interpretation_level=source_data.get("interpretation_level", "direct"),
        source_kind=source_data.get("source_kind"),
    )
    return True


def _normalize_raw_claim(
    payload: dict,
    *,
    fragment_lookup: dict[str, dict],
    sentence_lookup: dict[str, dict],
    ordered_sentences: list[dict],
) -> None:
    source_label = payload.pop("source", None)
    existing_ref = payload.get("source_ref", {})
    if source_label is None:
        source_label = "question" if existing_ref.get("source_kind") == "question" else "historical"

    fragment = fragment_lookup.get(normalize_text(payload["text"].rstrip(".")))
    sentence_id = None
    fragment_id = None
    sentence_kind = None
    if fragment is not None:
        fragment_id = fragment["id"]
        sentence_id = fragment["sentence_id"]
        sentence = sentence_lookup.get(sentence_id)
        sentence_kind = sentence["kind"] if sentence else None

    if sentence_id is None:
        for candidate in ordered_sentences:
            candidate_text = normalize_text(candidate["text"].rstrip("."))
            payload_text = normalize_text(payload["text"].rstrip("."))
            if candidate_text == payload_text or payload_text in candidate_text or candidate_text in payload_text:
                sentence_id = candidate["id"]
                sentence_kind = candidate["kind"]
                break

    if sentence_id is None and source_label == "condition":
        for candidate in ordered_sentences:
            if candidate["kind"] == "structural":
                sentence_id = candidate["id"]
                sentence_kind = candidate["kind"]
                break

    if sentence_id is None and source_label.startswith("condition."):
        condition_index = int(source_label.split(".", 1)[1]) - 1
        numbered_conditions = [
            sentence
            for sentence in ordered_sentences
            if sentence["kind"] in {"ordering", "adjacency", "choice", "observation", "negative_constraint"}
        ]
        if 0 <= condition_index < len(numbered_conditions):
            sentence_id = numbered_conditions[condition_index]["id"]
            sentence_kind = numbered_conditions[condition_index]["kind"]

    if sentence_id is None:
        for candidate in ordered_sentences:
            if normalize_text(candidate["text"].rstrip(".")) == normalize_text(payload["text"].rstrip(".")):
                sentence_id = candidate["id"]
                sentence_kind = candidate["kind"]
                break

    if sentence_id is None:
        best_sentence = _best_sentence_match(payload["text"], ordered_sentences)
        if best_sentence is not None:
            sentence_id = best_sentence["id"]
            sentence_kind = best_sentence["kind"]

    if sentence_id is not None and fragment_id is None:
        for candidate in fragment_lookup.values():
            if candidate["sentence_id"] != sentence_id:
                continue
            candidate_text = normalize_text(candidate["text"].rstrip("."))
            payload_text = normalize_text(payload["text"].rstrip("."))
            if candidate_text == payload_text:
                fragment_id = candidate["id"]
                break

    if sentence_id is not None and fragment_id is None:
        sentence_fragments = [candidate for candidate in fragment_lookup.values() if candidate["sentence_id"] == sentence_id]
        best_fragment = _best_sentence_match(payload["text"], sentence_fragments)
        if best_fragment is not None:
            fragment_id = best_fragment["id"]

    if sentence_id is None:
        for candidate in sentence_lookup.values():
            if normalize_text(candidate["text"].rstrip(".")) == normalize_text(payload["text"].rstrip(".")):
                sentence_id = candidate["id"]
                sentence_kind = candidate["kind"]
                break

    payload["source_ref"] = SourceRef(
        file="source_text.md",
        version="v0",
        sentence_id=sentence_id,
        fragment_id=fragment_id,
        token_refs=[],
        char_span=None,
        surface_text=payload["text"],
        source_kind="question" if source_label == "question" else infer_source_kind("source_text.md", sentence_kind),
        interpretation_level="direct",
    ).to_dict()


def _atom_interpretation_level(atom_kind: str) -> str:
    if atom_kind == "derived_observation":
        return "strong"
    return "light"


def _normalize_atom(
    payload: dict,
    raw_claim_lookup: dict[str, dict],
) -> None:
    raw_claim = raw_claim_lookup.get(payload["raw_claim_id"])
    if raw_claim is None:
        return

    raw_ref = raw_claim["source_ref"]
    payload["source_ref"] = SourceRef(
        file=raw_ref["file"],
        version=raw_ref["version"],
        sentence_id=raw_ref["sentence_id"],
        fragment_id=raw_ref["fragment_id"],
        token_refs=list(raw_ref.get("token_refs", [])),
        char_span=raw_ref.get("char_span"),
        surface_text=raw_ref["surface_text"],
        source_kind="derived",
        interpretation_level=_atom_interpretation_level(payload["kind"]),
    ).to_dict()


def _rewrite_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_case_artifacts(case_dir: Path) -> None:
    sentences = load_sentence_records(case_dir / "sentences_v0.json")
    sentence_lookup = build_sentence_lookup(sentences)
    fragment_lookup = build_fragment_lookup(load_fragment_records(case_dir / "fragments_v0.json"))

    for directory in ("objects", "relations", "claims"):
        for path in sorted((case_dir / directory).glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            changed = _normalize_object_like(
                payload,
                fragment_lookup=fragment_lookup,
                sentence_lookup=sentence_lookup,
            )
            if changed:
                _rewrite_json(path, payload)

    raw_claims_path = case_dir / "raw_claims.json"
    raw_claims = json.loads(raw_claims_path.read_text(encoding="utf-8"))
    for payload in raw_claims:
        _normalize_raw_claim(
            payload,
            fragment_lookup=fragment_lookup,
            sentence_lookup=sentence_lookup,
            ordered_sentences=sentences,
        )
    _rewrite_json(raw_claims_path, raw_claims)

    raw_claim_lookup = {payload["id"]: payload for payload in raw_claims}
    atoms_path = case_dir / "atoms_v0.json"
    atoms = json.loads(atoms_path.read_text(encoding="utf-8"))
    for payload in atoms:
        _normalize_atom(payload, raw_claim_lookup)
    _rewrite_json(atoms_path, atoms)
