"""
Overnight pose generator: LLM generates unique poses → parse → embed → ChromaDB.
Generates in RU/EN/ZH, tags rarity, stores with embeddings for later image gen comparison.

Usage:
    python pose_generator.py                  # run with defaults
    python pose_generator.py --count 500      # generate 500 poses
    python pose_generator.py --resume         # continue from existing DB
    python pose_generator.py --stats          # show DB stats and exit
"""

import json
import re
import sys
import time
import random
import requests
import numpy as np
from embed_service import EmbedService

# ── config ──
KOBOLD_URL = "http://localhost:5001"
# KOBOLD_URL = "http://192.168.1.15:5050"  # 27B on remote machine

COLLECTION = "poses"
DEFAULT_COUNT = 1000
DELAY_BETWEEN = 0.0  # no delay needed, LLM is the bottleneck

PROMPT_TEMPLATE = """Generate one unique, non-standard human body pose. Be creative — avoid common poses like "standing straight" or "sitting down". Think of unusual, expressive, or rare poses from dance, martial arts, yoga, theater, everyday life, sleep positions, emotional reactions, etc.

Describe this SINGLE pose in three languages. Each description should be one sentence, natural for that language (not a literal translation).
Also rate how rare/unusual this pose is from 1 (common) to 10 (very rare).

IMPORTANT: Use this EXACT format, one line per field:
RU: [описание позы на русском]
EN: [pose description in English]
ZH: [中文姿势描述]
RARITY: [1-10]
TAGS: [2-4 comma-separated tags like: balance, floor, arms, legs, twist, inversion, asymmetric, dynamic, static, emotional, martial, dance, yoga, theatrical, everyday, sleep]

Example:
RU: стоит на одной ноге, другая прижата к колену, руки сложены перед грудью
EN: standing on one leg with the other foot pressed against the knee, hands in prayer position
ZH: 单脚站立，另一只脚抵住膝盖，双手合十于胸前
RARITY: 4
TAGS: balance, static, yoga

Now generate a DIFFERENT pose (not the example above). Be creative and unusual:"""

PROMPT_STRUCTURED = """Generate one unique, non-standard human body pose. Be creative — avoid common poses.

Describe this pose in a STRUCTURED anatomical format, breaking it down by body parts.
Also provide a natural language description in Russian and English, and rate rarity 1-10.

Bad example: "Человек сидит, закинув ногу на ногу и подпирая голову рукой"
Good example:
STRUCT: [Торс: вертикально; Ноги: скрещены; Руки: контакт с головой; Опора: таз]

Use this EXACT format:
RU: [описание позы на русском, одно предложение]
EN: [pose description in English, one sentence]
ZH: [中文姿势描述]
STRUCT: [Торс: ...; Ноги: ...; Руки: ...; Голова: ...; Опора: ...]
RARITY: [1-10]
TAGS: [2-4 comma-separated tags]

Be creative and unusual:"""

# vary the prompt to get more diversity
STYLE_HINTS = [
    "Think of a pose from contemporary dance.",
    "Think of an unusual sleeping position.",
    "Think of a martial arts stance or combat pose.",
    "Think of a theatrical or dramatic pose.",
    "Think of a pose expressing a strong emotion without words.",
    "Think of an awkward everyday pose (reaching for something, stuck in a tight space).",
    "Think of a yoga or acrobatic pose.",
    "Think of a pose a child would make while playing.",
    "Think of a pose from a painting or sculpture.",
    "Think of a pose that involves interaction with furniture or objects.",
    "Think of a pose that looks strange from one angle but natural from another.",
    "Think of a seated pose that isn't simply 'sitting in a chair'.",
    "Think of a lying down pose that isn't simply 'lying flat'.",
    "Think of a pose involving balance or precarious positioning.",
    "Think of a cultural or ritual pose from any tradition.",
    "Think of a pose that conveys exhaustion or extreme tiredness.",
    "Think of an animal-like human pose.",
    "Think of a pose mid-action, frozen in time.",
    "Think of a pose that involves hands or fingers in an unusual way.",
    "Think of a contorted or twisted body position.",
]


