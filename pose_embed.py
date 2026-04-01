"""
Pose embedding experiment: how close are similar body descriptions?
"склонил голову" vs "наклонил шею" — same pose, different words?
"""

import numpy as np
from embed_service import EmbedService

svc = EmbedService()


def cos(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def embed(text):
    return np.array(svc.encode_docs([text])[0])


# ── key comparison ──
print("=== Склонил голову vs наклонил шею ===")
a = embed("склонил голову")
b = embed("наклонил шею")
print(f"  cosine={cos(a, b):.4f}  dist={1 - cos(a, b):.4f}")

# ── head/neck pose variations ──
print("\n=== Вариации наклона головы ===")
head_poses = [
    "склонил голову",
    "наклонил голову",
    "опустил голову",
    "повесил голову",
    "наклонил шею",
    "склонил шею",
    "голова наклонена вбок",
    "голова опущена",
    "голова запрокинута",
    "поднял голову",
    "задрал голову",
    "повернул голову",
    "отвернул голову",
    "кивнул",
    "покачал головой",
]

head_embs = {p: embed(p) for p in head_poses}
base = head_embs["склонил голову"]

print(f"  (от 'склонил голову')")
dists = [(1 - cos(base, e), p) for p, e in head_embs.items() if p != "склонил голову"]
dists.sort()
for d, p in dists:
    print(f"  {d:.4f}  {p}")

# ── full body poses ──
print("\n=== Позы тела ===")
body_poses = [
    # стоя
    "стоит прямо",
    "стоит ссутулившись",
    "стоит подбоченившись",
    "стоит руки в боки",
    "стоит скрестив руки",
    "стоит руки за спиной",
    "облокотился на стену",
    # сидя
    "сидит прямо",
    "сидит развалившись",
    "сидит нога на ногу",
    "сидит подперев голову рукой",
    "сидит обхватив колени",
    "сидит на корточках",
    # лёжа
    "лежит на спине",
    "лежит на боку",
    "лежит ничком",
    "свернулся калачиком",
    # движение
    "идёт быстрым шагом",
    "крадётся",
    "бежит",
    "прыгает",
    "ползёт",
    # эмоциональные позы
    "съёжился",
    "выпрямился во весь рост",
    "сгорбился",
    "расправил плечи",
    "поник",
    "вытянулся по струнке",
    "замер",
    "отшатнулся",
]

body_embs = {p: embed(p) for p in body_poses}

# pairwise most similar
print("  Top-10 ближайших пар:")
pairs = []
pose_list = list(body_poses)
for i in range(len(pose_list)):
    for j in range(i + 1, len(pose_list)):
        c = cos(body_embs[pose_list[i]], body_embs[pose_list[j]])
        pairs.append((c, pose_list[i], pose_list[j]))
pairs.sort(reverse=True)
for c, a, b in pairs[:10]:
    print(f"  {c:.4f}  '{a}' ↔ '{b}'")

print("\n  Top-10 самых далёких пар:")
for c, a, b in pairs[-10:]:
    print(f"  {c:.4f}  '{a}' ↔ '{b}'")

# ── sensory category: is it a pose? ──
print("\n=== Категория: поза vs действие vs эмоция vs место ===")
categories = {
    "поза": embed("поза"),
    "действие": embed("действие"),
    "эмоция": embed("эмоция"),
    "место": embed("место"),
    "жест": embed("жест"),
}

all_poses = head_poses + body_poses
for name in all_poses:
    n_emb = embed(name)
    scores = [(cos(n_emb, c_emb), c_name) for c_name, c_emb in categories.items()]
    scores.sort(reverse=True)
    top = scores[0]
    all_str = "  ".join(f"{c}={v:.3f}" for v, c in scores)
    print(f"  {name:35s}  {all_str}")

# ── synonym pairs: same pose, different words ──
print("\n=== Синонимичные пары (одна поза — разные слова) ===")
synonym_pairs = [
    ("склонил голову", "наклонил шею"),
    ("склонил голову", "опустил голову"),
    ("стоит прямо", "выпрямился во весь рост"),
    ("стоит прямо", "вытянулся по струнке"),
    ("сидит развалившись", "сидит нога на ногу"),
    ("сгорбился", "ссутулился"),
    ("сгорбился", "съёжился"),
    ("лежит ничком", "лежит на животе"),
    ("крадётся", "идёт на цыпочках"),
    ("замер", "застыл"),
    ("отшатнулся", "отпрянул"),
    ("расправил плечи", "выпрямился"),
    ("поник", "повесил голову"),
    ("стоит руки в боки", "стоит подбоченившись"),
]
for a_text, b_text in synonym_pairs:
    a_emb = embed(a_text)
    b_emb = embed(b_text)
    c = cos(a_emb, b_emb)
    print(f"  {c:.4f}  '{a_text}' ↔ '{b_text}'")

print("\nDone!")
