"""End-to-end test + quota meter for the hero-mode scam verifier.

Runs three pasted inputs (known scam / ambiguous / legit-looking), then the
no-Tavily fallback and a cache replay. Reports each verdict verbatim and the
number of LIVE (non-cached) model completions + web searches each run cost.

Usage:  GITHUB_TOKEN=... [TAVILY_API_KEY=...] python test_verifier.py
"""

import os

from agent import model, search, verifier
from agent.pipeline import load_knowledge

# ---- quota meter: count only calls that actually hit the network ----
COUNTS = {"completions": 0, "searches": 0}
_orig_chat, _orig_comp, _orig_search = model.cached_chat, model.cached_completion, search.web_search


def _chat(*a, **k):
    out, cached = _orig_chat(*a, **k)
    if not cached:
        COUNTS["completions"] += 1
    return out, cached


def _comp(*a, **k):
    out, cached = _orig_comp(*a, **k)
    if not cached:
        COUNTS["completions"] += 1
    return out, cached


def _search(*a, **k):
    out, cached = _orig_search(*a, **k)
    if out and not cached:
        COUNTS["searches"] += 1
    return out, cached


# Patch every reference (modules import these by name).
for m in (model, verifier):
    if hasattr(m, "cached_chat"):
        m.cached_chat = _chat
import agent.pipeline as P
P.cached_completion = _comp
P.search.web_search = _search
search.web_search = _search


def reset():
    COUNTS["completions"] = COUNTS["searches"] = 0


INPUTS = {
    "1-KNOWN-SCAM (fake Tinubu N50k grant)": (
        "URGENT! President Tinubu has approved a N50,000 cash grant for all Nigerians. "
        "Applications reopening NOW and closing today! Claim yours before it's gone. "
        "Enter your full name, phone, home address and bank account details here: "
        "http://tinubu-grant-portal.com.ng/claim. Forward to 10 people to activate."
    ),
    "2-AMBIGUOUS (vague remote job)": (
        "Hello, we saw your profile and think you'd be great for a remote customer-support "
        "role, $400/week, flexible hours, no experience needed. Reply 'INTERESTED' to begin "
        "onboarding this week."
    ),
    "3-LEGIT-LOOKING (Microsoft Virtual Training Day)": (
        "Microsoft is hosting a free Virtual Training Day on Azure Fundamentals (AZ-900). "
        "Register free at https://www.microsoft.com/trainingdays to attend the live sessions "
        "and earn a certification exam voucher. No payment required."
    ),
    "4-AI-SKILLS-FEST (official aka.ms, fill dashboard form)": (
        "🎉 Microsoft AI Skills Fest is here! Join the free global AI learning event. "
        "Register and complete the challenge on your Microsoft Learn dashboard at "
        "https://aka.ms/AISkillsFest before the deadline on 8 July 2026 to earn your badge. "
        "No payment, no card — just sign in with your account and fill the form."
    ),
    "5-NEW-SCAM (never pre-loaded — structural only)": (
        "CONGRATULATIONS! You have been selected for the 2026 Shell Nigeria Youth "
        "Empowerment Grant of N250,000. To claim, pay a N5,000 processing fee and submit "
        "your BVN and bank account number at http://shell-grant-ng.online/verify within "
        "24 hours or your slot will be given away."
    ),
}


def run_one(label, text, knowledge):
    reset()
    res = verifier.verify_opportunity(text, knowledge)
    v = res["verdict"]
    print("=" * 78)
    print(label)
    print("-" * 78)
    print(f"VERDICT      : {v['verdict']}   (confidence: {v['confidence']})")
    print(f"SUMMARY      : {v['summary']}")
    print(f"REASONING    : {v.get('reasoning')}")
    print(f"RED FLAGS    : {v['red_flags']}")
    print(f"SCAM MATCH   : {v['known_scam_match']}")
    print(f"LEGIT MATCH  : {v.get('known_legit_match')}")
    print(f"LIVE CONFIRM : {v.get('live_confirmation')}")
    print(f"GROUNDING    : {res.get('grounding_source')}")
    print(f"EXTRACTION   : domain={res['extraction'].get('domain')!r} "
          f"hoped_for={res['extraction'].get('hoped_for')!r}")
    evidence = []
    if v['red_flags'] or v.get('reasoning'): evidence.append("reasoning")
    if v['known_scam_match'] or v.get('known_legit_match'): evidence.append("Foundry IQ KB")
    if v.get('live_confirmation'): evidence.append("Tavily live")
    print(f"EVIDENCE FIRED: {evidence}")
    print(f"\n[quota] live completions={COUNTS['completions']}  "
          f"web searches={COUNTS['searches']}  searched_web={res['searched_web']}  "
          f"all_cached={res['all_cached']}  live_mode={res['live_mode']}")
    print()
    return res


def main():
    knowledge = load_knowledge()
    print(f"Tavily available: {search.is_available()}\n")

    results = {}
    for label, text in INPUTS.items():
        results[label] = run_one(label, text, knowledge)

    # Cache replay — rerun input 1, expect zero quota.
    print("#" * 78)
    print("CACHE REPLAY of input 1 (expect 0 live completions / 0 searches):")
    reset()
    res = verifier.verify_opportunity(INPUTS[list(INPUTS)[0]], knowledge)
    print(f"[quota] live completions={COUNTS['completions']}  web searches={COUNTS['searches']}  "
          f"all_cached={res['all_cached']}")

    print("\nDONE.")


if __name__ == "__main__":
    main()
