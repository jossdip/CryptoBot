from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseStrategy(ABC):
    """
    Abstract base class for all strategies.
    Standardizes context parsing and opportunity detection interface.
    """

    def __init__(self, broker) -> None:
        self.broker = broker

    @abstractmethod
    def detect_opportunities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Detect trading opportunities based on the provided context.
        Must return a list of opportunity dicts.
        """
        pass

    def parse_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Helper to extract common market data from context safely.
        Returns a structured dict with prices, sentiment, volume, etc.
        """
        # 1. Extract primary symbol and price
        prices = context.get("prices", {})
        symbol = next(iter(prices.keys()), None)
        mid_price = 0.0
        
        if symbol:
            # Try hyperliquid price first, then average
            p_map = prices[symbol]
            if isinstance(p_map, dict):
                mid_price = float(p_map.get("hyperliquid", 0.0))
                if mid_price <= 0:
                    # Fallback to any valid price
                    valid_prices = [float(v) for v in p_map.values() if float(v) > 0]
                    if valid_prices:
                        import statistics
                        mid_price = statistics.median(valid_prices)
        
        # 2. Extract Sentiment
        sentiment = context.get("sentiment", {})
        reddit_score = float(sentiment.get("reddit", {}).get("score", 0.0))
        twitter_score = float(sentiment.get("twitter", {}).get("score", 0.0))
        polymarket_score = float(sentiment.get("polymarket", {}).get("score", 0.0))
        
        # 3. Extract Market Data
        market = context.get("market", {})
        volumes = market.get("volumes", {})
        volume = float(volumes.get(symbol, 0.0)) if symbol else 0.0
        
        funding_rates = market.get("funding_rates", {})
        funding_rate = float(funding_rates.get(symbol, 0.0)) if symbol else 0.0

        volatility_map = market.get("volatility", {})
        volatility = float(volatility_map.get(symbol, 0.01)) if symbol else 0.01
        
        return {
            "symbol": symbol,
            "mid_price": mid_price,
            "sentiment": {
                "reddit": reddit_score,
                "twitter": twitter_score,
                "polymarket": polymarket_score,
                "combined": (reddit_score + twitter_score + polymarket_score) / 3.0 # Simple average proxy
            },
            "market": {
                "volume": volume,
                "funding_rate": funding_rate,
                "volatility": volatility
            }
        }

