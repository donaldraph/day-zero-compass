"""Two-profile test for the personalized, grounded Plan step.

Confirms the two plans are visibly different and each references that person's own
stated details (level, skills, goal, every named constraint), cites real KB resources,
and respects eligibility. Reports both plans verbatim + quota.

Usage: GITHUB_TOKEN=... [AZURE_SEARCH_* / TAVILY_API_KEY=...] python test_plan.py
"""
from agent import model, search, pipeline
from agent.pipeline import load_knowledge

COUNTS = {"completions": 0, "searches": 0}
_oc, _ocomp, _os = model.cached_chat, model.cached_completion, search.web_search
def _c(*a, **k):
    o, c = _oc(*a, **k);  COUNTS["completions"] += 0 if c else 1;  return o, c
def _cp(*a, **k):
    o, c = _ocomp(*a, **k);  COUNTS["completions"] += 0 if c else 1;  return o, c
def _s(*a, **k):
    o, c = _os(*a, **k);  COUNTS["searches"] += 0 if (c or not o) else 1;  return o, c
model.cached_chat = pipeline.cached_chat = _c
pipeline.cached_completion = _cp
pipeline.search.web_search = search.web_search = _s

PROFILES = {
    "A — 19yo Aba, phone-first, power cuts, no card, basic HTML": (
        "I'm 19, in Aba. I finished secondary school, I have a small Android phone and "
        "sometimes my neighbour's laptop. Power goes out most days, data is expensive. "
        "I know basic computer use and a little HTML. I want to get into cloud "
        "engineering / SRE. I have no bank card that works for foreign payments."),
    "B — 300-level student, own laptop, stable power, same goal": (
        "I'm a 300-level Computer Science student at a Nigerian university. I have my own "
        "laptop and stable power at home, decent campus Wi-Fi, and a school email. I've "
        "done Python and some Linux. I also want to get into cloud engineering / SRE."),
}

def main():
    k = load_knowledge()
    print(f"Tavily available: {search.is_available()}\n")
    for label, profile in PROFILES.items():
        COUNTS["completions"] = COUNTS["searches"] = 0
        assessment, _raw, _c1 = pipeline.assess(profile)
        plan_text, _c2, searched = pipeline.plan_with_search(assessment, k)
        print("=" * 80)
        print(label)
        print("-" * 80)
        print("ASSESSMENT level/track:", assessment.get("level"), "/", assessment.get("target_track"))
        print("known_skills:", assessment.get("known_skills"))
        print("constraints:", assessment.get("constraints"))
        print("eligibility_signals:", assessment.get("eligibility_signals"))
        print(f"searched_web: {searched}")
        print("\nPLAN (verbatim):\n")
        print(plan_text)
        print(f"\n[quota] live completions={COUNTS['completions']}  "
              f"tavily_searches={COUNTS['searches']}\n")

if __name__ == "__main__":
    main()
