"""Foundry IQ grounding backend — Azure AI Search agentic retrieval.

Indexes data/knowledge.json (opportunities + pitfalls) into an Azure AI Search
index, registers it as a Knowledge Source, and (when an Azure OpenAI model is
configured) creates a Knowledge Base for agentic retrieval. kb_retrieve() then
pulls grounding with citations.

Retrieval degrades through three tiers, in order, so the app NEVER breaks:
  1. foundry-agentic  — Knowledge Base agentic retrieval (needs Azure OpenAI model)
  2. foundry-search   — semantic/keyword search on the Azure AI Search index
  3. local            — read data/knowledge.json directly (current behavior)

Config (env first, then st.secrets — same pattern as GITHUB_TOKEN):
  AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY          (required for any Foundry tier)
  AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT,
  AZURE_OPENAI_API_KEY (optional)                      (enables the agentic tier)

Every retrieval is disk-cached (.cache/, like the model/search caches) so demo
replays cost zero Azure quota. Indexing runs lazily on first use and only when
data/knowledge.json has changed since the last successful index.
"""

import hashlib
import json
import os
import threading
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
STATE_FILE = CACHE_DIR / "foundry_iq_state.json"

INDEX_NAME = "day-zero-compass-kb"
KNOWLEDGE_SOURCE_NAME = "day-zero-compass-source"
KNOWLEDGE_BASE_NAME = "day-zero-compass-base"
SEMANTIC_CONFIG = "default-semantic"
MAX_RESULTS = 8

