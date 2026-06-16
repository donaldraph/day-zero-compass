"""Day Zero Compass — Streamlit UI.

Two modes share one grounded spine:
  🛡️ Check if an opportunity is real  (HERO / default) — paste-and-verify scam check
  🧭 Plan my learning path            (secondary) — the four visible agent steps
"""

import json

import streamlit as st

from agent import foundry_iq, pipeline, search, verifier
from agent.model import ContentFilterError, ModelError

st.set_page_config(page_title="Day Zero Compass", page_icon="🛡️", layout="centered")

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
      .verdict-banner {
        border-radius: 12px; padding: 18px 20px; margin: 8px 0 4px 0;
        color: #fff; font-weight: 700;
      }
      .verdict-banner .vb-title { font-size: 1.5rem; line-height: 1.2; }
      .verdict-banner .vb-summary { font-size: 1.0rem; font-weight: 500; margin-top: 6px; }
      .vb-red   { background: #a01b1b; }
      .vb-amber { background: #8a5a0a; }
      .vb-green { background: #1f6f43; }
      .vb-conf  { font-size: 0.8rem; font-weight: 600; opacity: 0.9; }
      .trust-line { margin: -6px 0 10px 0; font-size: 0.86rem; color: #9aa6b2; }
      .trust-badge {
        display: inline-block; background: rgba(31,111,67,0.18); color: #4cc38a;
        border: 1px solid rgba(76,195,138,0.45); border-radius: 999px;
        padding: 1px 10px; font-size: 0.8rem; font-weight: 600; margin-right: 6px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🛡️ Day Zero Compass")

# Subtitle slot is filled after the mode is known so it swaps with the toggle,
# while keeping the page order: title → subtitle → trust line → mode picker.
subtitle_slot = st.empty()

SUBTITLES = {
    "🛡️ Check if an opportunity is real":
        "**Is this opportunity real?** Paste any scholarship, grant, job, or link you got "
        "on WhatsApp and find out if it's real or a scam — why, and what to do instead.",
    "🧭 Plan my learning path":
        "**Where are you starting from?** Tell me your level, goals, and constraints, and "
        "I'll map a real, step-by-step path into tech — with verified, cited resources, "
        "not invented ones.",
}


def trust_line() -> None:
    """A single quiet, user-facing trust signal under the title (no dev plumbing)."""
    kind, _ = foundry_iq.status()
    label = ("Grounded on Microsoft Foundry IQ" if kind == "foundry"
             else "Grounded on verified, cited sources")
    st.markdown(f'<div class="trust-line"><span class="trust-badge">🛡️ {label}</span>'
                "verified sources, cited — never invented.</div>", unsafe_allow_html=True)


trust_line()

mode = st.radio(
    "What do you need?",
    ["🛡️ Check if an opportunity is real", "🧭 Plan my learning path"],
    index=0,
    horizontal=True,
)

subtitle_slot.markdown(SUBTITLES[mode])

STANDING_CAPTION = ("This is guidance, not a guarantee. Always confirm on the official "
                    "website before acting.")
LIVE_CAPTION = ("We searched the web for current options. We have **NOT** verified "
                "these — confirm on the official site before acting.")


def badge(from_cache: bool) -> str:
    return ' <span class="cache-badge">served from cache</span>' if from_cache else ""


def web_tag(searched: bool) -> str:
    return ' <span class="web-badge">🔎 searched the web</span>' if searched else ""


def step_header(n: int, name: str, from_cache: bool, searched: bool = False) -> str:
    return (f'<span class="step-label">Step {n} — {name}</span>'
            f"{badge(from_cache)}{web_tag(searched)}")


def load_knowledge_or_stop() -> dict:
    try:
        return pipeline.load_knowledge()
    except Exception:
        st.error("Could not load data/knowledge.json — check the file is valid.")
        st.stop()


def technical_details() -> None:
    """Developer/judge-facing status, tucked away — not in the user's main view."""
    with st.expander("⚙️ Technical details"):
        _, grounding_msg = foundry_iq.status()
        st.markdown(f"- **Knowledge grounding:** {grounding_msg}")
        live_ok, live_msg = search.status()
        if live_ok:
            st.markdown("- **Live web search:** enabled (Tavily) — adds an unverified, "
                        "scam-screened web tier.")
        elif search.is_available():
            st.markdown(f"- **Live web search:** ⚠️ {live_msg}")
        else:
            st.markdown("- **Live web search:** off (optional). The app runs fully on the "
                        "verified, cited knowledge base; web cross-checking is skipped.")
        st.markdown("- **Caching:** every model call and retrieval is disk-cached, so "
                    "repeat checks cost zero quota.")


# ---------------------------------------------------------------------------
# HERO MODE — scam verifier
# ---------------------------------------------------------------------------

SCAM_EXAMPLE = (
    "URGENT! President Tinubu has approved a N50,000 cash grant for all Nigerians. "
    "Applications reopening NOW and closing today! Claim yours before it's gone. "
    "Enter your full name, phone, home address and bank account details here: "
    "http://tinubu-grant-portal.com.ng/claim. Forward to 10 people to activate."
)

_VB = {
    "scam":       ("vb-red",   "🔴 LIKELY A SCAM"),
    "suspicious": ("vb-amber", "🟠 SUSPICIOUS / CAN'T CONFIRM"),
    "clear":      ("vb-green", "🟢 NO RED FLAGS FOUND"),
}


def render_verdict_banner(verdict: dict) -> None:
    css, title = _VB.get(verdict["verdict"], _VB["suspicious"])
    summary = verdict["summary"] or {
        "scam": "This matches scam patterns — do not engage.",
        "suspicious": "We can't confirm this is real — treat it as unsafe until you verify it.",
        "clear": "No red flags found — still confirm on the official site yourself.",
    }[verdict["verdict"]]
    st.markdown(
        f'<div class="verdict-banner {css}">'
        f'<div class="vb-title">{title}</div>'
        f'<div class="vb-summary">{summary}</div>'
        f'<div class="vb-conf">Confidence: {verdict["confidence"]}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_what_to_do(verdict: dict) -> None:
    v = verdict["verdict"]
    st.markdown("**✅ What to do**")
    if v == "scam":
        st.markdown(
            "- **Do not engage.** Do not reply, click the link, send money, or enter any "
            "details (bank, BVN, NIN, password, OTP).\n"
            "- **Report it.** NITDA-CERRT — `cerrt@nitda.gov.ng`, **+234 817 877 4580**, "
            "[www.cerrt.ng](https://www.cerrt.ng). For fake student-loan offers, report to "
            "**NELFUND** and the **Nigeria Police Cybercrime Unit**.\n"
            "- **If you already shared details:** change your email/bank/NIN passwords now and "
            "tell your bank to secure the account — fraudsters often act within 24–48 hours."
        )
    elif v == "suspicious":
        st.markdown(
            "- **Treat it as unsafe until you confirm it.** Don't enter details or pay anything yet.\n"
            "- **Verify it yourself:** open the issuer's **official website by typing the address "
            "yourself** (don't trust the forwarded link), and cross-check the offer and any "
            "deadline there. A real opportunity never needs your bank login or a fee to 'release' funds.\n"
            "- If you can't confirm it on an official source, **don't act on it**."
        )
    else:  # clear
        st.markdown(
            "- **No red flags found — but this is not a guarantee it's real.** "
            "Always confirm on the **official website** (type the address yourself) before acting.\n"
            "- Never pay a fee to apply, and never share your bank login, BVN, NIN, password, or OTP.\n"
            "- If anything later asks for those, stop and treat it as suspicious."
        )


def render_hero() -> None:
    with st.form("scam_check"):
        pasted = st.text_area(
            "Paste the message, link, or offer you're unsure about:",
            value=SCAM_EXAMPLE,
            height=170,
        )
        run = st.form_submit_button("🛡️ Check if it's real", type="primary",
                                    use_container_width=True)

    if not run:
        st.caption(STANDING_CAPTION)
        return
    if not pasted.strip():
        st.warning("Please paste a message, link, or offer first.")
        return

    knowledge = load_knowledge_or_stop()
    with st.spinner("Checking against known scams, red-flag heuristics, and the web…"):
        try:
            result = verifier.verify_opportunity(pasted.strip(), knowledge)
        except ContentFilterError as e:
            st.warning(f"⚠️ {e} This sometimes happens with forwarded scam text — it "
                       "doesn't mean the message is safe. When in doubt, treat it as "
                       "unsafe: don't click links, pay fees, or share bank/BVN/NIN details, "
                       "and confirm on the official website yourself.")
            return
        except ModelError as e:
            st.warning(f"The checker could not reach the model. {e} "
                       "If you've hit the daily free-tier limit, try again tomorrow — "
                       "previously checked messages are served from cache.")
            return

    verdict = result["verdict"]

    # 1 — Verdict banner
    render_verdict_banner(verdict)
    badges = badge(result["all_cached"]) + web_tag(result["searched_web"])
    if badges.strip():
        st.markdown(badges, unsafe_allow_html=True)

    # 2 — Our reasoning (evidence weighed, not keywords fired)
    if verdict.get("reasoning"):
        st.markdown("**🧠 Our reasoning**")
        st.markdown(f"> {verdict['reasoning']}")

    st.markdown("**🚩 Red flags we checked**")
    if verdict["red_flags"]:
        st.markdown("\n".join(f"- ✅ {flag}" for flag in verdict["red_flags"]))
    else:
        st.markdown("- No strong red flags fired in the message we could read.")
    ex = result["extraction"]

    # 3 — Evidence sources: KB match (Foundry IQ) and live confirmation (Tavily)
    scam_match = verdict["known_scam_match"]
    legit_match = verdict.get("known_legit_match")
    if scam_match:
        st.markdown("**📌 Matches a documented scam in our verified knowledge base**")
        st.error(f"**{scam_match.get('title','Known scam')}** — "
                 f"[official source]({scam_match.get('source_url','')})  \n"
                 f"{scam_match.get('source_url','')}")
    elif legit_match:
        st.markdown("**✅ Matches a verified program in our knowledge base**")
        st.success(f"**{legit_match.get('title','Verified program')}** — "
                   f"[official link]({legit_match.get('source_url','')})  \n"
                   f"{legit_match.get('source_url','')}")

    live = verdict.get("live_confirmation")
    if live:
        icon = {"confirms_real": "🌐 ✅", "confirms_scam": "🌐 🚩",
                "inconclusive": "🌐 ❔"}.get(live["status"], "🌐")
        st.markdown(f"**{icon} Live verification (web-sourced)**")
        st.caption("Independently checked on the web — lower trust than our verified "
                   "knowledge base, but it explains the verdict. Confirm on the official site.")
        body = live["statement"] or ""
        if live.get("deadline"):
            body += f"\n\n**Deadline seen:** {live['deadline']}"
        if live.get("url"):
            body += f"\n\n{live['url']}"
        (st.success if live["status"] == "confirms_real"
         else st.error if live["status"] == "confirms_scam" else st.info)(body)
    elif verdict["web_findings"]:
        st.markdown("**🌐 Found online (unverified)**")
        st.caption(LIVE_CAPTION)
        st.warning("\n".join(
            f"- {w.get('finding','')}" + (f" — {w['url']}" if w.get("url") else "")
            for w in verdict["web_findings"]
        ))

    # Non-silent degradation: a live check was attempted but the tier is broken
    # (e.g. invalid key). Say so, rather than passing the verdict off as live-confirmed.
    if result.get("live_error"):
        st.markdown("**🌐 ⚠️ Live verification couldn't run**")
        st.warning(result["live_error"] + "  \nThis verdict rests on the verified "
                   "knowledge base and structural reasoning only — it was **not** "
                   "live-confirmed on the web.")

    # 4 — What to do
    render_what_to_do(verdict)

    # 4 — A real alternative (verified, cited)
    st.markdown("**🧭 Here's a real alternative**")
    st.success(result["alternative"])

    with st.expander("🔍 What we read from your message"):
        st.json(ex)
        if "_parse_note" in ex:
            st.code(result["extraction_raw"])

    st.divider()
    st.caption(STANDING_CAPTION)


# ---------------------------------------------------------------------------
# ADVISOR MODE — the original four-step learning-path pipeline (unchanged)
# ---------------------------------------------------------------------------

ADVISOR_EXAMPLE = (
    "I'm 19, in Aba. I finished secondary school, I have a small Android phone and "
    "sometimes my neighbour's laptop. Power goes out most days, data is expensive. "
    "I know basic computer use and a little HTML. I want to get into cloud "
    "engineering / SRE. I have no bank card that works for foreign payments.")


def render_advisor() -> None:
    with st.form("intake"):
        profile = st.text_area(
            "Tell us about yourself — level, skills, goal, and your constraints "
            "(money, power, bandwidth, payment access):",
            value=ADVISOR_EXAMPLE,
            height=160,
        )
        run = st.form_submit_button("Run the Compass", type="primary",
                                    use_container_width=True)

    if run and not profile.strip():
        st.warning("Please enter a short profile first.")
        return
    if not run:
        return

    knowledge = load_knowledge_or_stop()
    live_mode = search.is_available()

    # Step 1 — Assess
    with st.spinner("Step 1/4 — Assessing your profile…"):
        try:
            assessment, raw_assess, c1 = pipeline.assess(profile.strip())
        except ModelError as e:
            st.warning(f"The Assess step could not reach the model. {e} "
                       "If you've hit the daily free-tier limit, try again tomorrow — "
                       "previously seen profiles are served from cache.")
            return
    with st.expander("🔍 Step 1 — Assess", expanded=True):
        st.markdown(step_header(1, "Assess", c1), unsafe_allow_html=True)
        st.caption("What the agent understood about you.")
        st.json(assessment)
        if "_parse_note" in assessment:
            st.code(raw_assess)

    # Step 2 — Plan (may consult live web search for current resources)
    with st.spinner("Step 2/4 — Building your 90-day plan…"):
        try:
            plan_text, c2, plan_searched = pipeline.plan_with_search(assessment, knowledge)
        except ModelError as e:
            st.warning(f"The Plan step failed: {e}")
            return
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
            match_text, c3, _ = pipeline.match(assessment, knowledge)
        except ModelError as e:
            st.warning(f"The Match step failed: {e}")
            return
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
        st.caption("Recommendations come ONLY from the vetted knowledge base, with citations. "
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
            return
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


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

if mode.startswith("🛡️"):
    render_hero()
else:
    render_advisor()

st.divider()
technical_details()
st.caption("Day Zero Compass never invents scholarships, vouchers, deadlines, or links, "
           "and never gives a false 'all-clear'. Verified recommendations and known-scam "
           "matches come from its human-checked knowledge base, fully cited; anything found "
           "by live web search is always marked unverified. Always confirm on the official "
           "website before acting.")
