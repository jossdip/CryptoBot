from __future__ import annotations

from typing import Dict, Any, List

from cryptobot.llm.client import LLMClient
from cryptobot.web.twitter import fetch_tweets


class SentimentTwitterStrategy:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def analyze_sentiment(self, posts: List[str]) -> Dict[str, Any]:
        prompt = (
            f"Analyze crypto sentiment from these posts: {posts}\n"
            "Output JSON: {\"score\": -1.0 to 1.0, \"confidence\": 0.0-1.0}"
        )
        return self.llm.call(prompt=prompt, json_mode=True) or {"score": 0.0, "confidence": 0.0}

    def detect_opportunities(self, keywords: List[str]) -> Dict[str, Any]:
        texts: List[str] = []
        for kw in keywords:
            tweets = fetch_tweets(kw, limit=50)
            for tw in tweets:
                t = str(tw.get("text") or "")
                if t.strip():
                    texts.append(t.strip())
        # Deduplicate and downsample aggressively to reduce token usage
        seen = set()
        unique_texts: List[str] = []
        for t in texts:
            key = t[:96]
            if key not in seen:
                unique_texts.append(t[:200])
                seen.add(key)
            if len(unique_texts) >= 20:
                break
        sentiment = self.analyze_sentiment(unique_texts) if unique_texts else {"score": 0.0, "confidence": 0.0}
        return sentiment


