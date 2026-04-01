"""
Pose embedding: EN vs RU comparison.
Same poses, two languages — is the structure different?
"""

import numpy as np
from embed_service import EmbedService

svc = EmbedService()


def cos(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def embed(text):
    return np.array(svc.encode_docs([text])[0])


# ── paired poses RU/EN ──
pairs = [
    ("склонил голову", "bowed his head"),
    ("наклонил шею", "tilted his neck"),
    ("опустил голову", "lowered his head"),
    ("повесил голову", "hung his head"),
    ("голова запрокинута", "head thrown back"),
    ("поднял голову", "raised his head"),
    ("повернул голову", "turned his head"),
    ("кивнул", "nodded"),
    ("покачал головой", "shook his head"),
    ("стоит прямо", "standing straight"),
    ("стоит ссутулившись", "standing hunched"),
    ("стоит подбоченившись", "standing with arms akimbo"),
    ("стоит скрестив руки", "standing with arms crossed"),
    ("сидит прямо", "sitting upright"),
    ("сидит развалившись", "sitting slouched"),
    ("сидит нога на ногу", "sitting cross-legged"),
    ("лежит на спине", "lying on his back"),
    ("лежит на боку", "lying on his side"),
    ("свернулся калачиком", "curled up"),
    ("идёт быстрым шагом", "walking briskly"),
    ("крадётся", "sneaking"),
    ("бежит", "running"),
    ("ползёт", "crawling"),
    ("съёжился", "cringed"),
    ("выпрямился во весь рост", "stood up to full height"),
    ("сгорбился", "hunched over"),
    ("расправил плечи", "straightened his shoulders"),
    ("поник", "drooped"),
    ("замер", "froze"),
    ("отшатнулся", "recoiled"),
]

# ── cross-language: is the same pose close? ──
print("=== Cross-language: RU vs EN same pose ===")
cross_scores = []
for ru, en in pairs:
    ru_emb = embed(ru)
    en_emb = embed(en)
    c = cos(ru_emb, en_emb)
    cross_scores.append(c)
    print(f"  {c:.4f}  '{ru}' ↔ '{en}'")
print(f"\n  avg cross-language cosine: {np.mean(cross_scores):.4f}")

# ── key comparison in both languages ──
print("\n=== Ключевое сравнение ===")
ru_a, ru_b = embed("склонил голову"), embed("наклонил шею")
en_a, en_b = embed("bowed his head"), embed("tilted his neck")
print(f"  RU: склонил голову ↔ наклонил шею  = {cos(ru_a, ru_b):.4f}")
print(f"  EN: bowed his head ↔ tilted his neck = {cos(en_a, en_b):.4f}")

# ── within-language nearest pairs ──
print("\n=== Top-10 ближайших пар (RU) ===")
ru_texts = [p[0] for p in pairs]
ru_embs = {t: embed(t) for t in ru_texts}
ru_pairs = []
for i in range(len(ru_texts)):
    for j in range(i + 1, len(ru_texts)):
        c = cos(ru_embs[ru_texts[i]], ru_embs[ru_texts[j]])
        ru_pairs.append((c, ru_texts[i], ru_texts[j]))
ru_pairs.sort(reverse=True)
for c, a, b in ru_pairs[:10]:
    print(f"  {c:.4f}  '{a}' ↔ '{b}'")

print("\n=== Top-10 ближайших пар (EN) ===")
en_texts = [p[1] for p in pairs]
en_embs = {t: embed(t) for t in en_texts}
en_pairs = []
for i in range(len(en_texts)):
    for j in range(i + 1, len(en_texts)):
        c = cos(en_embs[en_texts[i]], en_embs[en_texts[j]])
        en_pairs.append((c, en_texts[i], en_texts[j]))
en_pairs.sort(reverse=True)
for c, a, b in en_pairs[:10]:
    print(f"  {c:.4f}  '{a}' ↔ '{b}'")

# ── category classifier in both languages ──
print("\n=== Категории RU ===")
cats_ru = {c: embed(c) for c in ["поза", "действие", "эмоция", "жест"]}
for ru, en in pairs[:15]:  # first 15 for brevity
    n_emb = embed(ru)
    scores = sorted([(cos(n_emb, ce), cn) for cn, ce in cats_ru.items()], reverse=True)
    top = scores[0]
    print(f"  {ru:30s}  {top[1]}={top[0]:.3f}")

print("\n=== Categories EN ===")
cats_en = {c: embed(c) for c in ["pose", "action", "emotion", "gesture"]}
for ru, en in pairs[:15]:
    n_emb = embed(en)
    scores = sorted([(cos(n_emb, ce), cn) for cn, ce in cats_en.items()], reverse=True)
    top = scores[0]
    print(f"  {en:35s}  {top[1]}={top[0]:.3f}")

# ── spread comparison ──
print("\n=== Разброс (avg pairwise cosine) ===")
ru_cosines = [c for c, _, _ in ru_pairs]
en_cosines = [c for c, _, _ in en_pairs]
print(f"  RU: mean={np.mean(ru_cosines):.4f}  std={np.std(ru_cosines):.4f}  min={np.min(ru_cosines):.4f}  max={np.max(ru_cosines):.4f}")
print(f"  EN: mean={np.mean(en_cosines):.4f}  std={np.std(en_cosines):.4f}  min={np.min(en_cosines):.4f}  max={np.max(en_cosines):.4f}")
marker = "RU кучнее" if np.mean(ru_cosines) > np.mean(en_cosines) else "EN кучнее"
print(f"  → {marker}")

print("\nDone!")
