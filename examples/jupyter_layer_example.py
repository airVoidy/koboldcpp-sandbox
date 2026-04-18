"""
jupyter_layer usage example.

Демонстрирует два режима:
  1. Standalone Panel — без ядра, просто контейнер (всегда работает).
  2. Kernel-backed Panel — требует jupyter_client + ipykernel.

Запуск:
  python examples/jupyter_layer_example.py
  python examples/jupyter_layer_example.py --live   # с живым ядром
"""

import sys
import json
import tempfile
from pathlib import Path

LIVE = "--live" in sys.argv


# ════════════════════════════════════════════════════════════════════════════
# Часть 1: Standalone Panel (без ядра)
# ════════════════════════════════════════════════════════════════════════════

print("\n=== Part 1: Standalone Panel ===\n")

from jupyter_layer import Panel, JupyterObject, LocalStore

# Создать панель — контейнер для артефактов препроцессинга
preprocessing = Panel("preprocessing", meta={"version": "alpha"})

# Добавить объекты вручную (как если бы мы загрузили их из файла)
preprocessing.add_value("raw_sentences", ["The cat sat.", "The dog ran."])
preprocessing.add_value("token_counts", [4, 4])

# L0: только IDs
print("L0 IDs:", preprocessing.list_ids())
# → ['raw_sentences', 'token_counts']

# Явная материализация одного объекта
sents = preprocessing.get("raw_sentences").value
print("Sentences:", sents)

# Иерархия через sub_panel
embed_panel = preprocessing.sub_panel("embeddings")
embed_panel.add_value("embed_v0", [[0.1, 0.2], [0.3, 0.4]])

print("Sub-panels:", preprocessing.list_panel_ids())
print("Embed IDs:", embed_panel.list_ids())

# Lazy object с кастомным fetcher
def expensive_computation():
    print("  [computing...]")
    return sum(range(1000))

lazy_obj = JupyterObject(id="big_sum", _fetch=expensive_computation)
preprocessing.add(lazy_obj)

print("\nBefore .value access — no computation yet")
print("big_sum fetched:", lazy_obj._fetched)
print("big_sum value:", lazy_obj.value)  # вызов fetcher
print("big_sum fetched now:", lazy_obj._fetched)
print("big_sum value again:", lazy_obj.value)  # кэш, не перевычисляет

# LocalStore — сохранить метадату панели
with tempfile.TemporaryDirectory() as tmpdir:
    store = LocalStore(tmpdir, "preprocessing")
    store.save_panel_meta(preprocessing)

    for obj_id in preprocessing.list_ids():
        obj = preprocessing.get(obj_id)
        store.save_object_meta(obj)

    store.save_blob("run_info", {"source": "example.py", "rows": 2})

    # Загрузить
    meta = store.load_panel_meta()
    print("\nStored panel meta:", json.dumps(meta, indent=2))

    blobs = store.list_blobs()
    print("Stored blobs:", blobs)


# ════════════════════════════════════════════════════════════════════════════
# Часть 2: Kernel-backed Panel (нужен jupyter_client)
# ════════════════════════════════════════════════════════════════════════════

if not LIVE:
    print("\n=== Part 2: Kernel-backed (skipped — pass --live to run) ===")
    sys.exit(0)

print("\n=== Part 2: Kernel-backed Panel ===\n")

from jupyter_layer import KernelSession, JupyterScope

with KernelSession() as ks:
    scope = JupyterScope(ks)

    # Выполнить препроцессинг прямо в ядре
    scope.run("sentences = ['The cat sat.', 'The dog ran.']")
    scope.run("lengths = [len(s.split()) for s in sentences]")
    scope.run("vocab = list(set(w for s in sentences for w in s.lower().split()))")

    # L0: только имена
    print("Kernel IDs (L0):", scope.list_ids())
    print("Typed  (L0):", scope.list_typed())

    # Panel над ядром
    panel = Panel("kernel_preprocessing", scope=scope)
    added = panel.sync_from_scope()
    print(f"\nSynced {len(added)} objects from kernel:")
    for oid in panel.list_ids():
        obj = panel.get(oid)
        print(f"  [{oid}] — lazy={not obj._fetched}")

    # Материализовать только vocab
    vocab = panel.get("vocab").value
    print(f"\nvocab fetched: {sorted(vocab)}")

    # Добавить новую переменную в ядро, синхронизировать панель
    scope.run("word_count = len(vocab)")
    new_ids = panel.sync_from_scope()
    print(f"\nAfter re-sync, new IDs: {new_ids}")
    print("word_count:", panel.get("word_count").value)

print("\nDone.")
