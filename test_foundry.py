"""Live test for the Foundry IQ (Azure AI Search) grounding backend.

Indexes data/knowledge.json on first run, then confirms kb_retrieve returns
cited results from the knowledge base, and that the local fallback still works.

Usage:
  AZURE_SEARCH_ENDPOINT=... AZURE_SEARCH_API_KEY=... \\
  [AZURE_OPENAI_ENDPOINT=... AZURE_OPENAI_DEPLOYMENT=... AZURE_OPENAI_API_KEY=...] \\
  python test_foundry.py
"""

from agent import foundry_iq
from agent.pipeline import load_knowledge


def main():
    knowledge = load_knowledge()
    kind, msg = foundry_iq.status()
    print(f"Foundry IQ available: {foundry_iq.is_available()}  | layer: {kind}")
    print(f"Status: {msg}\n")

    if not foundry_iq.is_available():
        print("No Azure Search creds — exercising the LOCAL FALLBACK only.")
        docs = foundry_iq.local_docs(knowledge, "pitfall")
        print(f"local_docs(pitfall) -> {len(docs)} docs, all cited: "
              f"{all(d['source_url'] for d in docs)}")
        return

    print("Triggering indexing (first run creates the index + uploads docs)…")
    ok = foundry_iq.ensure_indexed(knowledge)
    print(f"Indexing succeeded: {ok}\n")

    for query, kind_ in [("Tinubu grant phishing scam", "pitfall"),
                         ("free Azure certification voucher for beginners", "opportunity")]:
        docs, from_cache, mode = foundry_iq.kb_retrieve(query, kind_)
        print(f"kb_retrieve({query!r}, {kind_!r}) -> mode={mode} cached={from_cache} "
              f"docs={len(docs)}")
        for d in docs[:3]:
            print(f"   • [{d['id']}] {d['title'][:60]}  <{d['source_url']}>")
        print(f"   all cited: {bool(docs) and all(d['source_url'] for d in docs)}\n")

    # Fallback sanity: retrieve() must always return docs (Foundry or local).
    docs, source, cached = foundry_iq.retrieve("scholarship", "opportunity", knowledge)
    print(f"retrieve() -> source={source} docs={len(docs)} (must be > 0)")
    print("\nDONE.")


if __name__ == "__main__":
    main()
