from __future__ import annotations

from typing import Dict, Any, List
from cryptobot.strategy.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    def detect_opportunities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Very light heuristic on price momentum from context (if available)
        data = self.parse_context(context)
        symbol = data["symbol"]
        mid = data["mid_price"]
        
        if not symbol or mid <= 0:
            return []
            
        # Momentum signal proxy: if funding or sentiment bullish → long bias
        sent = data["sentiment"]
        reddit = sent["reddit"]
        twitter = sent["twitter"]
        bias = reddit + twitter
        direction = "long" if bias >= 0 else "short"
        
        # Include recent price change pct for upstream scoring filters
        pcp_map: Dict[str, float] = context.get("price_change_pct", {})
        pcp = float(pcp_map.get(symbol, 0.0))
        
        return [{"symbol": symbol, "price": mid, "bias": bias, "direction": direction, "price_change_pct": pcp}]
