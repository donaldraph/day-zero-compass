"""GitHub Models client with a mandatory disk cache.

Every model call goes through cached_chat(): the prompt is hashed and the
response stored in .cache/ as JSON, so re-running the demo never burns the
~50 requests/day free-tier quota.
"""

import hashlib
import json
import os
from pathlib import Path

from openai import OpenAI

ENDPOINT = "https://models.github.ai/inference"
MODEL = "openai/gpt-4o"
CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


class ModelError(Exception):
    """Raised when the model call fails and no cached result exists."""


def _get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        # Streamlit Cloud stores secrets in st.secrets, not env vars.
        try:
            import streamlit as st

            token = st.secrets.get("GITHUB_TOKEN", "")
        except Exception:
            token = ""
    if not token:
        raise ModelError(
            "GITHUB_TOKEN is not set. Create a GitHub PAT with the "
            "models:read scope and export it as GITHUB_TOKEN."
        )
    return token


def _cache_key(system: str, user: str) -> str:
    payload = json.dumps({"model": MODEL, "system": system, "user": user}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _read_cache(key: str):
    path = _cache_path(key)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))["content"]
        except (json.JSONDecodeError, KeyError):
            return None
    return None


def _write_cache(key: str, content: str) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(key).write_text(
        json.dumps({"model": MODEL, "content": content}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cached_chat(system: str, user: str) -> tuple[str, bool]:
    """Run one chat completion. Returns (content, served_from_cache)."""
    key = _cache_key(system, user)
    cached = _read_cache(key)
    if cached is not None:
        return cached, True

    try:
        client = OpenAI(base_url=ENDPOINT, api_key=_get_token())
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        content = resp.choices[0].message.content or ""
    except ModelError:
        raise
    except Exception as exc:  # rate limit, network, auth — keep the app calm
        raise ModelError(f"Model call failed: {exc}") from exc

    _write_cache(key, content)
    return content, False
