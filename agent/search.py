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


# Most recent live-search failure, or None if the last network attempt was fine.
# Lets callers tell a genuinely empty result apart from a misconfigured tier
# (key present but rejected) so the degradation is never silent.
_last_error: str | None = None


def last_error() -> str | None:
    return _last_error


def _classify(exc: Exception) -> str:
    blob = (str(getattr(exc, "args", "")) + " " + str(exc)).lower()
    if "unauthorized" in blob or "invalid api key" in blob or "401" in blob:
        return ("TAVILY_API_KEY is present but rejected (Unauthorized) — the key is "
                "invalid or expired. Live web verification is OFF until it's replaced.")
    return f"Live web search failed ({type(exc).__name__}); falling back to grounded only."


def status() -> tuple[bool, str]:
    """(live_ok, human message) for the technical panel and inline notices."""
    if not _get_key():
        return False, "off (optional) — no TAVILY_API_KEY set."
    if _last_error:
        return False, _last_error
    return True, "enabled (Tavily)."


def _cache_path(query: str) -> Path:
    payload = json.dumps({"tavily": query, "max_results": MAX_RESULTS}, sort_keys=True)
    return CACHE_DIR / f"search-{hashlib.sha256(payload.encode('utf-8')).hexdigest()}.json"


def web_search(query: str) -> tuple[list[dict], bool]:
    """Search the live web. Returns ([{title, url, snippet}], served_from_cache).

    Empty list means degraded (no key, API failure, or genuinely no results) —
    callers must keep working and show the calm grounded-only notice.
    """
    global _last_error
    query = (query or "").strip()
    if not query:
        return [], False

    path = _cache_path(query)
    if path.exists():
        try:
            results = json.loads(path.read_text(encoding="utf-8"))["results"]
            _last_error = None
            return results, True
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
    except Exception as exc:
        # Record WHY, so a present-but-invalid key never fails silently.
        _last_error = _classify(exc)
        return [], False

    _last_error = None

    CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(
        json.dumps({"query": query, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return results, False
