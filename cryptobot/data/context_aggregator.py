from __future__ import annotations

from typing import Dict, List, Any, Optional, Tuple
import os
import math
import statistics
import pandas as pd

from cryptobot.data.ccxt_live import fetch_mark_price
from cryptobot.core.logging import get_logger

# Import signal collectors (not strategies, but signal sources)
try:
    from cryptobot.llm.client import LLMClient
except ImportError:
    LLMClient = None  # type: ignore


class MarketContextAggregator:
    def __init__(self, broker, llm_client: Optional[Any] = None, config: Optional[Any] = None) -> None:
        self.broker = broker
        self.llm_client = llm_client
        self.config = config
        # Initialize signal collectors (not trading strategies, but signal sources)
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
        # Allow configurable outlier filter (percent from median). Default 1%
        try:
            outlier_pct = float(os.getenv("CB_PRICE_OUTLIER_PCT", "0.01"))
        except Exception:
            outlier_pct = 0.01

        for s in symbols:
            s_ccxt = self._normalize_symbol_for_ccxt(s)
            per_ex: Dict[str, float] = {}
            for ex in venues:
                k, sec = self._ccxt_keys(ex)
                p = fetch_mark_price(exchange_id=ex, symbol=s_ccxt, api_key=k, api_secret=sec, market_type="future" if getattr(self.config.general, "market_type", "spot") == "futures" else "spot", testnet=bool(getattr(self.config.broker, "testnet", False)))
                if p is not None:
                    per_ex[ex] = float(p)
            # Filter outliers vs median to avoid instrument mismatches (spot vs perp, inverse vs linear)
            try:
                if len(per_ex) >= 2:
                    vals = list(per_ex.values())
                    med = statistics.median(vals)
                    # Keep only prices within threshold of median
                    filtered = {
                        ex: px for ex, px in per_ex.items()
                        if med > 0 and abs(px - med) / med <= outlier_pct
                    }
                    # If everything filtered out (extreme divergence), keep the closest to median
                    if not filtered and med > 0:
                        # pick exchange with min absolute deviation
                        ex_best = min(per_ex.keys(), key=lambda e: abs(per_ex[e] - med))
                        filtered = {ex_best: per_ex[ex_best]}
                    per_ex = filtered or per_ex
            except Exception:
                # In case statistics.median fails unexpectedly, keep raw per_ex
                pass
            # Keep placeholder if still empty
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
                rate = float(self.broker.get_funding_rate(s))
            except Exception:
                rate = 0.0
            # Fallback via CCXT (best-effort) if broker returns 0.0
            if rate == 0.0:
                try:
                    import ccxt  # type: ignore
                    # Try common venues for funding rates
                    for ex_id in self._venues():
                        try:
                            ex = getattr(ccxt, ex_id)({"enableRateLimit": True, "options": {"defaultType": "future"}})
                            ex.load_markets()
                            # Try common contract naming variants
                            base = s.replace(":USD", "").replace("/USD", "/USDT")
                            candidates = [base + ":USDT", base, base.replace("/USDT", "/USD") + ":USD"]
                            symbol_found = None
                            for c in candidates:
                                if c in ex.markets:
                                    symbol_found = c
                                    break
                            if symbol_found is None:
                                continue
                            fr = None
                            # fetchFundingRate is not universally implemented; guard call
                            if hasattr(ex, "fetchFundingRate"):
                                try:
                                    data = ex.fetchFundingRate(symbol_found)  # type: ignore[attr-defined]
                                    # CCXT returns either dict with 'info' or flat fields
                                    if isinstance(data, dict):
                                        for key in ("fundingRate", "fundingRateDaily", "rate"):
                                            if key in data:
                                                fr = float(data[key])
                                                break
                                    if fr is None and isinstance(data, dict) and "info" in data and isinstance(data["info"], dict):
                                        info = data["info"]
                                        for key in ("fundingRate", "fundingRateDaily", "rate"):
                                            if key in info:
                                                fr = float(info[key])
                                                break
                                except Exception:
                                    fr = None
                            if fr is not None:
                                rate = float(fr)
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
            out[s] = float(rate or 0.0)
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

    def _fetch_ohlcv(self, symbols: List[str], timeframe: str = "1h", limit: int = 100) -> Dict[str, pd.DataFrame]:
        """
        Helper to fetch raw OHLCV data for technical analysis.
        """
        venues = self._venues()
        primary = venues[0] if venues else "binance"
        out: Dict[str, pd.DataFrame] = {}
        log = get_logger()
        try:
            import ccxt
            ex = getattr(ccxt, primary)({"enableRateLimit": True})
            ex.load_markets()
            for s in symbols:
                s_ccxt = self._normalize_symbol_for_ccxt(s)
                try:
                    o = ex.fetch_ohlcv(s_ccxt, timeframe=timeframe, limit=limit) or []
                    # Convert to DataFrame
                    if o:
                        df = pd.DataFrame(o, columns=["timestamp", "open", "high", "low", "close", "volume"])
                        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                        df.set_index("timestamp", inplace=True)
                        out[s] = df
                    else:
                        log.warning(f"No OHLCV data for {s} ({s_ccxt}) from {primary}")
                        out[s] = pd.DataFrame()
                except Exception as e:
                    log.warning(f"Failed to fetch OHLCV for {s} ({s_ccxt}): {e}")
                    out[s] = pd.DataFrame()
        except Exception as e:
            log.error(f"Failed to initialize CCXT {primary} for OHLCV: {e}")
            for s in symbols:
                out[s] = pd.DataFrame()
        return out

    def _get_volatility(self, symbols: List[str]) -> Dict[str, float]:
        # Refactored to use _fetch_ohlcv logic indirectly or kept simple for backward compat
        # Here we keep original implementation to avoid breaking existing consumers, 
        # but we could unify if we wanted. For safety, I keep it as is but maybe optimized.
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
        # Availability flags so missing signals do not penalize confidence
        # Sentiments are currently disabled/removed
        
        sentiment: Dict[str, Any] = {
            "reddit": {"score": 0.0, "confidence": None, "available": False},
            "twitter": {"score": 0.0, "confidence": None, "available": False},
            "polymarket": {"score": 0.0, "confidence": None, "available": False},
        }
        
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

    def build_technical_context(self, symbols: List[str], timeframe: str = "5m") -> Dict[str, pd.DataFrame]:
        """
        Lightweight method for the strategy loop.
        Fetches OHLCV for technical indicators.
        """
        return self._fetch_ohlcv(symbols, timeframe=timeframe, limit=100)

    def get_candles(self, symbols: List[str], timeframe: str = "5m", limit: int = 100) -> Dict[str, pd.DataFrame]:
        """
        Public accessor for OHLCV candles.
        """
        return self._fetch_ohlcv(symbols, timeframe=timeframe, limit=limit)

    def fetch_sentiment_on_demand(self, symbols: List[str]) -> Dict[str, Any]:
        """
        On-demand sentiment fetch. Currently grabs global/keyword sentiment,
        could be refined to filter by symbol if collectors support it.
        """
        return self._get_sentiment()
