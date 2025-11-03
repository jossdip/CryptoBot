from __future__ import annotations

from typing import Dict, List, Any, Optional

# Import signal collectors (not strategies, but signal sources)
try:
    from cryptobot.strategy.sentiment_reddit import SentimentRedditStrategy
    from cryptobot.strategy.sentiment_twitter import SentimentTwitterStrategy
    from cryptobot.strategy.sentiment_polymarket import SentimentPolymarketStrategy
    from cryptobot.llm.client import LLMClient
except ImportError:
    SentimentRedditStrategy = None  # type: ignore
    SentimentTwitterStrategy = None  # type: ignore
    SentimentPolymarketStrategy = None  # type: ignore
    LLMClient = None  # type: ignore


class MarketContextAggregator:
    def __init__(self, broker, llm_client: Optional[Any] = None, config: Optional[Any] = None) -> None:
        self.broker = broker
        self.llm_client = llm_client
        self.config = config
        # Initialize signal collectors (not trading strategies, but signal sources)
        if llm_client and LLMClient:
            self.reddit_collector = SentimentRedditStrategy(llm_client) if SentimentRedditStrategy else None
            self.twitter_collector = SentimentTwitterStrategy(llm_client) if SentimentTwitterStrategy else None
            self.polymarket_collector = SentimentPolymarketStrategy(llm_client) if SentimentPolymarketStrategy else None
        else:
            self.reddit_collector = None
            self.twitter_collector = None
            self.polymarket_collector = None

    def _get_prices(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        # Best-effort: use broker portfolio/ticker info if available; return stub
        out: Dict[str, Dict[str, float]] = {}
        for s in symbols:
            out[s] = {"hyperliquid": 30000.0}
        return out

    def _get_volumes(self, symbols: List[str]) -> Dict[str, float]:
        return {s: 0.0 for s in symbols}

    def _get_funding_rates(self, symbols: List[str]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for s in symbols:
            try:
                out[s] = float(self.broker.get_funding_rate(s))
            except Exception:
                out[s] = 0.0
        return out

    def _get_orderbooks(self, symbols: List[str]) -> Dict[str, Any]:
        return {s: {"bids": [], "asks": []} for s in symbols}

    def _get_sentiment(self) -> Dict[str, Any]:
        """
        Collect sentiment signals from all sources (Reddit, Twitter, Polymarket).
        These are SIGNAL SOURCES, not trading strategies.
        They are used by ALL trading strategies to evaluate confidence and timing.
        """
        sentiment: Dict[str, Any] = {
            "reddit": {"score": 0.0, "confidence": 0.0},
            "twitter": {"score": 0.0, "confidence": 0.0},
            "polymarket": {"score": 0.0, "confidence": 0.0},
        }
        
        # Collect Reddit signals
        if self.reddit_collector and self.config:
            try:
                subreddits = getattr(self.config.sentiment.reddit, "subreddits", [])
                if subreddits:
                    reddit_signal = self.reddit_collector.detect_opportunities(subreddits)
                    sentiment["reddit"] = {
                        "score": float(reddit_signal.get("score", 0.0)),
                        "confidence": float(reddit_signal.get("confidence", 0.0)),
                    }
            except Exception:
                pass
        
        # Collect Twitter signals
        if self.twitter_collector and self.config:
            try:
                keywords = getattr(self.config.sentiment.twitter, "keywords", [])
                if keywords:
                    twitter_signal = self.twitter_collector.detect_opportunities(keywords)
                    sentiment["twitter"] = {
                        "score": float(twitter_signal.get("score", 0.0)),
                        "confidence": float(twitter_signal.get("confidence", 0.0)),
                    }
            except Exception:
                pass
        
        # Collect Polymarket signals (highest confidence - real money bets)
        if self.polymarket_collector and self.config:
            try:
                keywords = getattr(self.config.sentiment.polymarket, "keywords", [])
                if keywords:
                    polymarket_signal = self.polymarket_collector.detect_opportunities(keywords)
                    sentiment["polymarket"] = {
                        "score": float(polymarket_signal.get("score", 0.0)),
                        "confidence": float(polymarket_signal.get("confidence", 0.0)),
                        "markets_count": int(polymarket_signal.get("markets_count", 0)),
                        "total_volume": float(polymarket_signal.get("total_volume", 0.0)),
                    }
            except Exception:
                pass
        
        return sentiment

    def _get_new_listings(self) -> List[Dict[str, Any]]:
        return []

    def _get_portfolio_state(self) -> Dict[str, Any]:
        pf = self.broker.get_portfolio()
        return pf.get("response", {}) if isinstance(pf, dict) else {}

    def build_context(
        self,
        symbols: List[str],
        include_sentiment: bool = True,
        include_orderbook: bool = False,
    ) -> Dict[str, Any]:
        return {
            "market": {
                "prices": self._get_prices(symbols),
                "volumes": self._get_volumes(symbols),
                "funding_rates": self._get_funding_rates(symbols),
                "orderbook_depths": self._get_orderbooks(symbols) if include_orderbook else {},
                "new_listings": self._get_new_listings(),
            },
            "sentiment": self._get_sentiment() if include_sentiment else {},
            "portfolio": self._get_portfolio_state(),
        }


