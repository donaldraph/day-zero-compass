"""Day Zero Compass — Streamlit UI + orchestration of the four visible agent steps."""

import json

import streamlit as st

from agent import pipeline
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


def step_header(n: int, name: str, from_cache: bool) -> str:
    return f'<span class="step-label">Step {n} — {name}</span>{badge(from_cache)}'


if run and profile.strip():
    try:
        knowledge = pipeline.load_knowledge()
    except Exception:
        st.error("Could not load data/knowledge.json — check the file is valid.")
        st.stop()

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

    # Step 2 — Plan
    with st.spinner("Step 2/4 — Building your 90-day plan…"):
        try:
            plan_text, c2 = pipeline.plan(assessment)
        except ModelError as e:
            st.warning(f"The Plan step failed: {e}")
            st.stop()
    with st.expander("🗺️ Step 2 — Plan (next 90 days)", expanded=True):
        st.markdown(step_header(2, "Plan", c2), unsafe_allow_html=True)
        st.markdown(plan_text)

    # Step 3 — Match (grounded: reads only data/knowledge.json)
    with st.spinner("Step 3/4 — Matching verified opportunities…"):
        try:
            match_text, c3 = pipeline.match(assessment, knowledge)
        except ModelError as e:
            st.warning(f"The Match step failed: {e}")
            st.stop()
    with st.expander("🎯 Step 3 — Match (verified opportunities only)", expanded=True):
        st.markdown(step_header(3, "Match", c3), unsafe_allow_html=True)
        st.caption("Recommendations come ONLY from the vetted knowledge file, with citations. "
                   "If nothing fits, the agent says so — it never invents an opportunity.")
        st.markdown(match_text)

    # Step 4 — Verify (grounded: reads only data/knowledge.json)
    with st.spinner("Step 4/4 — Safety check: scams & access pitfalls…"):
        try:
            verify_text, c4 = pipeline.verify(assessment, knowledge)
        except ModelError as e:
            st.warning(f"The Verify step failed: {e}")
            st.stop()
    with st.expander("🛡️ Step 4 — Verify (safety & access pitfalls)", expanded=True):
        st.markdown(step_header(4, "Verify", c4), unsafe_allow_html=True)
        st.caption("Known scams and access barriers relevant to you, with documented workarounds.")
        st.markdown(verify_text)

    st.success("Done. Every recommendation above is grounded in the vetted knowledge file — "
               "nothing is invented.")
elif run:
    st.warning("Please enter a short profile first.")

st.divider()
st.caption("Day Zero Compass never invents scholarships, vouchers, deadlines, or links. "
           "It only recommends what's in its human-verified knowledge base, and it cites "
           "every source. Always confirm on the issuer's official website.")
