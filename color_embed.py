"""
Color embedding experiment: how does the embedding space represent colors?
Multiple representations (name, RGB, CMYK, Russian names) + saturation/brightness variants.
"""

import colorsys
import json
from pathlib import Path

import numpy as np
from embed_service import EmbedService

# ── Base pure colors with RGB ──
BASE_COLORS = {
    "red":     (255, 0, 0),
    "green":   (0, 128, 0),
    "blue":    (0, 0, 255),
    "yellow":  (255, 255, 0),
    "cyan":    (0, 255, 255),
    "magenta": (255, 0, 255),
    "orange":  (255, 165, 0),
    "purple":  (128, 0, 128),
    "pink":    (255, 192, 203),
    "brown":   (139, 69, 19),
    "white":   (255, 255, 255),
    "black":   (0, 0, 0),
    "gray":    (128, 128, 128),
}

# ── Russian names for pure colors ──
RU_NAMES = {
    "red": "красный",
    "green": "зелёный",
    "blue": "синий",
    "yellow": "жёлтый",
    "cyan": "голубой",
    "magenta": "пурпурный",
    "orange": "оранжевый",
    "purple": "фиолетовый",
    "pink": "розовый",
    "brown": "коричневый",
    "white": "белый",
    "black": "чёрный",
    "gray": "серый",
}

# ── Extended color names (EN + RU) ──
EXTENDED_COLORS = {
    # reds
    "crimson": ((220, 20, 60), "малиновый"),
    "scarlet": ((255, 36, 0), "алый"),
    "burgundy": ((128, 0, 32), "бордовый"),
    "coral": ((255, 127, 80), "коралловый"),
    "salmon": ((250, 128, 114), "лососевый"),
    "ruby": ((224, 17, 95), "рубиновый"),
    "cherry": ((222, 49, 99), "вишнёвый"),
    "raspberry": ((227, 11, 92), "малиновый"),
    # oranges
    "tangerine": ((255, 148, 0), "мандариновый"),
    "peach": ((255, 218, 185), "персиковый"),
    "amber": ((255, 191, 0), "янтарный"),
    "apricot": ((251, 206, 177), "абрикосовый"),
    # yellows
    "gold": ((255, 215, 0), "золотой"),
    "lemon": ((255, 247, 0), "лимонный"),
    "honey": ((235, 177, 52), "медовый"),
    "mustard": ((255, 219, 88), "горчичный"),
    "canary": ((255, 239, 0), "канареечный"),
    # greens
    "emerald": ((0, 155, 119), "изумрудный"),
    "lime": ((0, 255, 0), "лаймовый"),
    "olive": ((128, 128, 0), "оливковый"),
    "mint": ((152, 255, 152), "мятный"),
    "forest green": ((34, 139, 34), "лесной зелёный"),
    "jade": ((0, 168, 107), "нефритовый"),
    "pistachio": ((147, 197, 114), "фисташковый"),
    "malachite": ((11, 218, 81), "малахитовый"),
    # blues
    "navy": ((0, 0, 128), "тёмно-синий"),
    "sky blue": ((135, 206, 235), "небесный"),
    "turquoise": ((64, 224, 208), "бирюзовый"),
    "azure": ((0, 127, 255), "лазурный"),
    "cobalt": ((0, 71, 171), "кобальтовый"),
    "sapphire": ((15, 82, 186), "сапфировый"),
    "indigo": ((75, 0, 130), "индиго"),
    "cornflower": ((100, 149, 237), "васильковый"),
    # purples
    "lavender": ((230, 230, 250), "лавандовый"),
    "violet": ((127, 0, 255), "фиалковый"),
    "plum": ((142, 69, 133), "сливовый"),
    "lilac": ((200, 162, 200), "сиреневый"),
    "mauve": ((224, 176, 255), "мальва"),
    "amethyst": ((153, 102, 204), "аметистовый"),
    # neutrals
    "ivory": ((255, 255, 240), "слоновая кость"),
    "beige": ((245, 245, 220), "бежевый"),
    "cream": ((255, 253, 208), "кремовый"),
    "charcoal": ((54, 69, 79), "угольный"),
    "silver": ((192, 192, 192), "серебряный"),
    "steel": ((70, 130, 180), "стальной"),
    "ash": ((178, 190, 181), "пепельный"),
    # others
    "chartreuse": ((127, 255, 0), "шартрёз"),
    "teal": ((0, 128, 128), "бирюзово-зелёный"),
    "khaki": ((195, 176, 145), "хаки"),
    "terracotta": ((204, 78, 92), "терракотовый"),
    "sand": ((194, 178, 128), "песочный"),
    "chocolate": ((123, 63, 0), "шоколадный"),
    "wine": ((114, 47, 55), "винный"),
    "coffee": ((111, 78, 55), "кофейный"),
}


