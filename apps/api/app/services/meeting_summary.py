"""Meeting intelligence: transcript -> summary, decisions, action items.

Implements the `meeting_extractor` prompt (see docs/PROMPTS.md).
Output is validated against a strict schema before being used.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime, date
from typing import Any

from app.services.llm import structured_completion
from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are SyncForge Meeting Intelligence, an expert meeting analyst.
You extract structured, accurate information from meeting transcripts.

Rules:
- Support English and Hinglish (Hindi written in Latin script) and mixed speech.
- Do NOT invent facts. If something is unclear, omit it or add it to unanswered_questions.
- Deadlines must be absolute ISO-8601 dates (YYYY-MM-DD) when a date is stated; otherwise null.
- Action items must be concrete, assignable and outcome-oriented.
- Keep the summary in the dominant language of the meeting.
- Respond with ONLY valid JSON matching the requested schema. No prose, no markdown outside fences.

JSON schema you MUST follow:
{
  "summary": "string (2-5 sentences)",
  "key_points": ["string"],
  "decisions": [
    {"title": "string", "description": "string", "impact": "low|medium|high", "rationale": "string"}
  ],
  "action_items": [
    {"title": "string", "description": "string", "assignee": "string or null",
     "priority": "low|medium|high|urgent", "due_date": "YYYY-MM-DD or null",
     "estimated_hours": number or null}
  ],
  "risks": ["string"],
  "unanswered_questions": ["string"],
  "next_steps": ["string"]
}
"""

USER_TEMPLATE = """Meeting title: {title}
Date: {meeting_date}
Participants: {participants}

Transcript:
\"\"\"
{transcript}
\"\"\"

Extract the JSON."""

VALID_IMPACT = {"low", "medium", "high"}
VALID_PRIORITY = {"low", "medium", "high", "urgent"}


def _clean_str(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value).strip()


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in (_clean_str(x) for x in value) if v]


def _clean_date(value: Any) -> str | None:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    # Tolerate ISO datetime prefix
    if len(value) >= 10 and value[4] == "-" and value[7] == "-":
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError:
            return None
    return None


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    decisions = []
    for item in raw.get("decisions") or []:
        if not isinstance(item, dict):
            continue
        title = _clean_str(item.get("title"))
        if not title:
            continue
        impact = _clean_str(item.get("impact"), "medium").lower()
        decisions.append({
            "title": title,
            "description": _clean_str(item.get("description")) or None,
            "impact": impact if impact in VALID_IMPACT else "medium",
            "rationale": _clean_str(item.get("rationale")) or None,
        })

    action_items = []
    for item in raw.get("action_items") or []:
        if not isinstance(item, dict):
            continue
        title = _clean_str(item.get("title"))
        if not title:
            continue
        priority = _clean_str(item.get("priority"), "medium").lower()
        hours = item.get("estimated_hours")
        try:
            hours = float(hours) if hours is not None else None
        except (TypeError, ValueError):
            hours = None
        action_items.append({
            "title": title,
            "description": _clean_str(item.get("description")) or None,
            "assignee": _clean_str(item.get("assignee")) or None,
            "priority": priority if priority in VALID_PRIORITY else "medium",
            "due_date": _clean_date(item.get("due_date")),
            "estimated_hours": hours,
        })

    return {
        "summary": _clean_str(raw.get("summary")),
        "key_points": _as_list(raw.get("key_points")),
        "decisions": decisions,
        "action_items": action_items,
        "risks": _as_list(raw.get("risks")),
        "unanswered_questions": _as_list(raw.get("unanswered_questions")),
        "next_steps": _as_list(raw.get("next_steps")),
    }


