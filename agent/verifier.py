"""Hero mode — "Is this opportunity real?" scam verifier.

Reuses the existing spine: the GitHub Models GPT-4o client + disk cache
(agent.model), the Tavily search tool (agent.search), the capped tool loop and
knowledge loader (agent.pipeline), and the grounded/eligibility-gated matcher.

Flow: Extract -> Check+Verdict -> Real alternative. Each step is one focused,
cached GPT-4o call. Web search is the UNVERIFIED tier and is always labeled so.
Honesty rules (never give false reassurance, never fabricate a scam, bias to
caution) live in the prompts AND are re-enforced in code in _normalize_verdict().
"""

import json

from agent import foundry_iq, pipeline, prompts, search
from agent.model import cached_chat

VALID_VERDICTS = {"scam", "suspicious", "clear"}

# A 🟢 verdict must NEVER read as "safe / legit / go ahead". If the model's summary
# leans reassuring, we replace it with this canonical, caution-preserving line.
CLEAR_SAFE_SUMMARY = ("No red flags found — but this is not a guarantee. "
                      "Confirm on the official website yourself before acting.")
_REASSURING_TERMS = ("legit", "safe", "genuine", "trustworthy", "trusted", "go ahead",
                     "you can trust", "is real", "is authentic", "no risk", "verified offer")


def extract(pasted_text: str) -> tuple[dict, str, bool]:
    """Parse the pasted message into structured claims. Returns (dict, raw, from_cache)."""
    raw, cached = cached_chat(prompts.EXTRACT_CLAIM, pasted_text.strip())
    try:
        data = json.loads(pipeline._strip_fences(raw))
    except json.JSONDecodeError:
        data = {
            "claimed_offer": "", "sender_brand": "", "url": "", "domain": "",
            "asks_for": [], "urgency": False, "hoped_for": "",
            "hoped_for_track": "general", "eligibility_signals": [],
            "_parse_note": "model output was not valid JSON; shown raw below",
        }
    # Defensive defaults so the UI never KeyErrors on a sparse extraction.
    data.setdefault("claimed_offer", "")
    data.setdefault("sender_brand", "")
    data.setdefault("url", "")
    data.setdefault("domain", "")
    data.setdefault("asks_for", [])
    data.setdefault("urgency", False)
    data.setdefault("hoped_for", "")
    data.setdefault("hoped_for_track", "general")
    data.setdefault("eligibility_signals", [])
    return data, raw, cached


def _normalize_verdict(data: dict) -> dict:
    """Force the model's verdict JSON into a safe shape.

    This is the code-side honesty backstop: any parse failure or out-of-range
    verdict collapses to 'suspicious' (never 'clear'), and a 'clear' verdict that
    nonetheless carries red flags or a known-scam match is downgraded. We never
    upgrade toward reassurance here — only toward caution.
    """
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = "suspicious"

    red_flags = data.get("red_flags") or []
    if not isinstance(red_flags, list):
        red_flags = [str(red_flags)]
    red_flags = [str(f) for f in red_flags if str(f).strip()]

    def _cite(obj):
        return obj if (isinstance(obj, dict) and obj.get("id")) else None

    scam_match = _cite(data.get("known_scam_match"))
    legit_match = _cite(data.get("known_legit_match"))

    # Caution-only backstops, never toward reassurance:
    #  - a human-verified KNOWN_SCAMS match is authoritative -> 🔴
    #  - a green light must carry no red flags
    if scam_match:
        verdict = "scam"
    elif verdict == "clear" and red_flags:
        verdict = "suspicious"

    live = data.get("live_confirmation")
    if isinstance(live, dict) and str(live.get("status", "")).strip().lower() in {
        "confirms_real", "confirms_scam", "inconclusive"
    }:
        live = {"status": str(live["status"]).strip().lower(),
                "statement": str(live.get("statement", "")).strip(),
                "url": str(live.get("url", "")).strip(),
                "deadline": str(live.get("deadline", "")).strip()}
    else:
        live = None

    web_findings = data.get("web_findings") or []
    if not isinstance(web_findings, list):
        web_findings = []
    web_findings = [w for w in web_findings if isinstance(w, dict) and w.get("finding")]

    confidence = str(data.get("confidence", "")).strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "low"

    summary = str(data.get("summary", "")).strip()
    # Honesty backstop: scrub any false "all-clear" reassurance from a green verdict.
    if verdict == "clear" and (not summary or any(t in summary.lower() for t in _REASSURING_TERMS)):
        summary = CLEAR_SAFE_SUMMARY

    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": summary,
        "reasoning": str(data.get("reasoning", "")).strip(),
        "red_flags": red_flags,
        "known_scam_match": scam_match,
        "known_legit_match": legit_match,
        "live_confirmation": live,
        "web_findings": web_findings,
    }


def _scam_query(extraction: dict) -> str:
    """Retrieval query to pull the most relevant KNOWN_SCAMS for this message."""
    bits = [extraction.get("claimed_offer", ""), extraction.get("sender_brand", ""),
            extraction.get("domain", "")]
    bits += extraction.get("asks_for", []) or []
    bits.append("scam phishing fraud impersonation")
    return " ".join(b for b in bits if b).strip()