def rgb_to_cmyk(r, g, b):
    if r == 0 and g == 0 and b == 0:
        return 0, 0, 0, 100
    c = 1 - r / 255
    m = 1 - g / 255
    y = 1 - b / 255
    k = min(c, m, y)
    c = round((c - k) / (1 - k) * 100)
    m = round((m - k) / (1 - k) * 100)
    y = round((y - k) / (1 - k) * 100)
    k = round(k * 100)
    return c, m, y, k


def rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"


def generate_variants(name, rgb, count=8):
    """Generate brightness/saturation variants of a color."""
    r, g, b = rgb
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    variants = []

    # vary value (brightness)
    for i in range(count):
        factor = (i + 1) / count
        new_v = min(1.0, v * factor + (1 - factor) * 0.1)
        nr, ng, nb = colorsys.hsv_to_rgb(h, s, new_v)
        nr, ng, nb = int(nr * 255), int(ng * 255), int(nb * 255)

        if factor < 0.3:
            prefix = "very dark"
        elif factor < 0.5:
            prefix = "dark"
        elif factor < 0.7:
            prefix = "medium"
        elif factor < 0.9:
            prefix = "light"
        else:
            prefix = "very light"

        variants.append({
            "name": f"{prefix} {name}",
            "rgb": (nr, ng, nb),
        })

    return variants


def build_dataset():
    """Build all text representations for embedding."""
    entries = []

    # ── Base pure colors: multiple representations ──
    for name, rgb in BASE_COLORS.items():
        r, g, b = rgb
        c, m, y, k = rgb_to_cmyk(r, g, b)
        hex_val = rgb_to_hex(r, g, b)
        ru = RU_NAMES[name]

        base = {
            "color": name,
            "rgb": rgb,
            "hex": hex_val,
        }

        # different text representations of the same color
        entries.append({**base, "repr": "name_en", "text": name})
        entries.append({**base, "repr": "name_ru", "text": ru})
        entries.append({**base, "repr": "rgb", "text": f"RGB({r}, {g}, {b})"})
        entries.append({**base, "repr": "cmyk", "text": f"CMYK({c}%, {m}%, {y}%, {k}%)"})
        entries.append({**base, "repr": "hex", "text": hex_val})
        entries.append({**base, "repr": "desc_en", "text": f"the color {name}"})
        entries.append({**base, "repr": "desc_ru", "text": f"цвет {ru}"})

        # brightness/saturation variants
        if name not in ("white", "black", "gray"):
            for var in generate_variants(name, rgb):
                vr, vg, vb = var["rgb"]
                entries.append({
                    "color": name,
                    "rgb": var["rgb"],
                    "hex": rgb_to_hex(vr, vg, vb),
                    "repr": "variant",
                    "text": var["name"],
                })

    # ── Extended colors ──
    for name, (rgb, ru) in EXTENDED_COLORS.items():
        r, g, b = rgb
        hex_val = rgb_to_hex(r, g, b)

        entries.append({"color": name, "rgb": rgb, "hex": hex_val, "repr": "name_en", "text": name})
        entries.append({"color": name, "rgb": rgb, "hex": hex_val, "repr": "name_ru", "text": ru})
        entries.append({"color": name, "rgb": rgb, "hex": hex_val, "repr": "desc_en", "text": f"the color {name}"})
        entries.append({"color": name, "rgb": rgb, "hex": hex_val, "repr": "desc_ru", "text": f"цвет {ru}"})

    return entries