def extract_meeting_intelligence(
    transcript_text: str,
    title: str = "",
    meeting_date: str | None = None,
    participants: list[str] | None = None,
    model: str | None = None,
    allow_fallback: bool | None = None,
) -> dict[str, Any]:
    """Run the meeting extractor and return a normalized dict.

    When the LLM is unreachable (no Ollama / no API key), an offline
    extractive fallback is used unless ``allow_fallback`` is False. The
    returned dict always carries a ``source`` key ("llm" or "fallback").
    """
    if allow_fallback is None:
        allow_fallback = settings.ALLOW_EXTRACTIVE_FALLBACK

    user = USER_TEMPLATE.format(
        title=title or "(untitled)",
        meeting_date=meeting_date or "unknown",
        participants=", ".join(participants) if participants else "unknown",
        transcript=transcript_text,
    )

    try:
        raw = structured_completion(
            system=SYSTEM_PROMPT,
            user=user,
            model=model or settings.DEFAULT_SUMMARY_MODEL,
            temperature=0.1,
            max_tokens=4096,
        )
        if not isinstance(raw, dict):
            raise ValueError("Extractor returned a non-object JSON payload")
        data = _normalize(raw)
        data["source"] = "llm"
        return data
    except Exception as exc:
        if not allow_fallback:
            raise
        logger.warning(
            "LLM extraction unavailable (%s); using offline extractive fallback", exc
        )
        data = _normalize(fallback_extract(transcript_text))
        data["source"] = "fallback"
        data["fallback_reason"] = str(exc)[:300]
        return data


# --------------------------------------------------------------------------
# Offline extractive fallback (no LLM required)
# --------------------------------------------------------------------------

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")

DECISION_CUES = (
    "decid", "decision", "we will", "we'll", "final", "approve", "agreed",
    "sign off", "signoff", "settle", "go with", "choose", "chose",
    "tay", "tay kiya", "final karte", "decide kiya",
)
ACTION_CUES = (
    "will ", "need to", "needs to", "should ", "must ", "have to", "has to",
    "action item", "todo", "to do", "follow up", "follow-up", "assign",
    "karna hai", "karega", "karegi", "karunga", "banana hai", "bhejna",
    "share", "send", "prepare", "finish", "complete", "implement", "fix",
)
RISK_CUES = (
    "risk", "blocker", "blocked", "issue", "problem", "concern", "delay",
    "delayed", "late", "tight", "dependency", "depend on", "unclear",
    "doubt", "worried", "dikkat", "problem hai",
)
QUESTION_CUES = ("?", "who will", "kaun", "kya", "when will", "how will")

ACTION_NAME_RE = re.compile(
    r"^\s*([A-Z][a-zA-Z]+)\s+(?:will|to|should|must|is going to|karega|karegi|karunga)\b"
)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "so", "to", "of", "in",
    "on", "at", "for", "with", "is", "are", "was", "were", "be", "been", "it",
    "this", "that", "these", "those", "we", "you", "they", "i", "he", "she",
    "will", "would", "can", "could", "should", "must", "do", "does", "did",
    "have", "has", "had", "not", "no", "yes", "okay", "ok", "let", "lets",
    "us", "our", "your", "their", "there", "here", "about", "from", "as",
    "by", "up", "out", "into", "than", "also", "just", "very",
    "hai", "hain", "ka", "ki", "ke", "ko", "se", "aur", "bhi", "ye", "yeh",
    "wo", "woh", "mein", "main", "hum", "aap", "kar", "karo", "karna",
}


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = _SENTENCE_SPLIT.split(text.strip())
    return [p.strip(" \t\"'") for p in parts if p and len(p.strip()) > 2]


def _content_words(text: str) -> list[str]:
    return [
        w
        for w in re.findall(r"[a-zA-Z][a-zA-Z'-]+", text.lower())
        if w not in _STOPWORDS and len(w) > 2
    ]


def _short_title(sentence: str, max_words: int = 12) -> str:
    words = sentence.split()
    title = " ".join(words[:max_words])
    if len(words) > max_words:
        title += "…"
    return title.rstrip(".,;:")


def _match(cues: tuple[str, ...], sentence: str) -> bool:
    s = sentence.lower()
    return any(c in s for c in cues)


