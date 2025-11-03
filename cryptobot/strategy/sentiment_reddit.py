from __future__ import annotations

from typing import Dict, Any, List

from cryptobot.llm.client import LLMClient
from cryptobot.web.reddit import fetch_reddit_posts


class SentimentRedditStrategy:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def analyze_sentiment(self, posts: List[str]) -> Dict[str, Any]:
        prompt = (
            f"Analyze crypto sentiment from these posts: {posts}\n"
            "Output JSON: {\"score\": -1.0 to 1.0, \"confidence\": 0.0-1.0}"
        )
        return self.llm.call(prompt=prompt, json_mode=True) or {"score": 0.0, "confidence": 0.0}

    def detect_opportunities(self, subreddits: List[str]) -> Dict[str, Any]:
        texts: List[str] = []
        for sr in subreddits:
            posts = fetch_reddit_posts(sr, limit=50)
            for p in posts:
                t = str(p.get("title") or "") + "\n" + str(p.get("body") or "")
                if t.strip():
                    texts.append(t[:500])
        sentiment = self.analyze_sentiment(texts[:50]) if texts else {"score": 0.0, "confidence": 0.0}
        return sentiment


