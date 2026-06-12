"""The four agent steps. Each is one focused model call through the disk cache.

Grounding guarantee: match() and verify() pass ONLY entries from
data/knowledge.json to the model — the model never sees an open-ended request
to name opportunities, so it cannot recommend anything outside the file.
"""

import json
from pathlib import Path

from agent import prompts
from agent.model import cached_chat

KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge.json"


def load_knowledge() -> dict:
    raw = KNOWLEDGE_PATH.read_text(encoding="utf-8")
    # Allow //-comment lines so the human-editing note can live in the file.
    lines = [ln for ln in raw.splitlines() if not ln.lstrip().startswith("//")]
    return json.loads("\n".join(lines))


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def assess(profile: str) -> tuple[dict, str, bool]:
    """Returns (assessment_dict, raw_text, from_cache)."""
    raw, cached = cached_chat(prompts.ASSESS, profile)
    try:
        assessment = json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        assessment = {"level": "unknown", "known_skills": [], "target_track": "unknown",
                      "constraints": {"money": "unknown", "power": "unknown",
                                      "bandwidth": "unknown", "payment_access": "unknown"},
                      "_parse_note": "model output was not valid JSON; shown raw below"}
    return assessment, raw, cached


def plan(assessment: dict) -> tuple[str, bool]:
    user = "Assessment JSON:\n" + json.dumps(assessment, indent=2)
    text, cached = cached_chat(prompts.PLAN, user)
    return _strip_fences(text), cached


def match(assessment: dict, knowledge: dict) -> tuple[str, bool]:
    opportunities = knowledge.get("opportunities", [])
    if not opportunities:
        return "No verified match found — the knowledge base has no opportunities yet.", True
    user = (
        "Assessment JSON:\n" + json.dumps(assessment, indent=2)
        + "\n\nVERIFIED opportunities (recommend ONLY from this list):\n"
        + json.dumps(opportunities, indent=2)
    )
    return cached_chat(prompts.MATCH, user)


def verify(assessment: dict, knowledge: dict) -> tuple[str, bool]:
    pitfalls = knowledge.get("pitfalls", [])
    if not pitfalls:
        return ("No documented pitfalls in the knowledge base yet. General rule: verify any "
                "opportunity on the issuer's official site and never pay to apply."), True
    user = (
        "Assessment JSON:\n" + json.dumps(assessment, indent=2)
        + "\n\nKNOWN_PITFALLS (use ONLY this list):\n"
        + json.dumps(pitfalls, indent=2)
    )
    return cached_chat(prompts.VERIFY, user)
