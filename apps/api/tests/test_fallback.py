"""Tests for the offline extractive fallback (no LLM required).

Run:  python tests/test_fallback.py
"""

from __future__ import annotations

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.meeting_summary import (  # noqa: E402
    fallback_extract,
    _normalize,
    _extract_due_date,
    _short_title,
)

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"{'PASS' if cond else 'FAIL'} | {name} | {detail}")


TRANSCRIPT = (
    "Okay team, let's start the sprint planning meeting. "
    "First decision, we will ship the login page by Friday. "
    "Second decision, Google authentication must be added this sprint. "
    "Priya will redesign the dashboard layout. "
    "Rahul will finish the login page and write the tests. "
    "There is a risk that testing starts late and blocks the release. "
    "Open question, who will own the production deployment? "
    "Next steps, daily standup at 10 a.m. and a demo on Monday."
)

HINGLISH = (
    "Chalo meeting start karte hain. "
    "Hum decide kiya ki login page Friday tak ship karenge. "
    "Priya dashboard redesign karega. "
    "Testing late hone ka risk hai. "
    "Kaun production deployment karega?"
)


def test_empty() -> None:
    out = fallback_extract("")
    check("empty transcript -> empty summary", out["summary"] == "")
    check("empty transcript -> no decisions", out["decisions"] == [])
    check("empty transcript -> no action items", out["action_items"] == [])


def test_decisions() -> None:
    out = fallback_extract(TRANSCRIPT)
    titles = " | ".join(d["title"].lower() for d in out["decisions"])
    check("detects 'we will ship' decision", "ship the login page" in titles, titles)
    check(
        "detects 'must be added' decision",
        "authentication" in titles or "google authentication" in titles,
        titles,
    )
    check("decisions have impact field", all("impact" in d for d in out["decisions"]))


def test_action_items() -> None:
    out = fallback_extract(TRANSCRIPT)
    titles = " | ".join(a["title"].lower() for a in out["action_items"])
    check("detects Priya action", "priya" in titles, titles)
    check("detects Rahul action", "rahul" in titles, titles)
    assignees = {a["assignee"] for a in out["action_items"] if a.get("assignee")}
    check("extracts assignee names", {"Priya", "Rahul"} <= assignees, str(assignees))
    check(
        "assigns priority to each item",
        all(a.get("priority") in {"low", "medium", "high", "urgent"} for a in out["action_items"]),
    )
    check(
        "question is not treated as action item",
        all("?" not in (a["description"] or "") for a in out["action_items"]),
    )


def test_risks_and_questions() -> None:
    out = fallback_extract(TRANSCRIPT)
    risks = " | ".join(out["risks"]).lower()
    check("detects risk sentence", "risk" in risks, risks)
    questions = " ".join(out["unanswered_questions"]).lower()
    check(
        "detects open question",
        "who will own the production deployment" in questions,
        questions,
    )
    check("questions end with '?'", all(q.endswith("?") for q in out["unanswered_questions"]))


def test_key_points_and_summary() -> None:
    out = fallback_extract(TRANSCRIPT)
    check("produces key points", len(out["key_points"]) > 0, f"n={len(out['key_points'])}")
    check("caps key points at 5", len(out["key_points"]) <= 5, f"n={len(out['key_points'])}")
    check("produces summary", len(out["summary"]) > 20, out["summary"][:60])


def test_hinglish() -> None:
    out = fallback_extract(HINGLISH)
    decisions = " | ".join(d["title"].lower() for d in out["decisions"])
    check("hinglish: detects decision cue", "decide" in decisions or "ship" in decisions, decisions)
    actions = " | ".join(a["title"].lower() for a in out["action_items"])
    check("hinglish: detects action ('karega')", "priya" in actions, actions)
    risks = " | ".join(out["risks"]).lower()
    check("hinglish: detects 'risk'", "risk" in risks, risks)
    questions = " ".join(out["unanswered_questions"]).lower()
    check("hinglish: detects 'kaun' question", "kaun" in questions or "?" in questions, questions)


def test_due_dates() -> None:
    check("parses ISO date", _extract_due_date("ship by 2026-03-15 please") == "2026-03-15")
    check("parses d/m/Y", _extract_due_date("due 15/03/2026") == "2026-03-15")

    friday = _extract_due_date("we will ship by Friday")
    check("parses weekday", friday is not None and len(friday) == 10, str(friday))
    if friday:
        d = date.fromisoformat(friday)
        check("weekday is a Friday", d.weekday() == 4, d.strftime("%A"))

    today = date.today().isoformat()
    check("parses 'by today'", _extract_due_date("finish by today") == today)
    check("no date -> None", _extract_due_date("just do it soon") is None)


def test_short_title() -> None:
    long = " ".join(["word"] * 20)
    t = _short_title(long)
    check("truncates long titles", len(t.split()) <= 12 and t.endswith("…"), t)


def test_normalize_accepts_fallback() -> None:
    """The fallback output must survive _normalize unchanged in shape."""
    raw = fallback_extract(TRANSCRIPT)
    norm = _normalize(raw)
    check("normalize keeps summary", bool(norm["summary"]))
    check("normalize keeps decisions", len(norm["decisions"]) == len(raw["decisions"]))
    check("normalize keeps action items", len(norm["action_items"]) == len(raw["action_items"]))
    check(
        "normalized action items have required keys",
        all(
            {"title", "description", "assignee", "priority", "due_date", "estimated_hours"}
            <= set(a)
            for a in norm["action_items"]
        ),
        str(sorted(norm["action_items"][0].keys()) if norm["action_items"] else "none"),
    )


def main() -> int:
    test_empty()
    test_decisions()
    test_action_items()
    test_risks_and_questions()
    test_key_points_and_summary()
    test_hinglish()
    test_due_dates()
    test_short_title()
    test_normalize_accepts_fallback()

    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n---")
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
