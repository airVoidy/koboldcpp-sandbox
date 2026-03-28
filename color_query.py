"""Quick color embedding queries."""

import sys
import numpy as np
from embed_service import EmbedService

svc = EmbedService()
col = svc.collection("colors")
print(f"Colors in DB: {col.count()}")

# ── browse DB contents ──
if "--browse" in sys.argv:
    data = col.get(include=["documents", "metadatas"])
    reprs = {}
    colors = {}
    for doc, meta in zip(data["documents"], data["metadatas"]):
        r = meta["repr"]
        c = meta["color"]
        reprs[r] = reprs.get(r, 0) + 1
        colors[c] = colors.get(c, 0) + 1

    print(f"\n=== DB overview ===")
    print(f"  Total entries: {len(data['ids'])}")
    print(f"\n  By repr type:")
    for r, n in sorted(reprs.items(), key=lambda x: -x[1]):
        print(f"    {r:12s}  {n}")
    print(f"\n  By color ({len(colors)} unique):")
    for c, n in sorted(colors.items(), key=lambda x: -x[1])[:20]:
        print(f"    {c:20s}  {n} entries")
    if len(colors) > 20:
        print(f"    ... and {len(colors) - 20} more")

    # sample entries
    print(f"\n  Sample entries:")
    for i in range(min(10, len(data["ids"]))):
        print(f"    [{data['ids'][i]}] \"{data['documents'][i]}\"  {data['metadatas'][i]}")
    sys.exit(0)

# ── opponent pairs: cross-language comparison ──
print("\n=== Opponent pairs (cosine distance) ===")
pairs = [
    ("red", "green"),
    ("красный", "зелёный"),
    ("red", "красный"),
    ("green", "зелёный"),
    ("red", "зелёный"),
    ("красный", "green"),
    ("blue", "yellow"),
    ("синий", "жёлтый"),
    ("blue", "синий"),
    ("yellow", "жёлтый"),
    ("blue", "жёлтый"),
    ("синий", "yellow"),
]

emb_cache = {}
for pair in pairs:
    for word in pair:
        if word not in emb_cache:
            emb_cache[word] = np.array(svc.encode_docs([word])[0])

for a, b in pairs:
    cos = np.dot(emb_cache[a], emb_cache[b]) / (
        np.linalg.norm(emb_cache[a]) * np.linalg.norm(emb_cache[b])
    )
    dist = 1 - cos
    print(f"  {a:12s} → {b:12s}  cos={cos:.4f}  dist={dist:.4f}")

# ── search by Russian descriptive names ──
print("\n=== Semantic search: descriptive queries ===")
queries = [
    "тёплый оттенок заката",
    "холодный зимний цвет",
    "цвет весенней листвы",
    "глубокий жёлто-коричневый",
    "олень коричневый",
    "орехово-коричневый",
]
for q in queries:
    # EN names
    res_en = col.query(
        query_embeddings=svc.encode_docs([q]),
        n_results=5,
        where={"repr": "name_en"},
    )
    # RU names
    res_ru = col.query(
        query_embeddings=svc.encode_docs([q]),
        n_results=5,
        where={"repr": "name_ru"},
    )
    # RU descriptions
    res_desc = col.query(
        query_embeddings=svc.encode_docs([q]),
        n_results=5,
        where={"repr": "desc_ru"},
    )
    hits_en = [f"{m['color']}={d:.3f}" for d, m in zip(res_en["distances"][0], res_en["metadatas"][0])]
    hits_ru = [f"{d['documents'][0]}={d2:.3f}" for d2, d in zip(res_ru["distances"][0], [{"documents": [doc]} for doc in res_ru["documents"][0]])]
    hits_desc = [f"{doc}={d:.3f}" for d, doc in zip(res_desc["distances"][0], res_desc["documents"][0])]
    print(f"  \"{q}\"")
    print(f"    EN: {', '.join(hits_en)}")
    print(f"    RU: {', '.join(hits_ru)}")
    print(f"    desc: {', '.join(hits_desc)}")

# ── flag triads: cultural clustering ──
print("\n=== Flag triads ===")
triads = [
    ("RU flag", ["синий", "белый", "красный"], ["blue", "white", "red"]),
    ("FR flag", ["синий", "белый", "красный"], ["bleu", "blanc", "rouge"]),
    ("DE flag", ["чёрный", "красный", "золотой"], ["black", "red", "gold"]),
    ("UA flag", ["синий", "жёлтый"], ["blue", "yellow"]),
    ("IT flag", ["зелёный", "белый", "красный"], ["green", "white", "red"]),
    ("JP flag", ["белый", "красный"], ["white", "red"]),
]
for name, ru_words, en_words in triads:
    ru_embs = [np.array(svc.encode_docs([w])[0]) for w in ru_words]
    en_embs = [np.array(svc.encode_docs([w])[0]) for w in en_words]
    # avg pairwise cosine within triad
    def avg_cos(embs):
        if len(embs) < 2:
            return 0.0
        cosines = []
        for i in range(len(embs)):
            for j in range(i + 1, len(embs)):
                cosines.append(np.dot(embs[i], embs[j]) / (np.linalg.norm(embs[i]) * np.linalg.norm(embs[j])))
        return np.mean(cosines)
    ru_cos = avg_cos(ru_embs)
    en_cos = avg_cos(en_embs)
    diff = ru_cos - en_cos
    marker = "←RU closer" if diff > 0.005 else "←EN closer" if diff < -0.005 else "≈"
    print(f"  {name:8s}  RU({','.join(ru_words)})={ru_cos:.4f}  EN({','.join(en_words)})={en_cos:.4f}  {marker}")