# Index-build is attempted at most once per process; the on-disk state file makes
# it a no-op across restarts unless knowledge.json changed.
_INDEX_LOCK = threading.Lock()
_INDEX_ATTEMPTED = False


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def _secret(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if val:
        return val
    try:  # Streamlit Cloud stores secrets in st.secrets, not env vars.
        import streamlit as st

        return (st.secrets.get(name, "") or "").strip()
    except Exception:
        return ""


def _endpoint() -> str:
    return _secret("AZURE_SEARCH_ENDPOINT").rstrip("/")


def _key() -> str:
    return _secret("AZURE_SEARCH_API_KEY")


def is_available() -> bool:
    """True when the Foundry IQ (Azure AI Search) backend can be used at all."""
    return bool(_endpoint() and _key())


def _aoai_config() -> dict | None:
    """Azure OpenAI model config for the agentic tier, or None if not configured."""
    ep = _secret("AZURE_OPENAI_ENDPOINT").rstrip("/")
    dep = _secret("AZURE_OPENAI_DEPLOYMENT")
    if ep and dep:
        return {"endpoint": ep, "deployment": dep, "api_key": _secret("AZURE_OPENAI_API_KEY")}
    return None


def status() -> tuple[str, str]:
    """(kind, human message) describing the active grounding layer for the UI."""
    if not is_available():
        return ("local", "Grounding: local verified knowledge base. Set "
                "AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_API_KEY to ground via "
                "Foundry IQ (Azure AI Search).")
    tier = "agentic retrieval" if _aoai_config() else "semantic retrieval"
    return ("foundry", f"Grounding: Foundry IQ — Azure AI Search ({tier}), indexing the "
            "verified knowledge base with citations.")


# --------------------------------------------------------------------------- #
# Normalized documents — identical shape from Foundry or from local fallback,
# so the Match / Verdict prompts get the same grounding either way.
# --------------------------------------------------------------------------- #
def _norm_opportunity(o: dict) -> dict:
    parts = [o.get("summary", "")]
    if o.get("eligibility"):
        parts.append(f"Eligibility: {o['eligibility']}")
    if o.get("fits"):
        parts.append("Fits: " + ", ".join(o["fits"]))
    return {
        "id": o.get("id", ""),
        "kind": "opportunity",
        "title": o.get("title", ""),
        "content": "\n".join(p for p in parts if p),
        "source_url": o.get("source_url", ""),
        "secondary_source_url": o.get("secondary_source_url", ""),
    }


def _norm_pitfall(p: dict) -> dict:
    parts = [p.get("problem", "")]
    if p.get("workaround"):
        parts.append(f"Workaround: {p['workaround']}")
    if p.get("applies_to"):
        parts.append("Applies to: " + ", ".join(p["applies_to"]))
    return {
        "id": p.get("id", ""),
        "kind": "pitfall",
        "title": p.get("title", ""),
        "content": "\n".join(part for part in parts if part),
        "source_url": p.get("source_url", ""),
        "secondary_source_url": p.get("secondary_source_url", ""),
    }


def local_docs(knowledge: dict, kind: str | None = None) -> list[dict]:
    """Normalized docs straight from knowledge.json — the grounded fallback."""
    docs: list[dict] = []
    if kind in (None, "opportunity"):
        docs += [_norm_opportunity(o) for o in knowledge.get("opportunities", [])]
    if kind in (None, "pitfall"):
        docs += [_norm_pitfall(p) for p in knowledge.get("pitfalls", [])]
    return docs


def _all_docs(knowledge: dict) -> list[dict]:
    return local_docs(knowledge, None)


def _knowledge_hash(knowledge: dict) -> str:
    return hashlib.sha256(
        json.dumps(knowledge, sort_keys=True).encode("utf-8")
    ).hexdigest()


# --------------------------------------------------------------------------- #
# Indexing (lazy, once, idempotent)
# --------------------------------------------------------------------------- #
def _read_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write_state(state: dict) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _build_index(knowledge: dict) -> bool:
    """Create/refresh the index, knowledge source, and (if possible) knowledge base.

    Returns True if the index is ready with documents uploaded. Any failure
    returns False so callers fall back to local — no exception escapes.
    """
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        SearchableField, SearchFieldDataType, SearchIndex,
        SemanticConfiguration, SemanticField, SemanticPrioritizedFields, SemanticSearch,
        SimpleField,
    )

    cred = AzureKeyCredential(_key())
    index_client = SearchIndexClient(endpoint=_endpoint(), credential=cred)

    # source_url fields are SearchableField (retrievable by default) to avoid the
    # retrievable/hidden kwarg differences between SearchField helpers.
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SearchableField(name="kind", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchableField(name="source_url", type=SearchFieldDataType.String),
        SearchableField(name="secondary_source_url", type=SearchFieldDataType.String),
    ]
    semantic = SemanticSearch(configurations=[
        SemanticConfiguration(
            name=SEMANTIC_CONFIG,
            prioritized_fields=SemanticPrioritizedFields(
                title_field=SemanticField(field_name="title"),
                content_fields=[SemanticField(field_name="content")],
                keywords_fields=[SemanticField(field_name="kind")],
            ),
        )
    ])
    index = SearchIndex(name=INDEX_NAME, fields=fields, semantic_search=semantic)
    index_client.create_or_update_index(index)

    search_client = SearchClient(endpoint=_endpoint(), index_name=INDEX_NAME, credential=cred)
    search_client.merge_or_upload_documents(documents=_all_docs(knowledge))

    # Knowledge source (points the Foundry IQ layer at our index). Best-effort —
    # if the SDK/service shape differs, semantic search on the index still works.
    try:
        from azure.search.documents.indexes.models import (
            SearchIndexKnowledgeSource, SearchIndexKnowledgeSourceParameters,
        )
        ks = SearchIndexKnowledgeSource(
            name=KNOWLEDGE_SOURCE_NAME,
            search_index_parameters=SearchIndexKnowledgeSourceParameters(
                search_index_name=INDEX_NAME,
                source_data_fields=["id", "kind", "title", "content", "source_url"],
                semantic_configuration_name=SEMANTIC_CONFIG,
            ),
        )
        index_client.create_or_update_knowledge_source(knowledge_source=ks)
    except Exception:
        pass  # source registration is optional; retrieval falls back to search

    # Knowledge base for agentic retrieval — only if an Azure OpenAI model exists.
    agentic = False
    aoai = _aoai_config()
    if aoai:
        try:
            from azure.search.documents.indexes.models import (
                KnowledgeBase, KnowledgeBaseAzureOpenAIModel, KnowledgeSourceReference,
            )
            from azure.search.documents.indexes.models import AzureOpenAIVectorizerParameters
            model = KnowledgeBaseAzureOpenAIModel(
                azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                    resource_url=aoai["endpoint"],
                    deployment_name=aoai["deployment"],
                    model_name=aoai["deployment"],
                    api_key=aoai["api_key"] or None,
                )
            )
            kb = KnowledgeBase(
                name=KNOWLEDGE_BASE_NAME,
                knowledge_sources=[KnowledgeSourceReference(name=KNOWLEDGE_SOURCE_NAME)],
                models=[model],
            )
            index_client.create_or_update_knowledge_base(knowledge_base=kb)
            agentic = True
        except Exception:
            agentic = False

    _write_state({"knowledge_hash": _knowledge_hash(knowledge), "agentic": agentic})
    return True


def ensure_indexed(knowledge: dict) -> bool:
    """Index on first use; no-op if knowledge.json is unchanged. Never raises."""
    global _INDEX_ATTEMPTED
    if not is_available():
        return False
    state = _read_state()
    if state.get("knowledge_hash") == _knowledge_hash(knowledge):
        return True
    with _INDEX_LOCK:
        if _INDEX_ATTEMPTED and _read_state().get("knowledge_hash") == _knowledge_hash(knowledge):
            return True
        _INDEX_ATTEMPTED = True
        try:
            return _build_index(knowledge)
        except Exception:
            return False


