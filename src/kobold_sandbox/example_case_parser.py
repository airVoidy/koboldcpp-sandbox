from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


ENUM_RE = re.compile(r"^\s*(\d+)\.\s+(.*)$")


@dataclass
class SentenceRecord:
    id: str
    kind: str
    text: str


@dataclass
class FragmentRecord:
    id: str
    sentence_id: str
    text: str
    bucket: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    out: list[str] = []
    buffer: list[str] = []

    for line in lines:
        m = ENUM_RE.match(line)
        if m:
            if buffer:
                out.append(_normalize(" ".join(buffer)))
                buffer = []
            out.append(_normalize(m.group(2)))
            continue
        buffer.append(line)
        if line.endswith((".", "?", "!")):
            out.append(_normalize(" ".join(buffer)))
            buffer = []

    if buffer:
        out.append(_normalize(" ".join(buffer)))
    return out


def classify_sentence(sentence: str) -> str:
    low = sentence.lower()
    if low.startswith("определи"):
        return "question"
    if "ровно один раз" in low or "поодиночке" in low:
        return "structural"
    if "либо" in low and "либо" in low:
        return "choice"
    if "сразу после" in low or "сразу перед" in low:
        return "adjacency"
    if "обнаружил" in low or "обнаружили" in low or "уже был" in low:
        return "observation"
    if " не " in f" {low} ":
        return "negative_constraint"
    if any(word in low for word in ["после", "до ", "раньше", "позже"]):
        return "ordering"
    return "setup"


def split_fragments(sentence: str) -> list[str]:
    low = sentence.lower()
    if " но " in low:
        return [_normalize(part) for part in re.split(r"\s+но\s+", sentence) if _normalize(part)]
    if " либо " in low:
        return [sentence]
    return [sentence]


def classify_fragment(fragment: str) -> str:
    low = fragment.lower()
    if any(word in low for word in ["лера", "максим", "софья", "илья", "диана", "елисей", "анна"]) and "," in fragment:
        return "entities"
    if "ровно один раз" in low or "поодиночке" in low:
        return "structural_once_individual"
    if "сразу после" in low or "сразу перед" in low:
        return "adjacency_immediate"
    if "либо" in low:
        return "choice_either_or"
    if "перв" in low or "последн" in low or "пятый" in low:
        return "ordinal_position"
    if "обнаруж" in low or "уже был открыт" in low:
        return "observation_state"
    if "кто оставил записку" in low or "один из участников" in low or "посетитель" in low:
        return "role_mentions"
    if " не " in f" {low} ":
        return "negation_not"
    if any(word in low for word in ["после", "до ", "раньше", "позже"]):
        return "ordering_after_before"
    if "семеро друзей" in low:
        return "entities"
    return "unresolved"


def build_sentence_records(sentences: list[str]) -> list[SentenceRecord]:
    return [
        SentenceRecord(
            id=f"s-{i+1:04d}",
            kind=classify_sentence(sentence),
            text=sentence,
        )
        for i, sentence in enumerate(sentences)
    ]


def build_fragment_records(sentences: list[SentenceRecord]) -> list[FragmentRecord]:
    out: list[FragmentRecord] = []
    idx = 1
    for sentence in sentences:
        for fragment in split_fragments(sentence.text):
            out.append(
                FragmentRecord(
                    id=f"f-{idx:04d}",
                    sentence_id=sentence.id,
                    text=fragment,
                    bucket=classify_fragment(fragment),
                )
            )
            idx += 1
    return out


def parse_case_text(source_path: Path) -> tuple[list[SentenceRecord], list[FragmentRecord]]:
    text = source_path.read_text(encoding="utf-8")
    sentences = build_sentence_records(split_sentences(text))
    fragments = build_fragment_records(sentences)
    return sentences, fragments


def write_case_outputs(case_dir: Path) -> None:
    source_path = case_dir / "question.txt"
    sentences, fragments = parse_case_text(source_path)

    sentences_obj = {
        "source_file": source_path.name,
        "version": "auto-v0",
        "sentences": [sentence.__dict__ for sentence in sentences],
    }
    fragments_obj = {
        "version": "auto-v0",
        "fragments": [fragment.__dict__ for fragment in fragments],
    }

    (case_dir / "sentences_auto.json").write_text(
        json.dumps(sentences_obj, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (case_dir / "fragments_auto.json").write_text(
        json.dumps(fragments_obj, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_case_outputs(Path("examples/quest_order_case"))
