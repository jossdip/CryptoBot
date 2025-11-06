from __future__ import annotations

from typing import Dict, Any, List


class MomentumStrategy:
    def __init__(self, broker) -> None:
        self.broker = broker

    def detect_opportunities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Very light heuristic on price momentum from context (if available)
        prices: Dict[str, Dict[str, float]] = context.get("prices", {})
        if not prices:
            return []
        symbol = next(iter(prices.keys()))
        mid = float(prices[symbol].get("hyperliquid", 0.0))
        if mid <= 0:
            return []
        # Momentum signal proxy: if funding or sentiment bullish → long bias
        sentiment = context.get("sentiment", {})
        reddit = float(sentiment.get("reddit", {}).get("score", 0.0))
        twitter = float(sentiment.get("twitter", {}).get("score", 0.0))
        bias = reddit + twitter
        direction = "long" if bias >= 0 else "short"
        # Include recent price change pct for upstream scoring filters
        pcp_map: Dict[str, float] = context.get("price_change_pct", {})
        pcp = float(pcp_map.get(symbol, 0.0))
        return [{"symbol": symbol, "price": mid, "bias": bias, "direction": direction, "price_change_pct": pcp}]


