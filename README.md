# 🛡️ Day Zero Compass

**Is this opportunity real?** Paste any "opportunity" you got on WhatsApp — a scholarship, grant, job, or link — and find out if it's real or a scam, *why*, and what to do instead. Built for the real plague of forwarded scams hitting early-stage tech learners in underserved Southeast Nigeria.

A grounded, cited, scam-aware AI guidance agent — starting from day zero.

*Built for the Microsoft Agents League Hackathon (Creative Apps track).*

## Two modes

| Mode | What it does |
|---|---|
| 🛡️ **Check if an opportunity is real** *(default — hero)* | Paste a suspicious message/link/offer and get a clear verdict (🔴/🟠/🟢) with the specific red flags, what to do, and a real verified alternative. |
| 🧭 **Plan my learning path** *(secondary)* | The original Assess → Plan → Match → Verify advisor that builds a grounded, cited 90-day learning path. |

## The problem

A motivated 19-year-old in Aba or Owerri who wants to get into cloud engineering faces three walls at once:

1. **No map.** Generic "learn to code" advice ignores their reality: shared devices, daily power cuts, expensive data, no money for courses.
2. **Invisible access barriers.** Real ones — for example, Pearson VUE's payment flow rejecting many Nigerian debit cards, which silently blocks students from sitting AWS certification exams even when they've earned a voucher.
3. **Scams.** Fake scholarships and pay-to-apply "opportunities" specifically target exactly this population.

Generic chatbots make this *worse*: they hallucinate scholarships that don't exist and deadlines that were never real. For a student whose entire budget is one application fee, a hallucinated opportunity isn't an inconvenience — it's a catastrophe.

## 🛡️ Scam check (hero feature)

The headline use case. A learner pastes the message, link, or offer they're unsure about into one box. The agent then runs three focused, cached GPT-4o steps (reusing the same model client, disk cache, capped tool loop, and Tavily search as the advisor):

1. **Extract** — parses the pasted text into strict JSON: the claimed offer, the apparent sender/brand, any URL/domain, and crucially *what it asks you to do or provide* (bank details, BVN, NIN, password, OTP, an upfront fee, click a link…). It invents nothing.
2. **Check** — assesses the extraction against three sources: the **known scams in `data/knowledge.json`** (e.g. the fake Tinubu N50,000 grant, fake NELFUND portals), **scam heuristics** (requests for sensitive data, upfront fee to "release" funds, urgency/"reopening now", unofficial/look-alike domain, government/brand impersonation, forwarded-chain signals), and an **optional live web cross-check** (Tavily — the unverified tier, always labeled).
3. **Verdict + real alternative** — returns one of three verdicts with reasons, confidence, and a red-flags checklist, then redirects the user to the closest **verified, free** opportunity from the knowledge base (eligibility-gated, cited).

### The three-verdict model

