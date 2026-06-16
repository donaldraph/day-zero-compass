"""The four agent steps. Each is one focused model call through the disk cache.

Grounding guarantee: match() and verify() pass ONLY entries from
data/knowledge.json to the model — the model never sees an open-ended request
to name opportunities, so it cannot recommend anything outside the file.
"""

import json
from pathlib import Path

from agent import foundry_iq, prompts, search
from agent.model import cached_chat, cached_completion

KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge.json"

# Hard cap on web searches per step — controls the free-tier model-call budget
# (each search round costs one extra completion) and keeps latency bounded.
MAX_SEARCHES_PER_STEP = 2

WEB_SEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the live web for current opportunities or learning resources. "
                "Returns a list of {title, url, snippet}. Results are UNVERIFIED."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    }
]


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


def _tool_call_queries(arguments: str) -> list[str]:
    """Pull the search query/queries out of a web_search tool call.

    Handles the normal {"query": "..."} shape AND GPT-4o's
    multi_tool_use.parallel wrapper, which packs several parallel calls into a
    single tool_call:
        {"tool_uses": [{"recipient_name": "functions.web_search",
                        "parameters": {"query": "..."}}, ...]}.
    Without the wrapper handling that nested form has no top-level "query", so
    the search silently ran on an empty string and Tavily never fired.
    """
    try:
        data = json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    q = data.get("query")
    if isinstance(q, str) and q.strip():
        return [q.strip()]
    queries = []
    for use in data.get("tool_uses") or []:
        if not isinstance(use, dict):
            continue
        params = use.get("parameters") or use.get("arguments") or {}
        if isinstance(params, dict):
            qq = params.get("query")
            if isinstance(qq, str) and qq.strip():
                queries.append(qq.strip())
    return queries


def _tool_chat(system: str, user: str) -> tuple[str, bool, bool, list[dict]]:
    """Tool-calling loop, capped at MAX_SEARCHES_PER_STEP web searches.

    Returns (text, all_from_cache, searched_web, results_used).
    """
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    all_cached = True
    searched = False
    results_used: list[dict] = []
    searches_done = 0

    while True:
        tools = WEB_SEARCH_TOOLS if searches_done < MAX_SEARCHES_PER_STEP else None
        msg, cached = cached_completion(messages, tools)
        all_cached = all_cached and cached

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return msg.get("content", ""), all_cached, searched, results_used

        messages.append(
            {
                "role": "assistant",
                "content": msg.get("content") or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            # One tool message per tool_call_id is required, but a single call
            # may carry several queries (the multi_tool_use.parallel wrapper) —
            # run each against the shared budget and aggregate their results.
            results: list[dict] = []
            for query in _tool_call_queries(tc.get("arguments", "")):
                if searches_done >= MAX_SEARCHES_PER_STEP:
                    break
                found, res_cached = search.web_search(query)
                all_cached = all_cached and (res_cached or not found)
                searched = True  # only set when a real, non-empty query runs
                searches_done += 1
                results.extend(found)
            results_used.extend(results)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(results, ensure_ascii=False),
                }
            )


def assess(profile: str) -> tuple[dict, str, bool]:
    """Returns (assessment_dict, raw_text, from_cache)."""
    raw, cached = cached_chat(prompts.ASSESS, profile)
    try:
        assessment = json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        assessment = {"level": "unknown", "known_skills": [], "target_track": "unknown",
                      "constraints": {"money": "unknown", "power": "unknown",
                                      "bandwidth": "unknown", "payment_access": "unknown",
                                      "device": "unknown"},
                      "eligibility_signals": [],
                      "_parse_note": "model output was not valid JSON; shown raw below"}
    return assessment, raw, cached