def main():
    print("Building color dataset...")
    entries = build_dataset()
    print(f"  {len(entries)} text entries")

    texts = [e["text"] for e in entries]

    print("Embedding...")
    svc = EmbedService()
    embeddings = svc.encode_docs(texts)
    print(f"  {len(embeddings)} embeddings, dim={len(embeddings[0])}")

    # store in chroma
    print("Storing in ChromaDB...")
    col = svc.collection("colors")
    # clear if exists
    try:
        svc.db.delete_collection("colors")
        col = svc.collection("colors")
    except Exception:
        pass

    col.add(
        ids=[f"c_{i}" for i in range(len(entries))],
        embeddings=embeddings,
        documents=texts,
        metadatas=[{
            "color": e["color"],
            "repr": e["repr"],
            "hex": e["hex"],
            "r": e["rgb"][0], "g": e["rgb"][1], "b": e["rgb"][2],
        } for e in entries],
    )
    print(f"  stored {col.count()} entries")

    # ── Analysis ──
    emb_array = np.array(embeddings)

    # group by base color
    color_groups = {}
    for i, e in enumerate(entries):
        c = e["color"]
        if c not in color_groups:
            color_groups[c] = []
        color_groups[c].append(i)

    # average embedding per color
    print("\n=== Cross-representation consistency ===")
    print("(cosine between different representations of same color)")
    for color in list(BASE_COLORS.keys()):
        idxs = color_groups.get(color, [])
        if len(idxs) < 2:
            continue
        vecs = emb_array[idxs]
        # pairwise cosine
        cosines = []
        for i in range(len(vecs)):
            for j in range(i + 1, len(vecs)):
                c = np.dot(vecs[i], vecs[j]) / (np.linalg.norm(vecs[i]) * np.linalg.norm(vecs[j]))
                cosines.append(c)
        print(f"  {color:12s}  mean={np.mean(cosines):.4f}  min={np.min(cosines):.4f}  max={np.max(cosines):.4f}  (n={len(idxs)} repr)")

    # nearest neighbors for each pure color name
    print("\n=== Nearest neighbors (by English name) ===")
    for color in ["red", "blue", "green", "yellow", "purple", "orange"]:
        results = col.query(
            query_embeddings=[emb_array[entries.index(next(e for e in entries if e["color"] == color and e["repr"] == "name_en"))].tolist()],
            n_results=8,
            where={"repr": {"$ne": "variant"}},
        )
        nns = [
            f"{m['color']}({m['repr']})={d:.3f}"
            for d, m in zip(results["distances"][0][1:], results["metadatas"][0][1:])
        ]
        print(f"  {color}: {', '.join(nns)}")

    # representation clustering: do RGB strings cluster together?
    print("\n=== Representation type clustering ===")
    print("(avg cosine within same repr type vs across types)")
    repr_groups = {}
    for i, e in enumerate(entries):
        rp = e["repr"]
        if rp not in repr_groups:
            repr_groups[rp] = []
        repr_groups[rp].append(i)

    for rp, idxs in sorted(repr_groups.items()):
        if len(idxs) < 3:
            continue
        vecs = emb_array[idxs]
        # within-group avg cosine (sample)
        sample = min(50, len(idxs))
        chosen = np.random.choice(len(idxs), sample, replace=False)
        cosines = []
        for i in range(len(chosen)):
            for j in range(i + 1, len(chosen)):
                c = np.dot(vecs[chosen[i]], vecs[chosen[j]]) / (np.linalg.norm(vecs[chosen[i]]) * np.linalg.norm(vecs[chosen[j]]))
                cosines.append(c)
        print(f"  {rp:12s}  n={len(idxs):3d}  within-group cosine={np.mean(cosines):.4f}")

    # ── UMAP visualization ──
    print("\n=== Generating UMAP plot ===")
    try:
        from umap import UMAP
        import matplotlib.pyplot as plt
        import matplotlib

        reducer = UMAP(n_components=2, random_state=42, n_neighbors=15, min_dist=0.1)
        coords = reducer.fit_transform(emb_array)

        fig, axes = plt.subplots(1, 2, figsize=(24, 10))

        # Plot 1: colored by actual RGB
        ax = axes[0]
        ax.set_title("Colors in embedding space (actual RGB)", fontsize=14)
        for i, e in enumerate(entries):
            r, g, b = e["rgb"]
            color_hex = f"#{r:02x}{g:02x}{b:02x}"
            marker = {"name_en": "o", "name_ru": "s", "rgb": "^", "cmyk": "v",
                       "hex": "D", "desc_en": "p", "desc_ru": "*", "variant": "."}.get(e["repr"], "o")
            size = 20 if e["repr"] == "variant" else 60
            ax.scatter(coords[i, 0], coords[i, 1], c=color_hex, marker=marker,
                      s=size, edgecolors="gray", linewidths=0.3, alpha=0.8)
        # label base colors
        for e_idx, e in enumerate(entries):
            if e["repr"] == "name_en" and e["color"] in BASE_COLORS:
                ax.annotate(e["color"], (coords[e_idx, 0], coords[e_idx, 1]),
                           fontsize=8, ha="center", va="bottom")

        # Plot 2: colored by representation type
        ax = axes[1]
        ax.set_title("Colors in embedding space (by representation type)", fontsize=14)
        repr_colors = {"name_en": "red", "name_ru": "blue", "rgb": "green", "cmyk": "orange",
                       "hex": "purple", "desc_en": "brown", "desc_ru": "pink", "variant": "gray"}
        for rp, rp_color in repr_colors.items():
            idxs = repr_groups.get(rp, [])
            if idxs:
                ax.scatter(coords[idxs, 0], coords[idxs, 1], c=rp_color, label=rp,
                          s=20 if rp == "variant" else 50, alpha=0.7)
        ax.legend(fontsize=9)

        plt.tight_layout()
        plt.savefig("color_embeddings.png", dpi=150, bbox_inches="tight")
        print("  saved color_embeddings.png")
        plt.close()

    except ImportError as e:
        print(f"  skipped (install umap-learn matplotlib): {e}")

    # save raw data for further analysis
    with open("color_embeddings.json", "w", encoding="utf-8") as f:
        json.dump([{
            "text": e["text"],
            "color": e["color"],
            "repr": e["repr"],
            "rgb": list(e["rgb"]),
            "hex": e["hex"],
        } for e in entries], f, ensure_ascii=False, indent=2)
    print(f"\n  saved color_embeddings.json ({len(entries)} entries)")
    print("\nDone!")


if __name__ == "__main__":
    main()