# --------------------------------------------------------------------------- #
# Retrieval
# --------------------------------------------------------------------------- #
def _cache_path(query: str, kind: str | None, mode: str) -> Path:
    payload = json.dumps({"q": query, "kind": kind, "mode": mode, "index": INDEX_NAME},
                         sort_keys=True)
    return CACHE_DIR / f"foundryiq-{hashlib.sha256(payload.encode('utf-8')).hexdigest()}.json"


def _agentic_retrieve(query: str, kind: str | None) -> list[dict]:
    """Knowledge Base agentic retrieval. Returns normalized docs or [] on any issue."""
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
    from azure.search.documents.knowledgebases.models import (
        KnowledgeBaseRetrievalRequest, KnowledgeRetrievalSemanticIntent,
    )

    client = KnowledgeBaseRetrievalClient(
        endpoint=_endpoint(), knowledge_base_name=KNOWLEDGE_BASE_NAME,
        credential=AzureKeyCredential(_key()),
    )
    req = KnowledgeBaseRetrievalRequest(
        intents=[KnowledgeRetrievalSemanticIntent(search=query)],
        include_activity=False,
    )
    resp = client.retrieve(req)

    docs: list[dict] = []
    for ref in (getattr(resp, "references", None) or []):
        data = getattr(ref, "source_data", None) or {}
        if not isinstance(data, dict) or not data.get("id"):
            continue
        if kind and data.get("kind") and data["kind"] != kind:
            continue
        docs.append({
            "id": data.get("id", ""), "kind": data.get("kind", ""),
            "title": data.get("title", ""), "content": data.get("content", ""),
            "source_url": data.get("source_url", ""),
            "secondary_source_url": data.get("secondary_source_url", ""),
        })
    return docs


def _search_retrieve(query: str, kind: str | None) -> list[dict]:
    """Semantic search on the index (keyword fallback if semantic isn't enabled)."""
    from azure.core.credentials import AzureKeyCredential
    from azure.core.exceptions import HttpResponseError
    from azure.search.documents import SearchClient

    client = SearchClient(endpoint=_endpoint(), index_name=INDEX_NAME,
                          credential=AzureKeyCredential(_key()))
    flt = f"kind eq '{kind}'" if kind else None
    select = ["id", "kind", "title", "content", "source_url", "secondary_source_url"]

    def _run(text: str, semantic: bool):
        try:
            if semantic:
                return list(client.search(
                    search_text=text, query_type="semantic",
                    semantic_configuration_name=SEMANTIC_CONFIG,
                    filter=flt, select=select, top=MAX_RESULTS))
            return list(client.search(search_text=text, filter=flt, select=select,
                                      top=MAX_RESULTS))
        except HttpResponseError:
            # Semantic ranker may be unavailable on the tier — plain search.
            return list(client.search(search_text=text, filter=flt, select=select,
                                      top=MAX_RESULTS))

    rows = _run(query or "*", semantic=True)
    # The verified candidate set is small and curated. Semantic re-ranks only what
    # keyword recall finds, so a narrow query with no lexical overlap can return
    # nothing. In that case return the full set via "*" instead of dropping to the
    # local tier — grounding stays on Foundry IQ and the prompt does its own selection.
    if not rows:
        rows = _run("*", semantic=False)
    return [{k: r.get(k, "") for k in select} for r in rows]


def kb_retrieve(query: str, kind: str | None = None) -> tuple[list[dict], bool, str]:
    """Retrieve grounding from Foundry IQ. Returns (docs, from_cache, mode).

    mode is 'foundry-agentic' or 'foundry-search'. Returns ([], False, '') when the
    backend is unavailable or fails — callers then fall back to local docs.
    """
    if not is_available():
        return [], False, ""

    agentic_ready = _read_state().get("agentic", False) and bool(_aoai_config())
    mode = "foundry-agentic" if agentic_ready else "foundry-search"

    path = _cache_path(query, kind, mode)
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            return cached["docs"], True, cached["mode"]
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    try:
        docs = _agentic_retrieve(query, kind) if agentic_ready else []
        if not docs:
            docs = _search_retrieve(query, kind)
            mode = "foundry-search"
    except Exception:
        return [], False, ""

    if not docs:
        return [], False, ""

    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps({"query": query, "mode": mode, "docs": docs},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return docs, False, mode


def retrieve(query: str, kind: str | None, knowledge: dict) -> tuple[list[dict], str, bool]:
    """Grounding with mandatory fallback. Returns (docs, source, from_cache).

    source is 'foundry-agentic', 'foundry-search', or 'local'. Indexing is
    triggered lazily on first use. The local tier guarantees the app never breaks.
    """
    if is_available():
        if ensure_indexed(knowledge):
            docs, from_cache, mode = kb_retrieve(query, kind)
            if docs:
                return docs, mode, from_cache
    return local_docs(knowledge, kind), "local", True
