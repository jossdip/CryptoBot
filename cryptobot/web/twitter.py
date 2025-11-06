from __future__ import annotations

from typing import List, Dict
import os

try:
    import httpx
except Exception:
    httpx = None  # type: ignore


def fetch_tweets(query: str, limit: int = 50) -> List[Dict]:
    """Fetch recent tweets using Twitter API v2 recent search.

    Requires TWITTER_BEARER_TOKEN in env.
    Returns [] if token missing, httpx missing, or on error.
    """
    if httpx is None:
        return []
    token = os.getenv("TWITTER_BEARER_TOKEN", "").strip()
    if not token:
        return []
    url = "https://api.twitter.com/2/tweets/search/recent"
    params = {
        "query": query,
        "max_results": str(max(10, min(100, int(limit)))),
        "tweet.fields": "text,created_at,lang",
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=10.0, headers=headers) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("data", []) if isinstance(data, dict) else []
            out: List[Dict] = []
            for it in items:
                out.append({
                    "text": it.get("text", ""),
                    "created_at": it.get("created_at", ""),
                    "lang": it.get("lang", ""),
                })
            return out
    except Exception:
        return []
