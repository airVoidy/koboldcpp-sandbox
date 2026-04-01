"""
Bench: sequential vs parallel LLM + embedding on same GPU.
Measures how much they interfere with each other.
"""

import time
import asyncio
import aiohttp
import sys

# ── config ──
KOBOLD_URL = "http://localhost:5001"  # 9B Qwen on KoboldCPP
VLLM_URL = "http://localhost:8000"    # VL embed on vLLM

LLM_PROMPT = "Write a detailed essay about the history of quantum mechanics, from Planck's discovery through the Copenhagen interpretation, EPR paradox, Bell's theorem, and modern quantum computing. Include key experiments and their significance."
EMBED_TEXTS = [
    "Quantum entanglement is a phenomenon in quantum mechanics.",
    "The weather is nice today and birds are singing.",
    "Neural networks are computational models inspired by the brain.",
    "The capital of France is Paris, a city known for the Eiffel Tower.",
    "Machine learning algorithms can detect patterns in large datasets.",
    "Photosynthesis converts sunlight into chemical energy in plants.",
    "The Roman Empire lasted for over a thousand years across Europe.",
    "Deep learning uses multiple layers to progressively extract features.",
    "Mozart composed his first symphony at the age of eight.",
    "Blockchain technology enables decentralized digital transactions.",
] * 10  # 100 texts


async def llm_generate(session):
    """Call KoboldCPP generation."""
    t0 = time.perf_counter()
    payload = {
        "prompt": LLM_PROMPT,
        "max_length": 500,
        "temperature": 0.7,
    }
    async with session.post(f"{KOBOLD_URL}/api/v1/generate", json=payload) as resp:
        result = await resp.json()
    elapsed = time.perf_counter() - t0
    tokens = len(result["results"][0]["text"].split())
    return {"task": "LLM", "time": elapsed, "tokens": tokens}


async def embed_batch(session):
    """Call vLLM embedding endpoint."""
    t0 = time.perf_counter()
    payload = {
        "model": "alexliap/Qwen3-VL-Embedding-2B-FP8-DYNAMIC",
        "input": EMBED_TEXTS,
        "encoding_format": "float",
    }
    async with session.post(f"{VLLM_URL}/v1/embeddings", json=payload) as resp:
        result = await resp.json()
    elapsed = time.perf_counter() - t0
    count = len(result["data"])
    return {"task": "Embed", "time": elapsed, "count": count}


async def run_sequential():
    """Run LLM then embed, measure total."""
    async with aiohttp.ClientSession() as session:
        t0 = time.perf_counter()
        llm = await llm_generate(session)
        emb = await embed_batch(session)
        total = time.perf_counter() - t0
    return llm, emb, total


async def run_parallel():
    """Run LLM and embed simultaneously."""
    async with aiohttp.ClientSession() as session:
        t0 = time.perf_counter()
        llm, emb = await asyncio.gather(
            llm_generate(session),
            embed_batch(session),
        )
        total = time.perf_counter() - t0
    return llm, emb, total


async def run_llm_only():
    """LLM generate only, no embed."""
    async with aiohttp.ClientSession() as session:
        return await llm_generate(session)


async def run_embed_only():
    """Embed only, no LLM."""
    async with aiohttp.ClientSession() as session:
        return await embed_batch(session)


async def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    # ── isolated baselines ──
    print(f"=== LLM only x{rounds} ===")
    llm_times = []
    for i in range(rounds):
        r = await run_llm_only()
        llm_times.append(r["time"])
        print(f"  [{i+1}] {r['time']:.3f}s ({r['tokens']}tok)")

    print(f"\n=== Embed only x{rounds} ===")
    emb_times = []
    for i in range(rounds):
        r = await run_embed_only()
        emb_times.append(r["time"])
        print(f"  [{i+1}] {r['time']:.3f}s ({r['count']}texts)")

    # ── sequential ──
    print(f"\n=== Sequential (LLM → Embed) x{rounds} ===")
    seq_totals = []
    for i in range(rounds):
        llm, emb, total = await run_sequential()
        seq_totals.append(total)
        print(f"  [{i+1}] LLM={llm['time']:.3f}s ({llm['tokens']}tok)  Embed={emb['time']:.3f}s ({emb['count']}texts)  Total={total:.3f}s")

    # ── parallel ──
    print(f"\n=== Parallel (LLM + Embed) x{rounds} ===")
    par_llm_times = []
    par_emb_times = []
    par_totals = []
    for i in range(rounds):
        llm, emb, total = await run_parallel()
        par_llm_times.append(llm["time"])
        par_emb_times.append(emb["time"])
        par_totals.append(total)
        print(f"  [{i+1}] LLM={llm['time']:.3f}s ({llm['tokens']}tok)  Embed={emb['time']:.3f}s ({emb['count']}texts)  Total={total:.3f}s")

    # ── summary ──
    llm_avg = sum(llm_times) / len(llm_times)
    emb_avg = sum(emb_times) / len(emb_times)
    seq_avg = sum(seq_totals) / len(seq_totals)
    par_avg = sum(par_totals) / len(par_totals)
    par_llm_avg = sum(par_llm_times) / len(par_llm_times)
    par_emb_avg = sum(par_emb_times) / len(par_emb_times)

    print(f"\n=== Summary ===")
    print(f"  LLM alone:        {llm_avg:.3f}s")
    print(f"  Embed alone:      {emb_avg:.3f}s")
    print(f"  Sequential total: {seq_avg:.3f}s  (sum of both)")
    print(f"  Parallel total:   {par_avg:.3f}s")
    print(f"  Speedup:          {seq_avg / par_avg:.2f}x")
    print(f"")
    print(f"  LLM slowdown in parallel:   {par_llm_avg - llm_avg:+.3f}s ({(par_llm_avg / llm_avg - 1) * 100:+.1f}%)")
    print(f"  Embed slowdown in parallel: {par_emb_avg - emb_avg:+.3f}s ({(par_emb_avg / emb_avg - 1) * 100:+.1f}%)")
    print(f"  Embed 'cost' in parallel:   {par_avg - llm_avg:.3f}s  (vs {emb_avg:.3f}s alone)")


if __name__ == "__main__":
    asyncio.run(main())
