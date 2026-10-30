"""LLM client with structured JSON output.

Provider ladder (first configured wins, Ollama is the local last resort):

1. **Google Gemini** — cloud, free tier, OpenAI-compatible. Used when
   ``GEMINI_API_KEY`` is set, so the app gets real AI with nothing to install.
2. **OpenRouter** — cloud fallback, OpenAI-compatible (free models available).
3. **Ollama** — fully local/offline (``OLLAMA_BASE_URL``), needs no key.

The order is configurable via ``LLM_PROVIDER_ORDER``.

Returns parsed JSON (dict) or raises.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
_DEFAULT_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.1-8b-instruct:free"


def _gemini_provider(model: str) -> tuple[str, str, str] | None:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    base = os.getenv("GEMINI_BASE_URL", _DEFAULT_GEMINI_BASE).rstrip("/")
    chosen = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"
    return base, key, chosen


def _openrouter_provider(model: str) -> tuple[str, str, str] | None:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None
    base = os.getenv("OPENROUTER_BASE_URL", _DEFAULT_OPENROUTER_BASE).rstrip("/")
    chosen = os.getenv("OPENROUTER_MODEL", _DEFAULT_OPENROUTER_MODEL).strip()
    return base, key, chosen


def _ollama_provider(model: str) -> tuple[str, str, str] | None:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    return f"{base}/v1", "ollama", model


_PROVIDERS = {
    "gemini": _gemini_provider,
    "openrouter": _openrouter_provider,
    "ollama": _ollama_provider,
}


def _provider_chain(model: str) -> list[tuple[str, str, str]]:
    """Ordered ``(base_url, api_key, model_name)`` candidates to try."""
    order = os.getenv("LLM_PROVIDER_ORDER", "gemini,openrouter,ollama")
    chain: list[tuple[str, str, str]] = []
    for name in (part.strip().lower() for part in order.split(",")):
        if not name:
            continue
        builder = _PROVIDERS.get(name)
        if builder is None:
            continue
        cfg = builder(model)
        if cfg:
            chain.append(cfg)
    return chain


def _chat_completion(
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 4096,
    timeout: float = 180.0,
) -> str:
    """Try each configured provider in order. Returns raw text."""
    providers = _provider_chain(model)
    if not providers:
        raise RuntimeError("No LLM provider configured (set GEMINI_API_KEY)")

    errors: list[str] = []
    for (base_url, api_key, model_name) in providers:
        try:
            headers = {"Content-Type": "application/json"}
            if api_key and api_key != "ollama":
                headers["Authorization"] = f"Bearer {api_key}"
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if content:
                return str(content)
            errors.append(f"{model_name}: empty content")
        except Exception as exc:
            logger.warning("LLM provider %s failed: %s", model_name, exc)
            errors.append(f"{model_name}: {exc}")

    raise RuntimeError("All LLM providers failed -> " + " | ".join(errors))


def _scan_balanced(text: str, start: int, opener: str, closer: str) -> str | None:
    """Return the balanced {...} or [...] substring beginning at `start`.

    Handles quoted strings and escaped characters so braces inside strings
    do not terminate the scan early.
    """
    depth = 0
    in_str = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_json(text: str) -> dict[str, Any]:
    """Parse JSON from LLM output, tolerating code fences and surrounding prose."""
    text = text.strip()
    # Strip ```json ... ``` fences
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            return parsed
    except json.JSONDecodeError:
        pass

    # Find the first balanced JSON object (or array) in the text
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        candidate = _scan_balanced(text, start, opener, closer)
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed

    raise ValueError(f"Could not parse JSON from LLM output: {text[:400]}")


def structured_completion(
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
) -> dict[str, Any]:
    """Request JSON from the model and parse it."""
    model = model or os.getenv("DEFAULT_CHAT_MODEL", "llama3.1:8b")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    raw = _chat_completion(model, messages, temperature=temperature, max_tokens=max_tokens)
    return _extract_json(raw)


def chat_completion(
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Free-form text completion (used by the Dev Studio assistant).

    Same provider ladder as :func:`structured_completion` but returns the raw
    answer instead of parsing JSON.
    """
    model = model or os.getenv("DEFAULT_CHAT_MODEL", "llama3.1:8b")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return _chat_completion(model, messages, temperature=temperature, max_tokens=max_tokens)


def _gemini_embeddings(texts: list[str]) -> list[list[float]] | None:
    """Embed via Gemini's OpenAI-compatible endpoint.

    Returns ``None`` when Gemini is unset *or* the call fails, so the caller can
    try the next backend instead of aborting.
    """
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    base = os.getenv("GEMINI_BASE_URL", _DEFAULT_GEMINI_BASE).rstrip("/")
    model = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(
                f"{base}/embeddings",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model, "input": list(texts)},
            )
        resp.raise_for_status()
        rows = resp.json()["data"]
        # OpenAI returns data rows possibly out of order -> sort by index.
        rows = sorted(rows, key=lambda r: r.get("index", 0))
        vectors = [[float(x) for x in row["embedding"]] for row in rows]
        if len(vectors) != len(texts) or not all(vectors):
            return None
        return vectors
    except Exception as exc:  # noqa: BLE001 - fall through to the next backend
        logger.info("Gemini embeddings unavailable (%s); trying next backend", exc)
        return None


def _ollama_embeddings(texts: list[str]) -> list[list[float]]:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    vectors: list[list[float]] = []
    with httpx.Client(timeout=60.0) as client:
        for text in texts:
            resp = client.post(f"{base}/api/embeddings", json={"model": model, "prompt": text})
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"])
    return vectors


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with the best configured backend (Gemini, then Ollama).

    Raises if no backend is reachable — callers (Project Memory) fall back to a
    deterministic offline hashing embedding.
    """
    if not texts:
        return []

    gemini = _gemini_embeddings(texts)
    if gemini is not None:
        return gemini

    return _ollama_embeddings(texts)
