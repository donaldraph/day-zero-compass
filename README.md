# Day Zero Compass

I'm the founder of Day Zero, a builders' community in Southeast Nigeria. This region is marginalised. One of the things people here lack most is clarity and direction. And because real opportunity is scarce, scammers move in to take advantage of people hunting for it. Fake grants, fake scholarships, fake jobs, forwarded on WhatsApp, made to steal the little someone has.

That's why I built Day Zero Compass. I didn't build it only for the Day Zero community. It's for anyone looking for clarity and a real path forward.

*Built for the Microsoft Agents League Hackathon.*

## What it does

You paste in something you're unsure about. A scholarship, a grant, a job, a link someone forwarded you. It tells you whether it looks real or like a scam, why it thinks so, and what to do next. If the thing you were hoping for is real (free training, a certificate, a way into tech), it points you to a genuine version instead.

There's a second mode: a learning-path planner. You say where you're starting and what you're aiming at, and it writes a plan for your actual situation, not a generic "learn to code" list.

Two things it will not do:

- It never gives a clean bill of health. Green means "no red flags found, now go confirm on the official site yourself." It never says "this is safe."
- It never makes up an opportunity. No invented scholarships, no invented deadlines, no invented links.

## How it works

The scam check weighs three kinds of evidence.

**Structural reasoning.** It reads the message the way a careful person would. Who is it claiming to be? What domain is the link on? What is it actually asking you to hand over? Your BVN, your bank login, or an upfront "processing fee" is a real warning sign. Filling a form on an official microsoft.com or aka.ms page is not. This is what lets it catch a scam it has never seen. I tested it with a made-up "Shell Nigeria youth grant" that isn't in any list, and it called it red on the structure alone: lookalike domain, asks for your BVN, wants a fee first.

**Foundry IQ (Azure AI Search).** Documented scams and real, checked programs live in a small knowledge base. The agent retrieves from it to confirm a match and cite the source. If your message matches a known scam, it shows you where that's documented. If it matches a verified program, it says so and links the official page. The knowledge base is never the gate, though. Something being absent from it means nothing. The verdict still has to stand on the reasoning and the live check.

**Tavily live search.** When there's an official-looking link or a named program, it can go check the real web to see whether the program actually exists, and pull out a deadline if it finds one. Web findings are labelled as web findings. They count for less than the checked knowledge base, and a scholarship never comes from there.

Grounding on Foundry IQ is most of what keeps it honest. The model is never asked "what scholarships exist?" It gets handed a fixed, human-checked list and told to work from that. That's how we hold down hallucination.

If a key is missing or a service is down, it falls to the next layer and keeps going. No Tavily key: reasoning plus the knowledge base. No Azure: it reads the knowledge file directly. Every check is cached on disk, so running the same one again costs nothing.

### The three verdicts

- 🔴 **Likely a scam.** Matches a documented scam, or asks for sensitive data or a fee, or impersonates a brand, or sits on a fake domain. It tells you not to engage and how to report it (NITDA-CERRT: `cerrt@nitda.gov.ng`, +234 817 877 4580, www.cerrt.ng; for student loans, NELFUND and the Police Cybercrime unit).
- 🟠 **Can't confirm.** Some warning signs, or nothing solid to check against. Treat it as unsafe until you've confirmed it yourself.
- 🟢 **No red flags found.** Still go and confirm on the official site.

The green rule lives in code, not only the prompt. `agent/verifier._normalize_verdict()` strips words like "safe" and "legit" out of a green result, and a known-scam match forces the verdict to red. When it's torn, it picks amber, not green.

## The learning-path planner

This mode runs four steps you can watch: Assess, Plan, Match, Verify. It reads your level, skills, goal, and your real constraints (money, power, bandwidth, device, payment access, whether you're a student), then writes the plan around them. Power cuts and only a phone? It goes offline-first: download the modules while you have Wi-Fi, study them off-grid, take the free-voucher route so a card isn't needed. Own laptop and steady power? It moves faster. It cites real resources from the same checked knowledge base, and it won't show student-only offers unless you said you're a student.

## Why this exists

The barriers here aren't theory. Nigerian cards get rejected at exam checkout and for Azure. You can earn a voucher and still get stopped at the till, for no reason other than where your card is from.

It happened to me while I was building this. I went to create an Azure subscription and was told I wasn't eligible. That's the exact exclusion this project is about: people doing the work and getting shut out at the last step. So the tool leans on routes that don't need a foreign card, and it's honest about where the walls are.

## Microsoft IQ integration

The grounding layer is Foundry IQ on Azure AI Search. On first run, `agent/foundry_iq.py` indexes `data/knowledge.json` into a search index, registers it as a Knowledge Source, and (when an Azure OpenAI model is configured) builds a Knowledge Base for agentic retrieval. Both the scam Check step and the planner's Match step pull cited grounding through `kb_retrieve()`.

Retrieval has three tiers and falls through them so nothing breaks: the agentic Knowledge Base, then semantic search over the index, then the local JSON file. Re-indexing runs when the knowledge file changes, deletions included.

## Stack

Plain and unfashionable on purpose.

- Python and Streamlit for the app.
- GitHub Models (`openai/gpt-4o`) for the model calls, free tier.
- Azure AI Search (`azure-search-documents`) for the Foundry IQ grounding, with cited results.
- Tavily (`tavily-python`) for live web search, optional.
- A disk cache (`.cache/`, keyed by a hash of each prompt and query), so re-runs cost no quota.
- `data/knowledge.json`, the human-checked list of scams and real programs.

No vector database, no agent framework, no containers.

## Architecture

![Architecture](architecture.png)

## Run it locally

```bash
git clone <this-repo> && cd day-zero-compass
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GITHUB_TOKEN=<your-token>
streamlit run app.py
```

Optional keys turn on the other layers:

```bash
export AZURE_SEARCH_ENDPOINT=https://<your-service>.search.windows.net
export AZURE_SEARCH_API_KEY=<admin-key>
export TAVILY_API_KEY=<your-key>
# optional, enables the agentic Knowledge Base tier:
export AZURE_OPENAI_ENDPOINT=https://<your-aoai>.openai.azure.com
export AZURE_OPENAI_DEPLOYMENT=<chat-model-deployment>
export AZURE_OPENAI_API_KEY=<aoai-key>
```

Keys are read from the environment first, then Streamlit secrets, so the same names work locally and on Streamlit Cloud. For the GitHub Models token: GitHub, Settings, Developer settings, Fine-grained personal access tokens, give it the `models:read` permission, export it as `GITHUB_TOKEN`. The free tier is about 50 requests a day, which is why everything is cached.

## About Day Zero

Day Zero is a builders' community in Southeast Nigeria. We meet people where they are, often at zero, and help them build from there. This tool is one piece of that: a way to tell a real chance from someone trying to rob you, and to find the next real step.

**From Nothing, To Everything.**