def fallback_extract(transcript_text: str) -> dict[str, Any]:
    """Extract structure from a transcript using heuristics (no LLM).

    Deliberately conservative: prefers precision over recall so the output
    stays trustworthy. Works for English and Hinglish.
    """
    sentences = _split_sentences(transcript_text)
    if not sentences:
        return {
            "summary": "",
            "key_points": [],
            "decisions": [],
            "action_items": [],
            "risks": [],
            "unanswered_questions": [],
            "next_steps": [],
        }

    # --- key points: top sentences by content-word frequency ---
    freq = Counter(w for s in sentences for w in _content_words(s))
    scored = []
    for idx, s in enumerate(sentences):
        words = _content_words(s)
        if not words:
            continue
        score = sum(freq[w] for w in set(words)) / (len(words) ** 0.5)
        # prefer earlier sentences slightly (meetings front-load decisions)
        score *= 1.0 + (len(sentences) - idx) / (len(sentences) * 4)
        scored.append((score, idx, s))
    scored.sort(reverse=True)
    key_points = [
        _short_title(s, 18) for _, _, s in sorted(scored[:5], key=lambda x: x[1])
    ]

    # --- decisions ---
    decisions = []
    for s in sentences:
        if _match(DECISION_CUES, s):
            decisions.append(
                {
                    "title": _short_title(s),
                    "description": s if s != _short_title(s) else None,
                    "impact": "high" if _match(("ship", "release", "deadline", "friday", "must"), s) else "medium",
                    "rationale": None,
                }
            )

    # --- action items ---
    action_items = []
    for s in sentences:
        if not _match(ACTION_CUES, s):
            continue
        if "?" in s:  # questions are not action items
            continue
        assignee = None
        m = ACTION_NAME_RE.match(s)
        if m:
            candidate = m.group(1)
            if candidate.lower() not in _STOPWORDS:
                assignee = candidate
        priority = "high" if _match(("urgent", "asap", "friday", "today", "must"), s) else "medium"
        action_items.append(
            {
                "title": _short_title(s),
                "description": s,
                "assignee": assignee,
                "priority": priority,
                "due_date": _extract_due_date(s),
                "estimated_hours": None,
            }
        )

    # --- risks ---
    risks = [_short_title(s, 20) for s in sentences if _match(RISK_CUES, s) and "?" not in s]

    # --- open questions ---
    questions = [
        s if s.endswith("?") else s + "?"
        for s in sentences
        if s.endswith("?") or _match(QUESTION_CUES, s)
    ]

    # --- next steps ---
    next_steps = [
        _short_title(s, 16)
        for s in sentences
        if _match(("next step", "next steps", "going forward", "from tomorrow", "follow up"), s)
    ]

    summary = " ".join(sentences[:3])
    if len(sentences) > 3:
        summary += " …"

    return {
        "summary": summary,
        "key_points": key_points,
        "decisions": decisions,
        "action_items": action_items,
        "risks": risks,
        "unanswered_questions": questions,
        "next_steps": next_steps,
    }


_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _extract_due_date(sentence: str) -> str | None:
    """Best-effort due-date extraction from a sentence (ISO string or None)."""
    s = sentence.lower()

    # Explicit date formats
    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", sentence)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", sentence)
    if m:
        d, mo, y = m.groups()
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            return None

    # "by Friday" / "on Monday"
    for name, weekday in _WEEKDAYS.items():
        if re.search(rf"\b(?:by|on|before|till|until)\s+{name}\b", s):
            today = date.today()
            delta = (weekday - today.weekday()) % 7 or 7
            return (today.fromordinal(today.toordinal() + delta)).isoformat()

    # "today" / "tomorrow" / "next week"
    today = date.today()
    if re.search(r"\bby (?:today|end of day|eod)\b", s):
        return today.isoformat()
    if re.search(r"\bby tomorrow\b", s):
        return today.fromordinal(today.toordinal() + 1).isoformat()
    if re.search(r"\bnext week\b", s):
        return today.fromordinal(today.toordinal() + 7).isoformat()

    return None