- 🔴 **LIKELY A SCAM** — matches a known scam or hits strong red flags. Lists the specific flags, **cites the known-scam `source_url`**, and tells the user not to engage and how to report it (NITDA-CERRT: `cerrt@nitda.gov.ng`, +234 817 877 4580, [www.cerrt.ng](https://www.cerrt.ng); for loans, NELFUND + Police Cybercrime).
- 🟠 **SUSPICIOUS / CAN'T CONFIRM** — some red flags or unverifiable. Tells the user to treat it as unsafe until confirmed, and exactly how to verify it themselves. **Chosen whenever the call is uncertain** — caution wins.
- 🟢 **NO RED FLAGS FOUND** — no known-scam match and no strong red flags.

### The never-give-false-reassurance rule (the whole point)

A confident green light on a real scam is the worst possible failure, so:

- 🟢 **always** reads as *"no red flags found — still confirm on the official site yourself,"* and **never** as "this is safe / legit / go ahead." This is enforced both in the `SCAM_VERDICT` prompt **and** in code: `agent/verifier._normalize_verdict()` scrubs any reassuring wording ("safe", "legit", "genuine"…) from a green summary and forces the safe phrasing.
- The agent **never fabricates a scam** either — it won't invent red flags that aren't in the text; when torn between 🟠 and 🟢 it picks 🟠.
- The code-side backstop also **downgrades** any 🟢 that somehow carries red flags or a known-scam match (→ 🟠 or 🔴) — it only ever moves toward caution, never toward reassurance.

If there's no Tavily key (or search fails/quota hits), the check runs on the knowledge base + heuristics only, with a calm notice. Every model call and search is disk-cached, so a demo replay costs zero quota.

## Grounding: Foundry IQ (Azure AI Search agentic retrieval)

The verified knowledge layer is **Foundry IQ — Azure AI Search**. On first run, `agent/foundry_iq.py` indexes `data/knowledge.json` (opportunities + pitfalls) into an Azure AI Search index, registers it as a **Knowledge Source**, and — when an Azure OpenAI model is configured — builds a **Knowledge Base** for agentic retrieval. Both the advisor's **Match** step and the scam-verifier's **Check** step now pull their verified grounding through `kb_retrieve(query)`, which returns cited `{content, source_url, id}` results, instead of reading the JSON file directly.

Retrieval degrades through three tiers so the app **never breaks**:

1. **`foundry-agentic`** — Knowledge Base agentic retrieval (LLM-planned, needs an Azure OpenAI model).
2. **`foundry-search`** — semantic/keyword search over the Azure AI Search index (works with just the search endpoint + key).
3. **`local`** — reads `data/knowledge.json` directly (the original behavior).

If `AZURE_SEARCH_ENDPOINT` / `AZURE_SEARCH_API_KEY` are missing or any Azure call fails, retrieval falls back to the local tier with a calm notice — the deployed grounded version is the safety net. Config is read from env first, then `st.secrets` (same pattern as `GITHUB_TOKEN`). Indexing runs once per `knowledge.json` change, and every retrieval is disk-cached, so demo replays cost zero Azure quota. The **verified vs. amber "Live web" two-tier UI and the citation discipline are unchanged** — Foundry IQ only swaps *where* the verified tier is retrieved from.

```bash
export AZURE_SEARCH_ENDPOINT=https://<your-service>.search.windows.net
export AZURE_SEARCH_API_KEY=<admin-key>
# optional — enables the agentic Knowledge Base tier:
export AZURE_OPENAI_ENDPOINT=https://<your-aoai>.openai.azure.com
export AZURE_OPENAI_DEPLOYMENT=<chat-model-deployment>
export AZURE_OPENAI_API_KEY=<aoai-key>
```

## How the advisor works

In **Plan my learning path** mode, the student enters a short free-form profile. The agent then runs **four visible, sequential steps** — each a separate GPT-4o call with its own focused system prompt:

| Step | What it does |
|---|---|
| 🔍 **Assess** | Parses the profile into structured JSON: level, skills, target track, and constraints (money, power, bandwidth, payment access). Extraction only — no advice, no invention. |
| 🗺️ **Plan** | Produces a sequenced, realistic next-90-days learning path tuned to the level and constraints (free, low-bandwidth resources preferred). |
| 🎯 **Match** | Recommends opportunities **only from the verified knowledge base** — a human-checked list of vouchers, scholarships, and resources retrieved via **Foundry IQ (Azure AI Search)** — citing each entry's `id` and `source_url`, and gating eligibility-restricted entries (e.g. student-only offers) on what the person actually stated. If nothing fits: "No verified match found." May then add a **separate, amber-flagged "Live" tier** of web-search finds — never mixed with the verified tier. |
| 🛡️ **Verify** | A safety pass: surfaces known scams and access pitfalls relevant to this student (with documented workarounds), screens every Live-tier web result against scam heuristics, and teaches them how to verify any opportunity themselves. |

![Architecture](architecture.png)

## Live web search with a verification spine

The agent can call a real `web_search` tool (Tavily) during the Plan and Match steps, via GPT-4o function calling. To keep the no-fabrication guarantee intact, everything the user sees lives in one of **two strictly separated tiers**:

- ✅ **Verified tier** — entries from `data/knowledge.json`, human-checked, shown in green with `id` + `source_url` citations. This is the only tier ever presented as trusted.
- 🌐 **Live tier** — web-search results, shown in amber, always labeled *"found online — verify yourself before acting"*, with the result URL. The Verify step screens every live result against scam heuristics (payment/bank-detail requests, look-alike domains, urgency language, brand/government impersonation) and flags suspicious ones with a reason.

A web result is **never** rendered with verified styling, and if the tiers conflict, the verified tier wins. Tool calls are hard-capped at 2 searches per step, and both search results and model calls are disk-cached. If `TAVILY_API_KEY` is missing or search fails, the app falls back cleanly to the grounded knowledge-base-only behavior with a calm notice — the deployed grounded version is the safety net.

## What this agent will NOT do

This is the core of the project:

- ❌ It will **never invent** a scholarship, voucher, deadline, or URL. The Match and Verify steps are given *only* the entries in the human-verified knowledge file — the model is never asked an open-ended "what opportunities exist?" question.
- ✅ Every recommendation **cites its source** (`id` + `source_url` from the knowledge file).
- 🙅 If nothing in the knowledge base fits, it **says so plainly** instead of filling the gap.
- 🌐 It **never presents an unverified web result as confirmed** — live-search finds are always amber-flagged, URL-attributed, and scam-screened before display.
- 🎓 It **never recommends eligibility-gated offers** (e.g. student-only programs) to someone who gave no signal they qualify — at most a conditional "if you're a student…" pointer.
- 🔎 It always ends with **"verify it yourself"** guidance — official domains only, never pay to apply.

This is enforced in the system prompts **and** in code: the Match and verifier Check steps are grounded exclusively in the verified knowledge base — retrieved via **Foundry IQ (Azure AI Search)**, or from `data/knowledge.json` directly when Azure isn't configured. Either way the model only ever sees a fixed, human-checked candidate list.

## Stack

Deliberately boring and reliable:

- **Python + Streamlit** — UI and orchestration
- **`openai` SDK → GitHub Models** (`https://models.github.ai/inference`, model `openai/gpt-4o`) — free tier
- **Foundry IQ — Azure AI Search** (`azure-search-documents`) — agentic retrieval over the indexed knowledge base, with citations; optional (`AZURE_SEARCH_ENDPOINT` / `AZURE_SEARCH_API_KEY`), with clean fallback to local `knowledge.json` grounding when absent
- **Tavily** (`tavily-python`) — real web search as a GPT-4o tool, free tier; optional (`TAVILY_API_KEY`), with clean fallback to grounded-only mode when absent
- **Disk cache** (`.cache/`, SHA-256 of each prompt and search query) — every model call *and* web search is cached, so the demo re-runs without burning the ~50 req/day free-tier quota. A "served from cache" badge shows when a result is cached.
- **`data/knowledge.json`** — the human-verified grounding file

No frameworks, no vector DB, no containers.

**Built with Microsoft:** [GitHub Copilot](https://github.com/features/copilot) for AI-assisted development, and [GitHub Models](https://docs.github.com/en/github-models) for runtime inference (GPT-4o) — both Microsoft.

## Run it locally

```bash
git clone <this-repo> && cd day-zero-compass
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GITHUB_TOKEN=<your-token>   # see below
export TAVILY_API_KEY=<optional>   # enables the Live web-search tier; omit for grounded-only mode
streamlit run app.py
```

### Getting a GitHub Models token

1. Go to GitHub → **Settings → Developer settings → Fine-grained personal access tokens**.
2. Create a token with the **`models:read`** permission (under Account permissions → Models).
3. `export GITHUB_TOKEN=github_pat_...`
4. Sanity-check it: `python test_model.py` should print a one-line model response.

On Streamlit Community Cloud, set `GITHUB_TOKEN` in the app's **Secrets** instead.

> **Rate limits:** GitHub Models' free tier allows roughly 50 requests/day. Day Zero Compass caches every response on disk, so repeated runs of the same profile cost zero quota.

## Knowledge base

`data/knowledge.json` holds the verified opportunities and known pitfalls. Every entry carries a `source_url` and a `verified_on` date. **Entries are added by a human after checking the issuer's official site** — that manual verification step is a feature, not a gap.