# ── голубой: unique Russian basic color ──
print("\n=== Голубой neighborhood ===")
goluboy = np.array(svc.encode_docs(["голубой"])[0])
targets = [
    "синий", "blue", "cyan", "sky blue", "light blue",
    "azure", "лазурный", "бирюзовый", "turquoise",
    "небесный", "голубой цвет", "ice blue",
]
dists = []
for t in targets:
    t_emb = np.array(svc.encode_docs([t])[0])
    cos = np.dot(goluboy, t_emb) / (np.linalg.norm(goluboy) * np.linalg.norm(t_emb))
    dists.append((1 - cos, t))
dists.sort()
for d, t in dists:
    print(f"  {d:.4f}  {t}")

# ── contextual color terms: color vs object ──
print("\n=== Контекстные цвета: к цвету или к объекту? ===")
context_pairs = [
    # (term, expected_color, expected_object)
    ("карие", "коричневый", "глаза"),
    ("голубые", "голубой", "глаза"),
    ("синие", "синий", "глаза"),
    ("чёрные", "чёрный", "глаза"),
    ("русые", "коричневый", "волосы"),
    ("рыжие", "оранжевый", "волосы"),
    ("вороной", "чёрный", "конь"),
    ("алый", "красный", "закат"),
    ("багровый", "красный", "лицо"),
    ("седые", "серый", "волосы"),
]
for term, color, obj in context_pairs:
    t_emb = np.array(svc.encode_docs([term])[0])
    c_emb = np.array(svc.encode_docs([color])[0])
    o_emb = np.array(svc.encode_docs([obj])[0])
    cos_color = np.dot(t_emb, c_emb) / (np.linalg.norm(t_emb) * np.linalg.norm(c_emb))
    cos_obj = np.dot(t_emb, o_emb) / (np.linalg.norm(t_emb) * np.linalg.norm(o_emb))
    closer = "← цвет" if cos_color > cos_obj else "← объект"
    print(f"  {term:12s}  →{color:12s}={cos_color:.4f}  →{obj:8s}={cos_obj:.4f}  {closer}")

# ── exotic Yandex color names: does the model get them? ──
print("\n=== Экзотические названия → ближайший базовый цвет ===")
base_colors_ru = {
    "красный": np.array(svc.encode_docs(["красный"])[0]),
    "оранжевый": np.array(svc.encode_docs(["оранжевый"])[0]),
    "жёлтый": np.array(svc.encode_docs(["жёлтый"])[0]),
    "зелёный": np.array(svc.encode_docs(["зелёный"])[0]),
    "голубой": np.array(svc.encode_docs(["голубой"])[0]),
    "синий": np.array(svc.encode_docs(["синий"])[0]),
    "фиолетовый": np.array(svc.encode_docs(["фиолетовый"])[0]),
    "розовый": np.array(svc.encode_docs(["розовый"])[0]),
    "коричневый": np.array(svc.encode_docs(["коричневый"])[0]),
    "серый": np.array(svc.encode_docs(["серый"])[0]),
    "белый": np.array(svc.encode_docs(["белый"])[0]),
    "чёрный": np.array(svc.encode_docs(["чёрный"])[0]),
}

exotic_names = [
    # яндекс палитра
    "розовато-лавандовый",
    "бледно-песочный",
    "циннвальдитовый",
    "бледно-коричневый",
    "тёмно-каштановый",
    "тёмно-мандариновый",
    "тыквенный",
    "последний вздох Жако",
    "мандариновый",
    "сигнальный оранжевый",
    "весенне-зелёный",
    "аквамариновый",
    "панг",
    "лягушки в обмороке",
    "маренго",
    "ярко-бирюзовый",
    "электрик",
    "бледно-синий",
    "серебристый",
    "синий Клейна",
    "синей стали",
    "воды пляжа Бонди",
    "лазурный",
    "морской волны",
    "сливовый",
    "фиолетово-баклажанный",
    "орхидеевый",
    "гелиотроповый",
    "фиалковый",
    # бонус
    "пыльная роза",
    "цвет бедра испуганной нимфы",
    "влюблённой жабы",
    "медвежьего ушка",
    "драконьей зелени",
]

# ── sensory category classifier via embedding distance ──
print("\n=== Сенсорная категория (расстояние до цвет/звук/вкус/запах) ===")
categories = {
    "цвет": np.array(svc.encode_docs(["цвет"])[0]),
    "звук": np.array(svc.encode_docs(["звук"])[0]),
    "вкус": np.array(svc.encode_docs(["вкус"])[0]),
    "запах": np.array(svc.encode_docs(["запах"])[0]),
    "предмет": np.array(svc.encode_docs(["предмет"])[0]),
}

for name in exotic_names:
    n_emb = np.array(svc.encode_docs([name])[0])
    scores = []
    for cat_name, cat_emb in categories.items():
        cos = np.dot(n_emb, cat_emb) / (np.linalg.norm(n_emb) * np.linalg.norm(cat_emb))
        scores.append((cos, cat_name))
    scores.sort(reverse=True)
    top = scores[0]
    all_str = "  ".join(f"{c}={v:.3f}" for v, c in scores)
    marker = "✓" if top[1] == "цвет" else f"← {top[1]}"
    print(f"  {name:35s}  {all_str}  {marker}")
