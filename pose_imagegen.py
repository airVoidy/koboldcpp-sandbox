"""
Batch image generation from pose embeddings via ComfyUI (Z-image).
Reads poses from ChromaDB, sends to ComfyUI with fixed character + pose prompt.

Usage:
    python pose_imagegen.py --character "描述персонажа"
    python pose_imagegen.py --character "A girl with short hair, simple white clothes" --lang en
    python pose_imagegen.py --lang ru          # use Russian pose descriptions
    python pose_imagegen.py --lang en          # use English
    python pose_imagegen.py --lang struct      # use structured format
    python pose_imagegen.py --stats            # show what's been generated
    python pose_imagegen.py --start 50         # start from pose #50
    python pose_imagegen.py --count 100        # generate only 100
"""

import json
import random
import re
import sys
import time
import requests
from embed_service import EmbedService

# ── config ──
COMFYUI_URL = "http://127.0.0.1:8188"
COLLECTION = "poses"
WORKFLOW_PATH = r"C:\Users\vAiry\Downloads\ZImage.json"

DEFAULT_CHARACTER = ""  # set via --character or interactive input


PROGRESS_FILE = "pose_imagegen_progress.json"


def load_workflow():
    with open(WORKFLOW_PATH) as f:
        return json.load(f)


def load_progress():
    """Load set of already generated pose IDs."""
    try:
        with open(PROGRESS_FILE) as f:
            data = json.load(f)
        return set(data.get("done", []))
    except FileNotFoundError:
        return set()


def save_progress(done_set):
    """Save progress to disk."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"done": sorted(done_set)}, f)


def strip_subject(text):
    """Remove subject words from pose description."""
    # strip common subjects from beginning
    text = re.sub(
        r"^(человек|мужчина|женщина|девушка|парень|ребёнок|он|она|man|woman|person|child|dancer|a person|the person)\s+",
        "", text, flags=re.IGNORECASE
    )
    return text.strip()


def build_prompt(character, pose):
    """Build the full prompt: character + pose."""
    pose = strip_subject(pose)
    if character:
        return f"Anime style:\n{character}\n\nPose: {pose}"
    else:
        return f"Anime style:\n{pose}"


def queue_prompt(workflow, prompt_text, pose_id, lang):
    """Send prompt to ComfyUI queue."""
    # modify positive prompt (node "6")
    workflow["6"]["inputs"]["text"] = prompt_text

    # random seed
    workflow["3"]["inputs"]["seed"] = random.randint(0, 2**53)

    # filename prefix with pose info
    workflow["9"]["inputs"]["filename_prefix"] = f"pose_{pose_id}_{lang}"

    # send to ComfyUI
    try:
        resp = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("prompt_id")
    except Exception as e:
        print(f"  [ComfyUI error] {e}")
        return None


def wait_for_completion(prompt_id, timeout=120):
    """Wait for ComfyUI to finish generating."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            resp = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
            history = resp.json()
            if prompt_id in history:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def get_poses_from_db(svc, lang="ru", start=0, count=None):
    """Get poses from ChromaDB."""
    col = svc.collection(COLLECTION)

    # get all poses in specified language
    data = col.get(
        where={"lang": lang} if lang != "struct" else {"lang": "ru"},
        include=["documents", "metadatas"],
    )

    poses = []
    for doc, meta in zip(data["documents"], data["metadatas"]):
        pose_id = meta.get("pose_id", 0)

        if lang == "struct" and meta.get("struct"):
            text = meta["struct"]
        else:
            text = doc

        poses.append({
            "pose_id": pose_id,
            "text": text,
            "rarity": meta.get("rarity", 5),
            "tags": meta.get("tags", ""),
            "text_en": meta.get("text_en", ""),
            "text_ru": meta.get("text_ru", "") if lang != "ru" else doc,
            "struct": meta.get("struct", ""),
        })

    # sort by pose_id
    poses.sort(key=lambda x: x["pose_id"])

    # apply start/count
    poses = poses[start:]
    if count:
        poses = poses[:count]

    return poses


def main():
    svc = EmbedService()

    if "--stats" in sys.argv:
        col = svc.collection(COLLECTION)
        print(f"Poses in DB: {col.count()}")
        # count by language
        for lang in ["ru", "en", "zh"]:
            data = col.get(where={"lang": lang})
            print(f"  {lang}: {len(data['ids'])}")
        return

    # parse args
    lang = "en"  # default to English for image gen
    character = DEFAULT_CHARACTER
    start = 0
    count = None

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--lang" and i + 1 < len(args):
            lang = args[i + 1]
        elif arg == "--character" and i + 1 < len(args):
            character = args[i + 1]
        elif arg == "--start" and i + 1 < len(args):
            start = int(args[i + 1])
        elif arg == "--count" and i + 1 < len(args):
            count = int(args[i + 1])

    # interactive character input if not provided
    if not character:
        print("Enter character description (or press Enter for pose-only):")
        character = input("> ").strip()

    # load poses
    poses = get_poses_from_db(svc, lang=lang, start=start, count=count)
    print(f"\nLoaded {len(poses)} poses (lang={lang}, start={start})")
    print(f"Character: '{character}'" if character else "No character (pose only)")
    print(f"ComfyUI: {COMFYUI_URL}")

    # load workflow
    workflow = load_workflow()
    print(f"Workflow loaded from {WORKFLOW_PATH}\n")

    # load progress for resume
    done = load_progress()
    if done:
        print(f"Resuming: {len(done)} poses already done, skipping them.")

    generated = 0
    skipped = 0
    failed = 0
    t_start = time.time()

    try:
        for pose in poses:
            pid = pose["pose_id"]

            # skip already done
            if pid in done:
                skipped += 1
                continue

            prompt_text = build_prompt(character, pose["text"])

            prompt_id = queue_prompt(
                json.loads(json.dumps(workflow)),  # deep copy
                prompt_text,
                pid,
                lang,
            )

            if not prompt_id:
                failed += 1
                continue

            # wait for completion
            ok = wait_for_completion(prompt_id)
            if not ok:
                print(f"  [timeout] pose_{pid}")
                failed += 1
                continue

            generated += 1
            done.add(pid)

            # save progress every 5 images
            if generated % 5 == 0:
                save_progress(done)

            elapsed = time.time() - t_start
            rate = generated / elapsed * 3600 if elapsed > 0 else 0

            print(f"  [{generated}] pose_{pid} r={pose['rarity']} {pose['text'][:60]}")

            if generated % 50 == 0:
                print(f"\n  --- {generated} done, {skipped} skipped, {failed} failed, {rate:.0f}/hr ---\n")

    except KeyboardInterrupt:
        print(f"\n\nStopped.")

    # save final progress
    save_progress(done)

    elapsed = time.time() - t_start
    print(f"\n=== Done ===")
    print(f"  Generated: {generated}")
    print(f"  Skipped (already done): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Time: {elapsed:.0f}s ({elapsed / 60:.1f}min)")
    if elapsed > 0:
        print(f"  Rate: {generated / elapsed * 3600:.0f}/hr")


if __name__ == "__main__":
    main()
