"""Unit tests for the LLM provider ladder and cloud embedding selection.

Cloud-first behaviour: Google Gemini (OpenAI-compatible) is preferred when
``GEMINI_API_KEY`` is set, OpenRouter is the cloud fallback, and Ollama stays
available as the local/offline last resort.

Run from apps/api:  python tests/test_llm_providers.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    tempfile.gettempdir(), f"llmprov_{uuid.uuid4().hex}.db"
).replace(os.sep, "/")

from app.services import llm  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Records every POST and replays scripted responses keyed by URL."""

    calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    responder = None  # type: ignore[assignment]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def post(self, url: str, headers: dict | None = None, json: dict | None = None) -> _FakeResponse:
        _FakeClient.calls.append((url, headers or {}, json or {}))
        assert _FakeClient.responder is not None
        return _FakeClient.responder(url, json or {})


def _reset_env() -> None:
    for key in (
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "LLM_PROVIDER_ORDER",
        "GEMINI_MODEL",
        "OPENROUTER_MODEL",
        "OLLAMA_BASE_URL",
    ):
        os.environ.pop(key, None)


def run() -> int:
    original_client = llm.httpx.Client
    llm.httpx.Client = _FakeClient  # type: ignore[assignment]
    try:
        # --- provider chain ordering --------------------------------------
        _reset_env()
        os.environ["GEMINI_API_KEY"] = "g-key"
        chain = llm._provider_chain("llama3.1:8b")
        check("chain: gemini first when key set", chain[0][0].startswith("https://generativelanguage"), str(chain[0]))
        check("chain: gemini uses its own model", chain[0][2] == "gemini-2.0-flash", chain[0][2])
        check("chain: ollama retained as last resort", chain[-1][1] == "ollama", str(chain[-1]))

        _reset_env()
        chain = llm._provider_chain("llama3.1:8b")
        check("chain: ollama only without keys", len(chain) == 1 and chain[0][1] == "ollama", str(chain))
        check("chain: ollama keeps the requested tag", chain[0][2] == "llama3.1:8b", chain[0][2])

        _reset_env()
        os.environ["OPENROUTER_API_KEY"] = "or-key"
        os.environ["LLM_PROVIDER_ORDER"] = "openrouter,gemini,ollama"
        chain = llm._provider_chain("qwen2.5-coder:7b")
        check("chain: openrouter first when ordered", chain[0][0].startswith("https://openrouter"), str(chain[0]))
        check("chain: openrouter default model", "free" in chain[0][2], chain[0][2])
        check("chain: gemini skipped without key", all("generativelanguage" not in c[0] for c in chain), str(chain))

        # --- _chat_completion tries providers in order ---------------------
        _reset_env()
        os.environ["GEMINI_API_KEY"] = "g-key"
        _FakeClient.calls = []

        def first_ok(url: str, payload: dict) -> _FakeResponse:
            return _FakeResponse({"choices": [{"message": {"content": "hello"}}]})

        _FakeClient.responder = first_ok
        text = llm.chat_completion("sys", "user")
        check("chat: returns first provider content", text == "hello", text)
        check("chat: called gemini endpoint", _FakeClient.calls and "generativelanguage" in _FakeClient.calls[0][0], _FakeClient.calls[0][0] if _FakeClient.calls else "")
        check("chat: sent bearer auth", _FakeClient.calls[0][1].get("Authorization") == "Bearer g-key", str(_FakeClient.calls[0][1]))
        check("chat: used gemini model in payload", _FakeClient.calls[0][2].get("model") == "gemini-2.0-flash", str(_FakeClient.calls[0][2].get("model")))

        # Gemini fails -> OpenRouter succeeds
        _reset_env()
        os.environ["GEMINI_API_KEY"] = "g-key"
        os.environ["OPENROUTER_API_KEY"] = "or-key"
        _FakeClient.calls = []

        def gemini_down(url: str, payload: dict) -> _FakeResponse:
            if "generativelanguage" in url:
                return _FakeResponse({}, status=500)
            return _FakeResponse({"choices": [{"message": {"content": "from-openrouter"}}]})

        _FakeClient.responder = gemini_down
        text = llm.chat_completion("sys", "user")
        check("chat: falls back gemini -> openrouter", text == "from-openrouter", text)
        check("chat: tried two providers", len(_FakeClient.calls) == 2, f"n={len(_FakeClient.calls)}")

        # All providers fail -> RuntimeError
        _reset_env()
        os.environ["GEMINI_API_KEY"] = "g-key"

        def all_down(url: str, payload: dict) -> _FakeResponse:
            return _FakeResponse({}, status=502)

        _FakeClient.responder = all_down
        raised = False
        try:
            llm.chat_completion("sys", "user")
        except RuntimeError:
            raised = True
        check("chat: raises when every provider fails", raised)

        # structured_completion parses JSON from the provider answer
        _reset_env()
        os.environ["GEMINI_API_KEY"] = "g-key"

        def json_ok(url: str, payload: dict) -> _FakeResponse:
            return _FakeResponse({"choices": [{"message": {"content": 'sure {"summary": "ok"}'}}]})

        _FakeClient.responder = json_ok
        parsed = llm.structured_completion("sys", "user")
        check("structured: parses JSON out of prose", parsed == {"summary": "ok"}, str(parsed))

        # --- embeddings: gemini preferred, ollama fallback -----------------
        _reset_env()
        os.environ["GEMINI_API_KEY"] = "g-key"
        _FakeClient.calls = []

        def embed_ok(url: str, payload: dict) -> _FakeResponse:
            n = len(payload.get("input", []))
            return _FakeResponse({"data": [{"index": i, "embedding": [0.1, 0.2]} for i in range(n)]})

        _FakeClient.responder = embed_ok
        vecs = llm.embed(["a", "b"])
        check("embed: gemini returns one vector per input", len(vecs) == 2, f"n={len(vecs)}")
        check("embed: hit the embeddings endpoint", _FakeClient.calls and _FakeClient.calls[0][0].endswith("/embeddings"), _FakeClient.calls[0][0] if _FakeClient.calls else "")

        # Gemini embed fails -> ollama endpoint used
        _reset_env()
        os.environ["GEMINI_API_KEY"] = "g-key"
        os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
        _FakeClient.calls = []

        def embed_gemini_down(url: str, payload: dict) -> _FakeResponse:
            if "generativelanguage" in url:
                return _FakeResponse({}, status=500)
            return _FakeResponse({"embedding": [0.3, 0.4]})

        _FakeClient.responder = embed_gemini_down
        vecs = llm.embed(["a"])
        check("embed: falls back to ollama after gemini error", vecs == [[0.3, 0.4]], str(vecs))
        check("embed: tried gemini then ollama", len(_FakeClient.calls) == 2 and _FakeClient.calls[1][0].endswith("/api/embeddings"), f"n={len(_FakeClient.calls)}")

        check("embed: empty input short-circuits", llm.embed([]) == [], "")
    finally:
        llm.httpx.Client = original_client  # type: ignore[assignment]
        _reset_env()

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
