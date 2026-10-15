"""Unit tests for LLM output parsing and meeting intelligence normalization.

Run from apps/api:  python tests/test_normalize.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(
    tempfile.gettempdir(), f"norm_{uuid.uuid4().hex}.db"
).replace(os.sep, "/")

from app.services.llm import _extract_json  # noqa: E402
from app.services.meeting_summary import _normalize, _clean_date  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


def run() -> int:
    # --- _extract_json robustness -----------------------------------------
    plain = '{"a": 1}'
    check("plain json", _extract_json(plain) == {"a": 1}, str(_extract_json(plain)))

    fenced = "```json\n{\"a\": 2}\n```"
    check("fenced json", _extract_json(fenced) == {"a": 2}, str(_extract_json(fenced)))

    fenced_no_lang = "```\n{\"a\": 3}\n```"
    check("fence without lang", _extract_json(fenced_no_lang) == {"a": 3}, "")

    prose = 'Sure! Here is the JSON you asked for:\n{"a": 4}\nHope that helps.'
    check("json inside prose", _extract_json(prose) == {"a": 4}, str(_extract_json(prose)))

    trailing = '{"a": 5} and some trailing text {"b": 6}'
    try:
        got = _extract_json(trailing)
        check("nested braces tolerated", isinstance(got, dict), str(got))
    except ValueError:
        check("nested braces tolerated", False, "raised ValueError")

    try:
        _extract_json("I could not do that.")
        check("garbage raises", False, "no exception")
    except ValueError:
        check("garbage raises", True, "")

    # --- _clean_date --------------------------------------------------------
    check("iso date", _clean_date("2026-10-17") == "2026-10-17", str(_clean_date("2026-10-17")))
    check("dd-mm-yyyy", _clean_date("17-10-2026") == "2026-10-17", str(_clean_date("17-10-2026")))
    check("slash date", _clean_date("17/10/2026") == "2026-10-17", str(_clean_date("17/10/2026")))
    check("iso datetime prefix", _clean_date("2026-10-17T10:00:00") == "2026-10-17", str(_clean_date("2026-10-17T10:00:00")))
    check("prose date -> null", _clean_date("by Friday") is None, str(_clean_date("by Friday")))
    check("none -> null", _clean_date(None) is None, "")
    check("non-str -> null", _clean_date(12345) is None, str(_clean_date(12345)))

    # --- _normalize ---------------------------------------------------------
    raw = {
        "summary": "  Ekdam sahi summary.  ",
        "key_points": ["A", 123, "  B  ", "", None],
        "decisions": [
            {"title": "Ship it", "impact": "BOGUS", "description": None, "rationale": "  "},
            {"title": "   "},                       # blank -> dropped
            "not-a-dict",                            # bad type -> dropped
            {"title": "Second", "impact": "low", "impact_x": "y"},
        ],
        "action_items": [
            {"title": "Do X", "priority": "BOGUS", "estimated_hours": "abc", "due_date": "2026-1-5"},
            {"title": "Do Y", "priority": "HIGH", "estimated_hours": 3},
            {},                                     # no title -> dropped
        ],
        "risks": "not a list",
        "unanswered_questions": None,
        "next_steps": ["step"],
    }
    out = _normalize(raw)

    check("summary trimmed", out["summary"] == "Ekdam sahi summary.", out["summary"])
    check("key_points cleaned", out["key_points"] == ["A", "123", "B"], str(out["key_points"]))
    check("risks non-list -> []", out["risks"] == [], str(out["risks"]))
    check("unanswered None -> []", out["unanswered_questions"] == [], str(out["unanswered_questions"]))
    check("next_steps kept", out["next_steps"] == ["step"], str(out["next_steps"]))

    check("bad decisions dropped", len(out["decisions"]) == 2, f"count={len(out['decisions'])}")
    check("impact coerced to medium", out["decisions"][0]["impact"] == "medium", out["decisions"][0]["impact"])
    check("impact low preserved", out["decisions"][1]["impact"] == "low", out["decisions"][1]["impact"])
    check("blank rationale -> None", out["decisions"][0]["rationale"] is None, str(out["decisions"][0]["rationale"]))

    check("blank action dropped", len(out["action_items"]) == 2, f"count={len(out['action_items'])}")
    check("priority coerced", out["action_items"][0]["priority"] == "medium", out["action_items"][0]["priority"])
    check("priority uppercased", out["action_items"][1]["priority"] == "high", out["action_items"][1]["priority"])
    check("hours 'abc' -> None", out["action_items"][0]["estimated_hours"] is None, str(out["action_items"][0]["estimated_hours"]))
    check("hours 3 -> 3.0", out["action_items"][1]["estimated_hours"] == 3.0, str(out["action_items"][1]["estimated_hours"]))

    # Malformed / completely wrong payloads should not crash
    out2 = _normalize({"nonsense": True})
    check(
        "empty payload handled",
        out2["summary"] == ""
        and out2["decisions"] == []
        and out2["action_items"] == [],
        str(out2),
    )
    out3 = _normalize({})
    check("empty dict handled", out3["key_points"] == [], str(out3))

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