def _plan_user(assessment: dict, knowledge: dict) -> tuple[str, bool]:
    """Build the Plan user message, grounded in Foundry IQ verified resources.

    Returns (user_message, kb_from_cache). The same VERIFIED list the Match step
    uses is handed to the planner so it can cite real, recommendable resources and
    gate student-only items — never invent a named scholarship/voucher.
    """
    docs, _source, kb_cached = foundry_iq.retrieve(
        _opportunity_query(assessment), "opportunity", knowledge
    )
    user = (
        "Assessment JSON (ONE person — write only for them):\n"
        + json.dumps(assessment, indent=2)
        + "\n\nVERIFIED free resources you may cite (cite id + source_url exactly; "
        "recommend named programs ONLY from here; gate student-only items on "
        "eligibility_signals):\n" + json.dumps(docs, indent=2, ensure_ascii=False)
    )
    return user, kb_cached


def plan(assessment: dict, knowledge: dict) -> tuple[str, bool]:
    user, kb_cached = _plan_user(assessment, knowledge)
    text, cached = cached_chat(prompts.PLAN, user)
    return _strip_fences(text), cached and kb_cached


def plan_with_search(assessment: dict, knowledge: dict) -> tuple[str, bool, bool]:
    """Plan step grounded in Foundry IQ, with optional live search for current resources.

    Returns (text, from_cache, searched_web). Falls back to the grounded-only plan()
    whenever live search is unavailable.
    """
    if not search.is_available():
        text, cached = plan(assessment, knowledge)
        return text, cached, False
    user, kb_cached = _plan_user(assessment, knowledge)
    text, cached, searched, _ = _tool_chat(prompts.PLAN_LIVE, user)
    return _strip_fences(text), cached and kb_cached, searched


def match_live(assessment: dict) -> tuple[str, bool, bool, list[dict]]:
    """LIVE-tier matcher: web-search tool loop for current, unverified extras.

    Returns (text, from_cache, searched_web, raw_results_used). Empty text/results
    when search is unavailable — the caller simply skips the amber tier.
    """
    if not search.is_available():
        return "", True, False, []
    user = "Assessment JSON:\n" + json.dumps(assessment, indent=2)
    text, cached, searched, results = _tool_chat(prompts.MATCH_LIVE, user)
    return _strip_fences(text), cached, searched, results


def screen_live(results: list[dict]) -> tuple[str, bool]:
    """Verify-step scam screen over LIVE-tier web results."""
    if not results:
        return "", True
    user = "Web results shown to the user (UNVERIFIED):\n" + json.dumps(
        results, ensure_ascii=False, indent=2
    )
    text, cached = cached_chat(prompts.SCREEN_LIVE, user)
    return _strip_fences(text), cached


def _opportunity_query(assessment: dict) -> str:
    """A retrieval query for the verified-opportunity grounding."""
    bits = [assessment.get("target_track", ""), assessment.get("level", "")]
    bits += assessment.get("known_skills", []) or []
    bits += assessment.get("eligibility_signals", []) or []
    bits.append("free certification voucher scholarship learning resource")
    return " ".join(b for b in bits if b and b != "unknown").strip()


def match(assessment: dict, knowledge: dict) -> tuple[str, bool, str]:
    """Returns (text, from_cache, grounding_source).

    Grounding comes from Foundry IQ (Azure AI Search) when configured, falling back
    to data/knowledge.json. Either way the candidate set is a fixed VERIFIED list —
    the model still recommends ONLY from it and cites id + source_url.
    """
    docs, source, kb_cached = foundry_iq.retrieve(
        _opportunity_query(assessment), "opportunity", knowledge
    )
    if not docs:
        return ("No verified match found — the knowledge base has no opportunities yet.",
                True, source)
    user = (
        "Assessment JSON:\n" + json.dumps(assessment, indent=2)
        + "\n\nVERIFIED opportunities (recommend ONLY from this list):\n"
        + json.dumps(docs, indent=2, ensure_ascii=False)
    )
    text, cached = cached_chat(prompts.MATCH, user)
    return text, cached and kb_cached, source


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
