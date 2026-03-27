"""
Shared LLM client for KoboldCPP tools.

Supports two modes:
  - Direct: hit KoboldCPP, strip <think> blocks in Python
  - Proxy:  hit kobold_nothink_proxy (injects empty think + strips output)

Usage:
    from llm_client import LLM, GEN_YES_NO, GEN_SHORT, GEN_MEDIUM, GEN_JSON, GEN_RULES

    llm = LLM()                          # uses defaults
    llm = LLM(proxy_9b="http://localhost:5056", proxy_27b="http://localhost:5055")

    text = llm.ask_9b("system msg", "user msg", GEN_SHORT)
    text = llm.ask_27b("system msg", "user msg", GEN_MEDIUM)
    info = llm.model_info("9b")

Environment variables (override defaults):
    LLM_9B_URL    = http://192.168.1.14:5001
    LLM_27B_URL   = http://192.168.1.15:5050
    LLM_9B_PROXY  = (empty = direct mode)
    LLM_27B_PROXY = (empty = direct mode)
"""

import json
import os
import re
import time

import requests

# ── Think-block stripping ────────────────────────────────────────────

THINK_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>\\s*", re.DOTALL)


def strip_thinking(text: str) -> str:
    """Remove all <thinking>…</thinking> and <think>…</think> blocks."""
    return THINK_RE.sub("", text).strip()


# ── ChatML ───────────────────────────────────────────────────────────


def chatml(system: str, user: str) -> str:
    """Build ChatML instruct prompt for Qwen 3.5."""
    return (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{user}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )


# ── Gen param presets ────────────────────────────────────────────────

_BASE_PARAMS = {
    "max_context_length": 2048,
    "top_a": 0.0,
    "typical": 1.0,
    "tfs": 1.0,
    "rep_pen": 1.0,
    "rep_pen_range": 256,
    "rep_pen_slope": 1.0,
    "min_p": 0.0,
    "mirostat": 0,
    "mirostat_tau": 5.0,
    "mirostat_eta": 0.1,
    "sampler_order": [6, 0, 1, 3, 4, 2, 5],
    "seed": -1,
    "stop_sequence": ["<|im_end|>", "<|endoftext|>"],
    "trim_stop": True,
    "memory": "",
    "use_story": False,
    "use_memory": False,
    "use_authors_note": False,
    "use_world_info": False,
}

# Yes/No probes: very short, very low temp
GEN_YES_NO = {
    **_BASE_PARAMS,
    "max_length": 20,
    "temperature": 0.1,
    "top_p": 0.9,
    "top_k": 20,
}

# Short answers (reformulation, single sentence)
GEN_SHORT = {
    **_BASE_PARAMS,
    "max_length": 80,
    "temperature": 0.3,
    "top_p": 0.9,
    "top_k": 20,
}

# Medium answers (discovery, validation)
GEN_MEDIUM = {
    **_BASE_PARAMS,
    "max_length": 200,
    "temperature": 0.4,
    "top_p": 0.9,
    "top_k": 20,
}

# JSON extraction
GEN_JSON = {
    **_BASE_PARAMS,
    "max_length": 500,
    "temperature": 0.2,
    "top_p": 0.9,
    "top_k": 20,
    "stop_sequence": ["<|im_end|>", "<|endoftext|>", "```\n\n"],
}

# Rule generation / validation (longer, precise)
GEN_RULES = {
    **_BASE_PARAMS,
    "max_length": 800,
    "temperature": 0.15,
    "top_p": 0.9,
    "top_k": 20,
}

# Compare models (more creative)
GEN_COMPARE = {
    **_BASE_PARAMS,
    "max_length": 200,
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 40,
    "rep_pen": 1.1,
}

# Long validation
GEN_VALIDATE = {
    **_BASE_PARAMS,
    "max_length": 500,
    "temperature": 0.4,
    "top_p": 0.9,
    "top_k": 20,
}


# ── LLM client ──────────────────────────────────────────────────────


