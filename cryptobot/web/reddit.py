from __future__ import annotations

from typing import List, Dict
import os

try:
    import httpx
except Exception:
    httpx = None  # type: ignore


def fetch_reddit_posts(subreddit: str, limit: int = 50) -> List[Dict]:
    """Fetch recent posts from a subreddit via the public JSON endpoint.

    Notes:
    - Uses Reddit's public JSON; heavy usage may be rate-limited. Provide a custom UA.
    - If httpx is not installed or an error occurs, return [].
    """
    if httpx is None:
        return []
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    params = {"limit": max(1, min(100, int(limit)))}
    headers = {
        "User-Agent": os.getenv("REDDIT_USER_AGENT", "cryptobot/0.1 (+https://github.com/)")
    }
    try:
        with httpx.Client(timeout=10.0, headers=headers) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            children = data.get("data", {}).get("children", []) if isinstance(data, dict) else []
            out: List[Dict] = []
            for c in children:
                d = c.get("data", {}) if isinstance(c, dict) else {}
                out.append({
                    "title": d.get("title", ""),
                    "body": d.get("selftext", "") or d.get("self_text", ""),
                    "url": d.get("url", ""),
                    "created_utc": d.get("created_utc", 0),
                })
            return out
    except Exception:
        return []
