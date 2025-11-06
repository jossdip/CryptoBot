from __future__ import annotations

from typing import Dict, List, Any, Optional, Tuple
import os
import math

from cryptobot.data.ccxt_live import fetch_mark_price

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

    def _venues(self) -> List[str]:
        env = os.getenv("CB_VENUES", "").strip()
        if env:
            return [v.strip() for v in env.split(",") if v.strip()]
        # Defaults chosen for liquidity and availability
        return ["binance", "okx", "bybit"]

    def _ccxt_keys(self, exchange_id: str) -> Tuple[Optional[str], Optional[str]]:
        prefix = exchange_id.upper()
        return os.getenv(f"{prefix}_API_KEY"), os.getenv(f"{prefix}_API_SECRET")

    def _normalize_symbol_for_ccxt(self, symbol: str) -> str:
        # Convert Hyperliquid-style BTC/USD:USD -> CCXT BTC/USDT (best effort)
        if ":USD" in symbol:
            return symbol.replace("/USD:USD", "/USDT").replace(":USD", "")
        return symbol

    def _get_prices(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        venues = self._venues()
        for s in symbols:
            s_ccxt = self._normalize_symbol_for_ccxt(s)
            per_ex: Dict[str, float] = {}
            for ex in venues:
                k, sec = self._ccxt_keys(ex)
                p = fetch_mark_price(exchange_id=ex, symbol=s_ccxt, api_key=k, api_secret=sec, market_type="future" if getattr(self.config.general, "market_type", "spot") == "futures" else "spot", testnet=bool(getattr(self.config.broker, "testnet", False)))
                if p is not None:
                    per_ex[ex] = float(p)
            # Keep placeholder for Hyperliquid if no CCXT data found yet
            if not per_ex:
                per_ex["binance"] = 0.0
            out[s] = per_ex
        return out

    def _get_volumes(self, symbols: List[str]) -> Dict[str, float]:
        # Best-effort from primary venue (first in list)
        venues = self._venues()
        primary = venues[0] if venues else "binance"
        vols: Dict[str, float] = {}
        try:
            import ccxt  # local import to avoid hard dep at import time
            ex_class = getattr(ccxt, primary)
            ex = ex_class({"enableRateLimit": True})
            ex.load_markets()
            for s in symbols:
                s_ccxt = self._normalize_symbol_for_ccxt(s)
                try:
                    t = ex.fetch_ticker(s_ccxt)
                    v = t.get("baseVolume") or t.get("quoteVolume") or 0.0
                    vols[s] = float(v or 0.0)
                except Exception:
                    vols[s] = 0.0
        except Exception:
            for s in symbols:
                vols[s] = 0.0
        return vols

    def _get_funding_rates(self, symbols: List[str]) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for s in symbols:
            try:
                out[s] = float(self.broker.get_funding_rate(s))
            except Exception:
                out[s] = 0.0
        return out

    def _get_orderbooks(self, symbols: List[str]) -> Dict[str, Any]:
        venues = self._venues()
        primary = venues[0] if venues else "binance"
        out: Dict[str, Any] = {}
        try:
            import ccxt
            ex = getattr(ccxt, primary)({"enableRateLimit": True})
            ex.load_markets()
            for s in symbols:
                s_ccxt = self._normalize_symbol_for_ccxt(s)
                try:
                    ob = ex.fetch_order_book(s_ccxt, limit=10)
                    out[s] = {
                        "bids": ob.get("bids", [])[:10],
                        "asks": ob.get("asks", [])[:10],
                    }
                except Exception:
                    out[s] = {"bids": [], "asks": []}
        except Exception:
            for s in symbols:
                out[s] = {"bids": [], "asks": []}
        return out

    def _get_volatility(self, symbols: List[str]) -> Dict[str, float]:
        venues = self._venues()
        primary = venues[0] if venues else "binance"
        vol_map: Dict[str, float] = {}
        try:
            import ccxt
            ex = getattr(ccxt, primary)({"enableRateLimit": True})
            ex.load_markets()
            for s in symbols:
                s_ccxt = self._normalize_symbol_for_ccxt(s)
                try:
                    o = ex.fetch_ohlcv(s_ccxt, timeframe="1m", limit=30) or []
                    closes = [float(x[4]) for x in o if isinstance(x, list) and len(x) >= 5]
                    if len(closes) < 3:
                        vol_map[s] = 0.01
                        continue
                    rets = []
                    for i in range(1, len(closes)):
                        if closes[i-1] > 0:
                            rets.append(math.log(closes[i] / closes[i-1]))
                    stdev = (sum((r - (sum(rets) / len(rets)))**2 for r in rets) / max(1, len(rets)-1)) ** 0.5 if rets else 0.0
                    vol_map[s] = float(max(1e-4, stdev))
                except Exception:
                    vol_map[s] = 0.01
        except Exception:
            for s in symbols:
                vol_map[s] = 0.01
        return vol_map

    def _get_price_change_pct(self, symbols: List[str]) -> Dict[str, float]:
        venues = self._venues()
        primary = venues[0] if venues else "binance"
        out: Dict[str, float] = {}
        try:
            import ccxt
            ex = getattr(ccxt, primary)({"enableRateLimit": True})
            ex.load_markets()
            for s in symbols:
                s_ccxt = self._normalize_symbol_for_ccxt(s)
                try:
                    o = ex.fetch_ohlcv(s_ccxt, timeframe="1m", limit=3) or []
                    if len(o) >= 2:
                        c0 = float(o[-2][4])
                        c1 = float(o[-1][4])
                        out[s] = float((c1 - c0) / c0) if c0 > 0 else 0.0
                    else:
                        out[s] = 0.0
                except Exception:
                    out[s] = 0.0
        except Exception:
            for s in symbols:
                out[s] = 0.0
        return out

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
        prices = self._get_prices(symbols)
        volumes = self._get_volumes(symbols)
        funding = self._get_funding_rates(symbols)
        orderbooks = self._get_orderbooks(symbols) if include_orderbook else {}
        volatility = self._get_volatility(symbols)
        price_change_pct = self._get_price_change_pct(symbols)
        sentiment = self._get_sentiment() if include_sentiment else {}
        portfolio = self._get_portfolio_state()

        # Back-compat: expose top-level keys as used by strategies today
        ctx = {
            "market": {
                "prices": prices,
                "volumes": volumes,
                "funding_rates": funding,
                "orderbook_depths": orderbooks,
                "new_listings": self._get_new_listings(),
                "volatility": volatility,
                "price_change_pct": price_change_pct,
            },
            "sentiment": sentiment,
            "portfolio": portfolio,
        }
        ctx["prices"] = prices
        ctx["volumes"] = volumes
        ctx["funding_rates"] = funding
        ctx["orderbook_depths"] = orderbooks
        ctx["volatility"] = volatility
        ctx["price_change_pct"] = price_change_pct
        return ctx