def _legit_query(extraction: dict) -> str:
    """Retrieval query to pull matching KNOWN_LEGIT programs (positive confirmation)."""
    bits = [extraction.get("claimed_offer", ""), extraction.get("sender_brand", ""),
            extraction.get("domain", ""), extraction.get("hoped_for", "")]
    bits.append("official verified program")
    return " ".join(b for b in bits if b).strip()


def check_verdict(extraction: dict, knowledge: dict) -> tuple[dict, bool, bool, list[dict], str]:
    """Weigh evidence: known scams + known-legit programs + heuristics (+ live search).

    Grounding for BOTH tiers is retrieved from Foundry IQ (Azure AI Search) when
    configured, falling back to data/knowledge.json — so the agent can both match
    documented scams and positively confirm verified-legitimate programs.
    Returns (verdict_dict, from_cache, searched_web, raw_web_results, grounding_source).
    """
    scams, src_s, _ = foundry_iq.retrieve(_scam_query(extraction), "pitfall", knowledge)
    legit, src_l, _ = foundry_iq.retrieve(_legit_query(extraction), "opportunity", knowledge)
    kb_source = src_s if src_s.startswith("foundry") else src_l
    user = (
        "Pasted-message extraction:\n" + json.dumps(extraction, indent=2, ensure_ascii=False)
        + "\n\nKNOWN_SCAMS / KNOWN_PITFALLS (cite exact id + source_url on a match):\n"
        + json.dumps(scams, indent=2, ensure_ascii=False)
        + "\n\nKNOWN_LEGIT — verified-legitimate programs (confirm a match by program "
        "name + official domain; cite exact id + source_url):\n"
        + json.dumps(legit, indent=2, ensure_ascii=False)
    )

    searched, raw_results = False, []
    if search.is_available():
        raw, cached, searched, raw_results = pipeline._tool_chat(prompts.SCAM_VERDICT_LIVE, user)
    else:
        raw, cached = cached_chat(prompts.SCAM_VERDICT, user)

    try:
        parsed = json.loads(pipeline._strip_fences(raw))
    except json.JSONDecodeError:
        # Never silently pass: an unparseable verdict is treated as "can't confirm".
        parsed = {
            "verdict": "suspicious", "confidence": "low",
            "summary": "We could not automatically read this one — treat it as unsafe "
                       "until you confirm it yourself.",
            "red_flags": [],
        }
    return _normalize_verdict(parsed), cached, searched, raw_results, kb_source


def _alternative_assessment(extraction: dict) -> dict:
    """Derive a minimal assessment from the extraction so the verified matcher can run.

    Eligibility signals carry through ONLY if the pasted text actually stated them,
    so student-only items stay gated for an anonymous forwarded message.
    """
    return {
        "level": "unknown",
        "known_skills": [],
        "target_track": extraction.get("hoped_for_track", "general") or "general",
        "constraints": {"money": "unknown", "power": "unknown",
                        "bandwidth": "unknown", "payment_access": "unknown"},
        "eligibility_signals": extraction.get("eligibility_signals", []) or [],
    }


def real_alternative(extraction: dict, knowledge: dict) -> tuple[str, bool]:
    """Surface the closest VERIFIED, free opportunity as a safe path. Returns (text, cached)."""
    opportunities = knowledge.get("opportunities", [])
    if not opportunities:
        return ("We don't have a verified alternative on file right now. Look for free "
                "options on the issuer's official website only, and never pay to apply."), True
    user = (
        "Pasted-message extraction:\n" + json.dumps(extraction, indent=2, ensure_ascii=False)
        + "\n\nDerived assessment (for eligibility gating):\n"
        + json.dumps(_alternative_assessment(extraction), indent=2)
        + "\n\nVERIFIED opportunities (recommend ONLY from this list):\n"
        + json.dumps(opportunities, indent=2, ensure_ascii=False)
    )
    text, cached = cached_chat(prompts.SCAM_ALTERNATIVE, user)
    return pipeline._strip_fences(text), cached


def verify_opportunity(pasted_text: str, knowledge: dict) -> dict:
    """Full hero-mode pipeline: Extract -> Check/Verdict -> Real alternative.

    Returns a structured result the UI renders. Raises ModelError only if the
    underlying model is unreachable with no cache (the app handles that calmly).
    """
    extraction, raw_extract, c_extract = extract(pasted_text)
    verdict, c_verdict, searched, _, kb_source = check_verdict(extraction, knowledge)
    alt_text, c_alt = real_alternative(extraction, knowledge)

    return {
        "extraction": extraction,
        "extraction_raw": raw_extract,
        "verdict": verdict,
        "alternative": alt_text,
        "searched_web": searched,
        "live_mode": search.is_available(),
        "live_error": search.last_error() if searched else None,
        "grounding_source": kb_source,
        "all_cached": c_extract and c_verdict and c_alt,
    }