def llm_generate(prompt, max_length=300):
    """Call KoboldCPP API."""
    # no-think: feed empty think block so Qwen skips reasoning
    prompt = prompt + "<think>\n\n</think>\n\n"
    payload = {
        "prompt": prompt,
        "max_length": max_length,
        "temperature": 0.9,
        "top_p": 0.95,
        "top_k": 50,
        "rep_pen": 1.15,
    }
    try:
        resp = requests.post(f"{KOBOLD_URL}/api/v1/generate", json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["results"][0]["text"].strip()
    except Exception as e:
        print(f"  [LLM error] {e}")
        return None


def parse_pose(text):
    """Parse LLM output into structured pose data."""
    result = {}

    # extract fields with regex
    ru_match = re.search(r"RU:\s*(.+?)(?:\n|$)", text)
    en_match = re.search(r"EN:\s*(.+?)(?:\n|$)", text)
    zh_match = re.search(r"ZH:\s*(.+?)(?:\n|$)", text)
    struct_match = re.search(r"STRUCT:\s*(.+?)(?:\n|$)", text)
    rarity_match = re.search(r"RARITY:\s*(\d+)", text)
    tags_match = re.search(r"TAGS:\s*(.+?)(?:\n|$)", text)

    if ru_match:
        result["ru"] = ru_match.group(1).strip()
    if en_match:
        result["en"] = en_match.group(1).strip()
    if zh_match:
        result["zh"] = zh_match.group(1).strip()
    if rarity_match:
        result["rarity"] = min(10, max(1, int(rarity_match.group(1))))
    if struct_match:
        result["struct"] = struct_match.group(1).strip()
    if tags_match:
        result["tags"] = [t.strip().lower() for t in tags_match.group(1).split(",")]

    # validate: need at least RU and EN
    if "ru" not in result or "en" not in result:
        return None

    result.setdefault("zh", "")
    result.setdefault("struct", "")
    result.setdefault("rarity", 5)
    result.setdefault("tags", [])

    return result


def embed_and_store(svc, col, pose, idx):
    """Embed all three languages and store in ChromaDB."""
    texts_to_embed = []
    labels = []

    for lang in ["ru", "en", "zh", "struct"]:
        if pose.get(lang):
            texts_to_embed.append(pose[lang])
            labels.append(lang)

    embeddings = svc.encode_docs(texts_to_embed)

    # also compute cross-language similarities
    sims = {}
    if len(embeddings) >= 2:
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                key = f"{labels[i]}_{labels[j]}"
                a, b = np.array(embeddings[i]), np.array(embeddings[j])
                sims[key] = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    # also compute distance to "поза" category anchor
    pose_anchor = np.array(svc.encode_docs(["поза"])[0])
    pose_score = float(np.dot(np.array(embeddings[0]), pose_anchor) /
                       (np.linalg.norm(embeddings[0]) * np.linalg.norm(pose_anchor)))

    # store each language version
    for k, (lang, emb) in enumerate(zip(labels, embeddings)):
        doc_id = f"pose_{idx}_{lang}"
        metadata = {
            "pose_id": idx,
            "lang": lang,
            "rarity": pose["rarity"],
            "tags": ",".join(pose["tags"]),
            "pose_score": round(pose_score, 4),
        }
        # add cross-language sims
        for sim_key, sim_val in sims.items():
            metadata[f"sim_{sim_key}"] = round(sim_val, 4)

        # add other language texts and struct as metadata
        for other_lang in ["ru", "en", "zh"]:
            if other_lang != lang and pose.get(other_lang):
                metadata[f"text_{other_lang}"] = pose[other_lang][:200]
        if pose.get("struct"):
            metadata["struct"] = pose["struct"][:300]

        col.add(
            ids=[doc_id],
            embeddings=[emb],
            documents=[pose[lang]],
            metadatas=[metadata],
        )

    return sims


def show_stats(svc):
    """Show DB statistics."""
    col = svc.collection(COLLECTION)
    count = col.count()
    print(f"\n=== Pose DB stats ===")
    print(f"  Total entries: {count}")
    if count == 0:
        return

    # get all metadatas
    data = col.get(include=["metadatas", "documents"])

    # count by language
    langs = {}
    rarities = []
    tags_count = {}
    sims_ru_en = []

    for meta in data["metadatas"]:
        lang = meta.get("lang", "?")
        langs[lang] = langs.get(lang, 0) + 1

        if lang == "ru":
            rarities.append(meta.get("rarity", 5))
            for tag in meta.get("tags", "").split(","):
                tag = tag.strip()
                if tag:
                    tags_count[tag] = tags_count.get(tag, 0) + 1
            if "sim_ru_en" in meta:
                sims_ru_en.append(meta["sim_ru_en"])

    print(f"\n  By language:")
    for lang, n in sorted(langs.items()):
        print(f"    {lang}: {n}")

    n_poses = langs.get("ru", 0)
    print(f"\n  Unique poses: ~{n_poses}")

    if rarities:
        print(f"\n  Rarity distribution:")
        for r in range(1, 11):
            n = rarities.count(r)
            bar = "█" * n
            print(f"    {r:2d}: {bar} ({n})")

    if tags_count:
        print(f"\n  Top tags:")
        for tag, n in sorted(tags_count.items(), key=lambda x: -x[1])[:15]:
            print(f"    {tag:20s}  {n}")

    if sims_ru_en:
        print(f"\n  RU↔EN similarity: mean={np.mean(sims_ru_en):.4f}  min={np.min(sims_ru_en):.4f}  max={np.max(sims_ru_en):.4f}")

    # sample some entries
    print(f"\n  Recent entries:")
    ru_docs = [(doc, meta) for doc, meta in zip(data["documents"], data["metadatas"]) if meta.get("lang") == "ru"]
    for doc, meta in ru_docs[-5:]:
        print(f"    [{meta['rarity']}] {doc[:80]}...")
        print(f"        tags: {meta.get('tags', '')}")


def main():
    svc = EmbedService()

    if "--stats" in sys.argv:
        show_stats(svc)
        return

    col = svc.collection(COLLECTION)
    # clear if not resuming
    if "--resume" not in sys.argv:
        try:
            svc.db.delete_collection(COLLECTION)
        except Exception:
            pass
        col = svc.collection(COLLECTION)
        start_idx = 0
        print("Starting fresh.")
    else:
        existing = col.count() // 3  # 3 languages per pose
        start_idx = existing
        print(f"Resuming from pose #{start_idx}")

    count = DEFAULT_COUNT
    for arg in sys.argv[1:]:
        if arg.startswith("--count"):
            count = int(sys.argv[sys.argv.index(arg) + 1])

    print(f"Generating {count} poses, storing in ChromaDB '{COLLECTION}'")
    print(f"LLM: {KOBOLD_URL}")
    print(f"Press Ctrl+C to stop (use --resume to continue later)\n")

    generated = 0
    failed = 0
    t_start = time.time()

    try:
        for i in range(count):
            idx = start_idx + i

            # every 3rd pose: structured anatomical format
            use_structured = (i % 3 == 2)
            hint = random.choice(STYLE_HINTS)

            if use_structured:
                prompt = PROMPT_STRUCTURED.rstrip() + f"\nHint: {hint}\n"
            else:
                prompt = PROMPT_TEMPLATE.rstrip() + f"\nHint: {hint}\n"

            # occasionally ask for higher rarity
            if random.random() < 0.4:
                prompt += "Try to make it VERY unusual (rarity 7+).\n"

            raw = llm_generate(prompt)
            if not raw:
                failed += 1
                continue

            pose = parse_pose(raw)
            if not pose:
                failed += 1
                if generated == 0:
                    print(f"  [parse fail] raw: {raw[:200]}")
                continue

            sims = embed_and_store(svc, col, pose, idx)

            generated += 1
            elapsed = time.time() - t_start
            rate = generated / elapsed * 3600 if elapsed > 0 else 0

            # compact progress
            sim_str = f"ru↔en={sims.get('ru_en', 0):.3f}" if sims.get("ru_en") else ""
            struct_flag = " [S]" if pose.get("struct") else ""
            print(f"  [{idx + 1}] r={pose['rarity']} {sim_str}{struct_flag} {pose.get('ru', '')[:60]}")

            if generated % 50 == 0:
                print(f"\n  --- checkpoint: {generated} poses, {failed} failed, {rate:.0f}/hr ---\n")

            time.sleep(DELAY_BETWEEN)

    except KeyboardInterrupt:
        print(f"\n\nStopped by user.")

    elapsed = time.time() - t_start
    print(f"\n=== Done ===")
    print(f"  Generated: {generated}")
    print(f"  Failed: {failed}")
    print(f"  Time: {elapsed:.0f}s ({elapsed / 60:.1f}min)")
    print(f"  Rate: {generated / elapsed * 3600:.0f}/hr" if elapsed > 0 else "")

    show_stats(svc)


if __name__ == "__main__":
    main()
