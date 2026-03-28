# embed_service.py
"""
Embedding service: Qwen3 text + VL + reranker + ChromaDB.

Models:
  - Qwen3-Embedding-0.6B      (text, 1024d, sentence_transformers)
  - Qwen3-Reranker-0.6B       (text pairs, causal LM yes/no scoring)
  - Qwen3-VL-Embedding-2B-FP8 (vision+text, 2048d, OpenAI API via vLLM)

Usage:
    svc = EmbedService()
    svc.add(["text1", "text2"], ids=["id1", "id2"])
    hits = svc.search("query")
"""

import warnings
from functools import cached_property
from pathlib import Path

import chromadb
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForCausalLM, AutoTokenizer

HF_CACHE = Path(r"C:\Users\vAiry\.cache\huggingface\hub")
CHROMA_PATH = "./chroma_db"

# VL model served via vLLM with OpenAI-compatible API
# If vLLM runs in WSL, replace localhost with WSL IP (check: cat /etc/resolv.conf)
VL_API_BASE = "http://localhost:8000/v1"
VL_MODEL_NAME = "alexliap/Qwen3-VL-Embedding-2B-FP8-DYNAMIC"


class EmbedService:
    """Lazy-load all models on first use."""

    def __init__(self, db_path: str = CHROMA_PATH, verbose: bool = False):
        self.db = chromadb.PersistentClient(path=db_path)
        self.verbose = verbose

    def _log(self, msg: str):
        if self.verbose:
            print(f"  [embed] {msg}")

    # ── text embedder (0.6B) ──

    @cached_property
    def embedder(self):
        self._log("loading Qwen3-Embedding-0.6B...")
        return SentenceTransformer(
            "Qwen/Qwen3-Embedding-0.6B",
            cache_folder=str(HF_CACHE),
        )

    # ── reranker (0.6B, causal LM) ──

    @cached_property
    def _reranker_model(self):
        self._log("loading Qwen3-Reranker-0.6B...")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = AutoModelForCausalLM.from_pretrained(
                "Qwen/Qwen3-Reranker-0.6B",
                cache_dir=str(HF_CACHE),
                trust_remote_code=True,
            ).eval()
        return model

    @cached_property
    def _reranker_tokenizer(self):
        tok = AutoTokenizer.from_pretrained(
            "Qwen/Qwen3-Reranker-0.6B",
            cache_dir=str(HF_CACHE),
            trust_remote_code=True,
            padding_side="left",
        )
        self._yes_id = tok.convert_tokens_to_ids("yes")
        self._no_id = tok.convert_tokens_to_ids("no")
        prefix = '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
        suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
        self._rerank_prefix = tok.encode(prefix, add_special_tokens=False)
        self._rerank_suffix = tok.encode(suffix, add_special_tokens=False)
        self._log(f"reranker ready, yes_id={self._yes_id}, no_id={self._no_id}")
        return tok

    # ── VL client (OpenAI-compatible, requires vLLM serving the model) ──

    @cached_property
    def vl_client(self):
        from openai import OpenAI
        return OpenAI(api_key="EMPTY", base_url=VL_API_BASE)

    # ── encode: text queries (with query prompt) ──

    def encode_query(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.encode(
            texts, prompt_name="query", normalize_embeddings=True
        ).tolist()

    # ── encode: text documents (no prompt) ──

    def encode_docs(self, texts: list[str]) -> list[list[float]]:
        return self.embedder.encode(texts, normalize_embeddings=True).tolist()

    # ── encode: legacy alias ──

    def encode(self, texts: list[str]) -> list[list[float]]:
        return self.encode_docs(texts)

    # ── encode: vision via vLLM OpenAI API ──

    def encode_vision(
        self,
        texts: list[str] | None = None,
        images: list[str] | None = None,
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """Embed text and/or images via VL model (OpenAI API).

        Args:
            texts: plain text inputs
            images: file paths to images (base64-encoded automatically)
            dimensions: matryoshka truncation (client-side), None = full 2048
        """
        import base64

        results = []

        for txt in texts or []:
            resp = self.vl_client.embeddings.create(
                model=VL_MODEL_NAME, input=txt, encoding_format="float",
            )
            results.append(resp.data[0].embedding)

        for img_path in images or []:
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            ext = Path(img_path).suffix.lstrip(".") or "jpeg"
            mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(ext, "jpeg")
            resp = self.vl_client.post(
                "/embeddings",
                body={
                    "messages": [{"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}},
                    ]}],
                    "model": VL_MODEL_NAME,
                    "encoding_format": "float",
                },
                cast_to=object,
            )
            results.append(resp.data[0].embedding)

        # client-side matryoshka: truncate + re-normalize
        if dimensions and dimensions < 2048:
            import numpy as np
            results = [
                (np.array(e[:dimensions]) / np.linalg.norm(e[:dimensions])).tolist()
                for e in results
            ]

        return results

    # ── rerank ──

    def rerank(
        self,
        query: str,
        docs: list[str],
        top_k: int = 5,
        instruction: str = "Given a web search query, retrieve relevant passages that answer the query",
    ) -> list[dict]:
        tok = self._reranker_tokenizer
        model = self._reranker_model
        max_len = 8192

        pairs = [
            f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
            for doc in docs
        ]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            inputs = tok(
                pairs, padding=False, truncation="longest_first",
                return_attention_mask=False,
                max_length=max_len - len(self._rerank_prefix) - len(self._rerank_suffix),
            )
            for i, ids in enumerate(inputs["input_ids"]):
                inputs["input_ids"][i] = self._rerank_prefix + ids + self._rerank_suffix
            inputs = tok.pad(inputs, padding=True, return_tensors="pt", max_length=max_len)
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        with torch.no_grad():
            logits = model(**inputs).logits[:, -1, :]
        true_v = logits[:, self._yes_id]
        false_v = logits[:, self._no_id]
        scores = (
            torch.nn.functional.log_softmax(
                torch.stack([false_v, true_v], dim=1), dim=1
            )[:, 1].exp().tolist()
        )

        ranked = sorted(zip(scores, docs), reverse=True)[:top_k]
        return [{"score": s, "text": t} for s, t in ranked]

    # ── chroma collections ──

    def collection(self, name: str = "knowledge"):
        return self.db.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    # ── add to collection ──

    def add(
        self,
        texts: list[str],
        ids: list[str],
        metadatas: list[dict] | None = None,
        collection: str = "knowledge",
    ):
        col = self.collection(collection)
        col.add(
            ids=ids,
            embeddings=self.encode_docs(texts),
            documents=texts,
            metadatas=metadatas,
        )

    def add_images(
        self,
        images: list[str],
        ids: list[str],
        metadatas: list[dict] | None = None,
        collection: str = "images",
        dimensions: int | None = None,
    ):
        col = self.collection(collection)
        embs = self.encode_vision(images=images, dimensions=dimensions)
        if metadatas is None:
            metadatas = [{"path": str(p)} for p in images]
        col.add(ids=ids, embeddings=embs, metadatas=metadatas)

    # ── search ──

    def search(
        self,
        query: str,
        n: int = 10,
        rerank_top: int | None = 5,
        where: dict | None = None,
        collection: str = "knowledge",
    ) -> list[dict]:
        col = self.collection(collection)
        results = col.query(
            query_embeddings=self.encode_query([query]),
            n_results=n,
            where=where,
        )
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        hits = [
            {"text": d, "meta": m, "dist": dist}
            for d, m, dist in zip(docs, metas, dists)
        ]

        if rerank_top and len(hits) > 1:
            reranked = self.rerank(query, [h["text"] for h in hits], rerank_top)
            text_to_meta = {h["text"]: h["meta"] for h in hits}
            hits = [{**r, "meta": text_to_meta[r["text"]]} for r in reranked]

        return hits

    def search_images(
        self,
        query: str,
        n: int = 10,
        where: dict | None = None,
        collection: str = "images",
        dimensions: int | None = None,
    ) -> list[dict]:
        """Search images by text query (cross-modal via VL model)."""
        col = self.collection(collection)
        results = col.query(
            query_embeddings=self.encode_vision(texts=[query], dimensions=dimensions),
            n_results=n,
            where=where,
        )
        return [
            {"meta": m, "dist": d}
            for m, d in zip(results["metadatas"][0], results["distances"][0])
        ]


# ── quick test ──

if __name__ == "__main__":
    import sys

    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    svc = EmbedService(verbose=verbose)

    print("=== Text embed ===")
    q = svc.encode_query(["What is quantum entanglement?"])
    d = svc.encode_docs(["Quantum entanglement is a phenomenon"])
    import numpy as np
    print(f"  dim={len(q[0])}, cosine={np.dot(q[0], d[0]):.4f}")

    print("\n=== Reranker ===")
    for query, docs in [
        ("What is the capital of China?",
         ["The capital of China is Beijing.",
          "Gravity is a force that attracts two bodies towards each other."]),
        ("quantum physics",
         ["quantum entanglement is a phenomenon",
          "the weather is nice today",
          "Schrodinger's cat thought experiment"]),
    ]:
        print(f"  q: {query}")
        for r in svc.rerank(query, docs):
            print(f"    {r['score']:.4f}  {r['text']}")

    print("\n=== ChromaDB ===")
    svc.add(
        texts=["quantum entanglement", "classical mechanics", "neural networks"],
        ids=["t1", "t2", "t3"],
        metadatas=[{"topic": "physics"}, {"topic": "physics"}, {"topic": "ml"}],
    )
    for h in svc.search("entanglement", rerank_top=3):
        print(f"  {h.get('score', h.get('dist', '?')):.4f}  {h['text']}")

    print("\n=== VL ===")
    try:
        vl = svc.encode_vision(texts=["a red cat"], dimensions=512)
        print(f"  dim={len(vl[0])}")
    except Exception as e:
        print(f"  not available: {e}")

    # cross-restart consistency: save/compare embeddings across vLLM restarts
    if "--save-baseline" in sys.argv:
        print("\n=== Saving VL baseline ===")
        import json, numpy as np
        baseline = {}
        for txt in ["a red cat on a sofa", "quantum entanglement explained"]:
            emb = svc.encode_vision(texts=[txt])
            baseline[txt] = emb[0]
        with open("vl_baseline.json", "w") as f:
            json.dump(baseline, f)
        print(f"  saved {len(baseline)} embeddings to vl_baseline.json")

    if "--check-baseline" in sys.argv:
        print("\n=== Checking VL against baseline ===")
        import json, numpy as np
        with open("vl_baseline.json") as f:
            baseline = json.load(f)
        for txt, old_emb in baseline.items():
            new_emb = svc.encode_vision(texts=[txt])[0]
            old, new = np.array(old_emb), np.array(new_emb)
            cos = np.dot(old, new) / (np.linalg.norm(old) * np.linalg.norm(new))
            l2 = np.linalg.norm(old - new)
            print(f"  \"{txt}\"")
            print(f"    cosine={cos:.8f}  L2={l2:.8f}")
        print("  (cosine < 0.9999 = FP8 dynamic noise across restarts)")

    # within-session consistency test
    if "--consistency" in sys.argv:
        print("\n=== VL consistency (FP8 dynamic noise) ===")
        import numpy as np
        runs = 5
        texts_to_test = ["a red cat on a sofa", "quantum entanglement explained"]
        for txt in texts_to_test:
            embeddings = []
            for i in range(runs):
                emb = svc.encode_vision(texts=[txt])
                embeddings.append(emb[0])
            embeddings = np.array(embeddings)
            # pairwise cosine between all runs
            cosines = []
            for i in range(runs):
                for j in range(i + 1, runs):
                    c = np.dot(embeddings[i], embeddings[j]) / (
                        np.linalg.norm(embeddings[i]) * np.linalg.norm(embeddings[j])
                    )
                    cosines.append(c)
            mean_cos = np.mean(cosines)
            std_cos = np.std(cosines)
            # L2 drift from first run
            drifts = [np.linalg.norm(embeddings[i] - embeddings[0]) for i in range(1, runs)]
            print(f"  \"{txt}\"")
            print(f"    cosine: mean={mean_cos:.6f} std={std_cos:.8f}")
            print(f"    L2 drift from run 0: {['%.6f' % d for d in drifts]}")
            # matryoshka: compare 256d vs 2048d consistency
            emb_full = svc.encode_vision(texts=[txt])
            emb_small = svc.encode_vision(texts=[txt], dimensions=256)
            trunc = np.array(emb_full[0][:256])
            trunc = trunc / np.linalg.norm(trunc)
            cos_trunc = np.dot(trunc, emb_small[0])
            print(f"    matryoshka 256d self-consistency: {cos_trunc:.6f}")

    print("\nDone!")