class LLM:
    """
    Unified client for 9B prober + 27B validator.

    If proxy URLs are set, requests go through kobold_nothink_proxy
    (which injects empty think block + strips output).
    Otherwise, hits KoboldCPP directly and strips think blocks in Python.
    """

    def __init__(
        self,
        url_9b: str = None,
        url_27b: str = None,
        proxy_9b: str = None,
        proxy_27b: str = None,
    ):
        self.proxy_9b = (
            proxy_9b or os.environ.get("LLM_9B_URL", "http://192.168.1.14:5001")
        ).rstrip("/")
        self.proxy_27b = (
            proxy_27b or os.environ.get("LLM_27B_URL", "http://192.168.1.15:5050")
        ).rstrip("/")
        self.url_9b = (url_9b or os.environ.get("LLM_9B_PROXY", "")).rstrip("/") or None
        self.url_27b = (url_27b or os.environ.get("LLM_27B_PROXY", "")).rstrip(
            "/"
        ) or None

    def _effective_url(self, which: str) -> str:
        """Return proxy URL if available, otherwise direct URL."""
        if which == "9b":
            return self.proxy_9b or self.url_9b
        else:
            return self.proxy_27b or self.url_27b

    def _is_proxied(self, which: str) -> bool:
        if which == "9b":
            return self.proxy_9b is not None
        return self.proxy_27b is not None

    def generate_raw(
        self, which: str, prompt: str, params: dict, timeout: int = 120
    ) -> dict:
        """
        Low-level generate. Returns {"text": ..., "elapsed_s": ..., "status": ..., "raw": ...}
        """
        url = self._effective_url(which)
        payload = {**params, "prompt": prompt}
        t0 = time.perf_counter()
        try:
            r = requests.post(f"{url}/api/v1/generate", json=payload, timeout=timeout)
            elapsed = time.perf_counter() - t0
            data = r.json()
            text = data["results"][0]["text"] if "results" in data else ""
            # Strip thinking if direct mode (proxy already strips)
            if not self._is_proxied(which):
                text = strip_thinking(text)
            return {
                "text": text.strip(),
                "elapsed_s": round(elapsed, 3),
                "status": r.status_code,
                "raw": data,
            }
        except Exception as e:
            elapsed = time.perf_counter() - t0
            return {
                "text": "",
                "elapsed_s": round(elapsed, 3),
                "status": -1,
                "error": str(e),
            }

    def generate(
        self, which: str, prompt: str, params: dict, timeout: int = 120
    ) -> str:
        """Generate text, return just the string."""
        return self.generate_raw(which, prompt, params, timeout)["text"]

    def ask(
        self, which: str, system: str, user: str, params: dict, timeout: int = 120
    ) -> str:
        """Build ChatML prompt + generate. Returns text."""
        prompt = chatml(system, user)
        return self.generate(which, prompt, params, timeout)

    def ask_9b(
        self, system: str, user: str, params: dict = None, timeout: int = 60
    ) -> str:
        return self.ask("9b", system, user, params or GEN_SHORT, timeout)

    def ask_27b(
        self, system: str, user: str, params: dict = None, timeout: int = 120
    ) -> str:
        return self.ask("27b", system, user, params or GEN_MEDIUM, timeout)

    def model_info(self, which: str) -> dict:
        """Fetch model name from endpoint."""
        url = self._effective_url(which)
        try:
            r = requests.get(f"{url}/api/v1/model", timeout=10)
            return r.json()
        except Exception as e:
            return {"error": str(e)}

    def status(self) -> str:
        """Print connection status for both models."""
        lines = []
        for label, which in [("9B", "9b"), ("27B", "27b")]:
            url = self._effective_url(which)
            mode = "proxy" if self._is_proxied(which) else "direct"
            info = self.model_info(which)
            model = info.get("result", info.get("error", "?"))
            lines.append(f"  {label}: {url} ({mode}) → {model}")
        return "\n".join(lines)


# ── JSON extraction helper ───────────────────────────────────────────


def extract_json(text: str):
    """Try to extract JSON from LLM output (handles ```json blocks)."""
    m = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except Exception:
        for sc, ec in [("{", "}"), ("[", "]")]:
            i0, i1 = text.find(sc), text.rfind(ec)
            if i0 != -1 and i1 != -1:
                try:
                    return json.loads(text[i0 : i1 + 1])
                except Exception:
                    pass
    return None


def is_yes(text: str) -> bool:
    """Parse yes/no answer."""
    t = text.lower().strip().rstrip(".!,")
    return t.startswith("yes") or t.startswith("да")
