"""LLM client with structured JSON output.

Providers:
- Ollama (primary, free/local) via the OpenAI-compatible endpoint
- OpenRouter (fallback) via OpenAI-compatible endpoint

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


def _ollama_config() -> tuple[str, str]:
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    return f"{base}/v1", "ollama"


def _openrouter_config() -> tuple[str, str]:
    base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    return base, os.getenv("OPENROUTER_API_KEY", "")


def _chat_completion(
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 4096,
    timeout: float = 180.0,
) -> str:
    """Call Ollama first, then fall back to OpenRouter. Returns raw text."""
    providers = [_ollama_config()]
    if os.getenv("OPENROUTER_API_KEY"):
        providers.append(_openrouter_config())

    errors: list[str] = []
    for (base_url, api_key) in providers:
        try:
            headers = {"Content-Type": "application/json"}
            if api_key and api_key != "ollama":
                headers["Authorization"] = f"Bearer {api_key}"
            payload = {
                "model": model,
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
            errors.append(f"{base_url}: empty content")
        except Exception as exc:
            logger.warning("LLM provider %s failed: %s", base_url, exc)
            errors.append(f"{base_url}: {exc}")

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
    model = model or os.getenv("DEFAULT_CHAT_MODEL", "llama-3.1:8b")
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

    Same provider ladder as :func:`structured_completion` (Ollama first, then
    OpenRouter) but returns the raw answer instead of parsing JSON.
    """
    model = model or os.getenv("DEFAULT_CHAT_MODEL", "llama-3.1:8b")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return _chat_completion(model, messages, temperature=temperature, max_tokens=max_tokens)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts using Ollama's embeddings endpoint."""
    base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    vectors: list[list[float]] = []
    with httpx.Client(timeout=60.0) as client:
        for text in texts:
            resp = client.post(f"{base}/api/embeddings", json={"model": model, "prompt": text})
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"])
    return vectors
