"""Day Zero Compass — Streamlit UI + orchestration of the four visible agent steps."""

import json

import streamlit as st

from agent import pipeline, search
from agent.model import ModelError

st.set_page_config(page_title="Day Zero Compass", page_icon="🧭", layout="centered")

st.markdown(
    """
    <style>
      .cache-badge {
        display: inline-block; background: #1f6f43; color: #fff;
        border-radius: 6px; padding: 1px 8px; font-size: 0.75rem;
        margin-left: 8px; vertical-align: middle;
      }
      .step-label { font-size: 1.05rem; font-weight: 700; }
      .web-badge {
        display: inline-block; background: #8a6d1a; color: #fff;
        border-radius: 6px; padding: 1px 8px; font-size: 0.75rem;
        margin-left: 8px; vertical-align: middle;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🧭 Day Zero Compass")
st.markdown("**From Nothing, To Everything.** — grounded, cited guidance for early-stage "
            "tech learners in underserved Southeast Nigeria.")

EXAMPLE = ("I'm 19, in Aba. I finished secondary school, I have a small Android phone and "
           "sometimes my neighbour's laptop. Power goes out most days, data is expensive. "
           "I know basic computer use and a little HTML. I want to get into cloud "
           "engineering / SRE. I have no bank card that works for foreign payments.")

with st.form("intake"):
    profile = st.text_area(
        "Tell us about yourself — level, skills, goal, and your constraints "
        "(money, power, bandwidth, payment access):",
        value=EXAMPLE,
        height=160,
    )
    run = st.form_submit_button("Run the Compass", type="primary", use_container_width=True)


def badge(from_cache: bool) -> str:
    return ' <span class="cache-badge">served from cache</span>' if from_cache else ""


def web_tag(searched: bool) -> str:
    return ' <span class="web-badge">🔎 searched the web</span>' if searched else ""


def step_header(n: int, name: str, from_cache: bool, searched: bool = False) -> str:
    return (f'<span class="step-label">Step {n} — {name}</span>'
            f"{badge(from_cache)}{web_tag(searched)}")


LIVE_CAPTION = ("We searched the web for current options. We have **NOT** verified "
                "these — confirm on the official site before acting.")


if run and profile.strip():
    try:
        knowledge = pipeline.load_knowledge()
    except Exception:
        st.error("Could not load data/knowledge.json — check the file is valid.")
        st.stop()

    live_mode = search.is_available()
    if not live_mode:
        st.info("🧭 Running in **grounded-only mode** — live web search is off "
                "(no TAVILY_API_KEY). Recommendations come from the verified "
                "knowledge base, fully cited.")

    # Step 1 — Assess
    with st.spinner("Step 1/4 — Assessing your profile…"):
        try:
            assessment, raw_assess, c1 = pipeline.assess(profile.strip())
        except ModelError as e:
            st.warning(f"The Assess step could not reach the model. {e} "
                       "If you've hit the daily free-tier limit, try again tomorrow — "
                       "previously seen profiles are served from cache.")
            st.stop()
    with st.expander("🔍 Step 1 — Assess", expanded=True):
        st.markdown(step_header(1, "Assess", c1), unsafe_allow_html=True)
        st.caption("What the agent understood about you.")
        st.json(assessment)
        if "_parse_note" in assessment:
            st.code(raw_assess)

    # Step 2 — Plan (may consult live web search for current resources)
    with st.spinner("Step 2/4 — Building your 90-day plan…"):
        try:
            plan_text, c2, plan_searched = pipeline.plan_with_search(assessment)
        except ModelError as e:
            st.warning(f"The Plan step failed: {e}")
            st.stop()
    with st.expander("🗺️ Step 2 — Plan (next 90 days)", expanded=True):
        st.markdown(step_header(2, "Plan", c2, plan_searched), unsafe_allow_html=True)
        if plan_searched:
            st.caption("Web-found resources in this plan are suggestions to verify, "
                       "not confirmed facts.")
        st.markdown(plan_text)

    # Step 3 — Match: VERIFIED tier first (grounded in knowledge.json),
    # then the separate LIVE tier from web search (never shown as verified).
    with st.spinner("Step 3/4 — Matching verified opportunities…"):
        try:
            match_text, c3 = pipeline.match(assessment, knowledge)
        except ModelError as e:
            st.warning(f"The Match step failed: {e}")
            st.stop()
    live_text, live_results, match_searched, c3b = "", [], False, True
    if live_mode:
        with st.spinner("Step 3/4 — Searching the web for current extras…"):
            try:
                live_text, c3b, match_searched, live_results = pipeline.match_live(assessment)
            except ModelError as e:
                st.caption(f"Live search skipped ({e}) — verified results below are unaffected.")
    with st.expander("🎯 Step 3 — Match (verified first, live extras flagged)", expanded=True):
        st.markdown(step_header(3, "Match", c3 and c3b, match_searched),
                    unsafe_allow_html=True)
        st.markdown("**✅ Verified — from our checked sources**")
        st.caption("Recommendations come ONLY from the vetted knowledge file, with citations. "
                   "If nothing fits, the agent says so — it never invents an opportunity.")
        st.success(match_text)
        if live_text:
            st.markdown("**🌐 Live — found online, unverified**")
            st.caption(LIVE_CAPTION)
            st.warning(live_text)

    # Step 4 — Verify: knowledge-base pitfalls (grounded) + scam screen of any
    # LIVE-tier web results surfaced in Step 3.
    with st.spinner("Step 4/4 — Safety check: scams & access pitfalls…"):
        try:
            verify_text, c4 = pipeline.verify(assessment, knowledge)
        except ModelError as e:
            st.warning(f"The Verify step failed: {e}")
            st.stop()
        screen_text, c4b = "", True
        if live_results:
            try:
                screen_text, c4b = pipeline.screen_live(live_results)
            except ModelError as e:
                screen_text = ("Could not run the automated scam screen on the live web "
                               f"results ({e}). Treat every live result as unverified and "
                               "confirm on the official site before acting.")
    with st.expander("🛡️ Step 4 — Verify (safety & access pitfalls)", expanded=True):
        st.markdown(step_header(4, "Verify", c4 and c4b), unsafe_allow_html=True)
        st.caption("Known scams and access barriers relevant to you, with documented workarounds.")
        st.markdown(verify_text)
        if screen_text:
            st.markdown("**🌐 Scam screen of the live web results above**")
            st.caption(LIVE_CAPTION)
            st.warning(screen_text)

    if live_text:
        st.success("Done. Verified recommendations are grounded in the vetted knowledge "
                   "file with citations; anything found by live web search is clearly "
                   "marked unverified and screened for scam signals — nothing is invented.")
    else:
        st.success("Done. Every recommendation above is grounded in the vetted knowledge "
                   "file — nothing is invented.")
elif run:
    st.warning("Please enter a short profile first.")

st.divider()
st.caption("Day Zero Compass never invents scholarships, vouchers, deadlines, or links. "
           "Verified recommendations come from its human-checked knowledge base, fully "
           "cited; anything found by live web search is always marked unverified and "
           "screened for scam signals. Always confirm on the issuer's official website.")
