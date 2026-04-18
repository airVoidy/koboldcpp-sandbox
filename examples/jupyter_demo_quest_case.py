"""
Demo: preprocessing quest_order_case через jupyter_layer.

Показывает полный цикл:
  1. Загрузка source_text.md
  2. Препроцессинг (sentences / tokens / entities / facts) — в kernel или локально
  3. Складываем в Panel с иерархией (+ sub_panel)
  4. L0 view: структура + статус материализации
  5. Lazy fetch отдельных объектов
  6. LocalStore сохраняет метадату

Запуск:
  python examples/jupyter_demo_quest_case.py           # standalone (без ядра)
  python examples/jupyter_demo_quest_case.py --live    # с живым Jupyter ядром
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

# src на path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from jupyter_layer import Panel, JupyterObject, LocalStore  # noqa: E402

LIVE = "--live" in sys.argv

# ── Панель-рендер (локальный helper, не часть библиотеки) ────────────────────

def describe_panel(panel: Panel, indent: int = 0) -> None:
    """Pretty-print структуру Panel + материализацию каждого объекта."""
    pad = "  " * indent
    backed = "kernel" if panel.scope else "standalone"
    print(f"{pad}╔═ Panel[{panel.name}] ({backed}, meta={panel.meta})")

    for oid in panel.list_ids():
        obj = panel.get(oid)
        mat = "●" if obj._fetched else "○"  # ● fetched  ○ lazy
        meta_str = f"meta={obj.meta}" if obj.meta else ""
        print(f"{pad}║  [{mat}] {oid:20s} {meta_str}")

    for sub_name in panel.list_panel_ids():
        describe_panel(panel.sub_panel(sub_name), indent + 1)
    print(f"{pad}╚" + "═" * 60)


# ── Препроцессинг ────────────────────────────────────────────────────────────
#
# Код препроцессинга — один и тот же, просто выполняется либо в живом ядре,
# либо локально. В live-режиме результаты остаются в kernel namespace, а
# Panel даёт L0-view через JupyterScope. В standalone режиме — считаем
# локально и кладём в Panel как готовые значения.

PREPROCESS_CODE = r"""
import re as _re

raw_text = __RAW_TEXT__

# sentences: split by period/question/exclamation
sentences = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', raw_text) if s.strip()]

# tokens: whitespace split
tokens_per_sentence = [s.split() for s in sentences]
total_tokens = sum(len(t) for t in tokens_per_sentence)

# facts: numbered lines (1. ..., 2. ..., etc.)
facts = _re.findall(r'^\s*\d+\.\s+(.+?)$', raw_text, _re.MULTILINE)

# entities: capitalized Russian names (simple heuristic)
names_pool = ['Лера', 'Максим', 'Софья', 'Илья', 'Диана', 'Елисей', 'Анна']
mentions = {n: raw_text.count(n) for n in names_pool}
"""


def load_source_text() -> str:
    src = ROOT / "examples" / "quest_order_case" / "source_text.md"
    return src.read_text(encoding="utf-8")


def run_standalone(raw_text: str) -> dict:
    """Выполнить препроцессинг локально, вернуть namespace."""
    ns: dict = {"__RAW_TEXT__": raw_text}
    # Чтобы не тащить __RAW_TEXT__ в строку — подставим inline
    code = PREPROCESS_CODE.replace("__RAW_TEXT__", repr(raw_text))
    exec(code, ns)
    return {
        "raw_text": ns["raw_text"],
        "sentences": ns["sentences"],
        "tokens_per_sentence": ns["tokens_per_sentence"],
        "total_tokens": ns["total_tokens"],
        "facts": ns["facts"],
        "mentions": ns["mentions"],
    }


# ── Собственно демка ─────────────────────────────────────────────────────────

def demo_standalone() -> None:
    print("\n=== STANDALONE mode (без живого ядра) ===\n")

    raw_text = load_source_text()
    result = run_standalone(raw_text)

    # Собираем Panel иерархию
    panel = Panel("quest_preprocessing", meta={"case": "quest_order", "mode": "standalone"})
    panel.add_value("raw_text", result["raw_text"],
                    meta={"type": "str", "length": len(result["raw_text"])})
    panel.add_value("sentences", result["sentences"],
                    meta={"type": "list[str]", "count": len(result["sentences"])})
    panel.add_value("facts", result["facts"],
                    meta={"type": "list[str]", "count": len(result["facts"])})

    # Sub-panel: stats
    stats = panel.sub_panel("stats")
    stats.add_value("total_tokens", result["total_tokens"], meta={"type": "int"})
    stats.add_value("tokens_per_sentence", result["tokens_per_sentence"],
                    meta={"type": "list[list[str]]"})

    # Sub-panel: entities
    entities = panel.sub_panel("entities")
    entities.add_value("mentions", result["mentions"], meta={"type": "dict[str, int]"})

    # L0 view
    print("── L0 view ───────────────────────────────────────")
    describe_panel(panel)

    # Демонстрация lazy vs fetched
    print("\n── Материализация (пара выборочных) ──────────")
    print(f"Facts count: {len(panel.get('facts').value)}")
    print(f"First fact:  {panel.get('facts').value[0]}")
    print(f"Mentions:    {entities.get('mentions').value}")

    # LocalStore
    print("\n── LocalStore ────────────────────────────────────")
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalStore(tmpdir, panel.name)
        store.save_panel_meta(panel)
        for oid in panel.list_ids():
            store.save_object_meta(panel.get(oid))
        store.save_blob("run_info", {
            "mode": "standalone",
            "source": str(load_source_text.__name__),
            "counts": {
                "sentences": len(result["sentences"]),
                "facts": len(result["facts"]),
                "total_tokens": result["total_tokens"],
            },
        })
        print(f"Saved to: {tmpdir}/{panel.name}/")
        print(f"  panel.json:      {(Path(tmpdir)/panel.name/'panel.json').exists()}")
        print(f"  objects/:         {len(store.list_stored_ids())} files")
        print(f"  blobs:            {store.list_blobs()}")


def demo_live() -> None:
    print("\n=== LIVE mode (Jupyter kernel) ===\n")

    from jupyter_layer import KernelSession, JupyterScope

    raw_text = load_source_text()

    with KernelSession() as ks:
        scope = JupyterScope(ks)

        # Inject preprocess code into kernel
        code = PREPROCESS_CODE.replace("__RAW_TEXT__", repr(raw_text))
        res = scope.run(code)
        if res["status"] != "ok":
            print(f"Kernel error: {res['error']}")
            return

        # Главная панель мирроит kernel namespace
        panel = Panel("quest_preprocessing", scope=scope,
                      meta={"case": "quest_order", "mode": "live"})
        added = panel.sync_from_scope()
        print(f"Synced {len(added)} objects from kernel namespace")

        # L0 view — всё ещё lazy
        print("\n── L0 view (до материализации) ───────────────────")
        describe_panel(panel)

        # Материализуем только sentences и facts
        sentences = panel.get("sentences").value
        facts = panel.get("facts").value
        total = panel.get("total_tokens").value
        mentions = panel.get("mentions").value

        print("\n── После материализации ──────────────────────────")
        describe_panel(panel)

        print(f"\nSentences: {len(sentences)}")
        print(f"Facts:     {len(facts)}")
        print(f"Total tokens: {total}")
        print(f"Mentions: {mentions}")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if LIVE:
        demo_live()
    else:
        demo_standalone()
        print("\n(Подсказка: добавь --live для запуска на живом Jupyter ядре)")
