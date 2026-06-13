"""Tavily web search wrapper — disk-cached, degrades gracefully.

LIVE-tier sourcing only: results from here are NEVER verified and must always
be rendered in the amber "Live · unverified" tier. If TAVILY_API_KEY is
missing or the API fails, web_search() returns [] and the app falls back to
the grounded knowledge-base-only behavior — no exceptions escape this module.
"""

import hashlib
import json
import os
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"
MAX_RESULTS = 5


def _get_key() -> str:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        # Streamlit Cloud stores secrets in st.secrets, not env vars.
        try:
            import streamlit as st

            key = st.secrets.get("TAVILY_API_KEY", "")
        except Exception:
            key = ""
    return key


def is_available() -> bool:
    """True when live search can run (key present)."""
    return bool(_get_key())


def _cache_path(query: str) -> Path:
    payload = json.dumps({"tavily": query, "max_results": MAX_RESULTS}, sort_keys=True)
    return CACHE_DIR / f"search-{hashlib.sha256(payload.encode('utf-8')).hexdigest()}.json"


def web_search(query: str) -> tuple[list[dict], bool]:
    """Search the live web. Returns ([{title, url, snippet}], served_from_cache).

    Empty list means degraded (no key, API failure, or genuinely no results) —
    callers must keep working and show the calm grounded-only notice.
    """
    query = (query or "").strip()
    if not query:
        return [], False

    path = _cache_path(query)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))["results"], True
        except (json.JSONDecodeError, KeyError):
            pass

    if not is_available():
        return [], False

    try:
        from tavily import TavilyClient

        resp = TavilyClient(api_key=_get_key()).search(query=query, max_results=MAX_RESULTS)
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": (r.get("content") or "")[:500],
            }
            for r in resp.get("results", [])
        ]
    except Exception:
        return [], False

    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(
        json.dumps({"query": query, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results, False
