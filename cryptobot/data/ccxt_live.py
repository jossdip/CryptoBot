from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional, List

import ccxt

from cryptobot.core.types import Bar


def _to_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _build_exchange(
    exchange_id: str,
    api_key: Optional[str],
    api_secret: Optional[str],
    market_type: str,
    testnet: bool,
):
    ex_class = getattr(ccxt, exchange_id)
    options: Dict[str, object] = {}
    if market_type == "futures":
        # Many exchanges rely on defaultType to route endpoints
        options["defaultType"] = "future"
    ex = ex_class({
        "apiKey": api_key or "",
        "secret": api_secret or "",
        "enableRateLimit": True,
        "options": options,
    })
    try:
        # Where supported, this toggles to testnet/demo endpoints
        ex.set_sandbox_mode(bool(testnet))  # type: ignore[attr-defined]
    except Exception:
        # Not all exchanges support sandbox_mode; ignore silently
        pass
    try:
        ex.load_markets()
    except Exception:
        pass
    return ex


def live_ohlcv(
    symbol: str,
    timeframe: str = "1m",
    exchange_id: str = "binance",
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    poll_sec: float = 2.0,
    market_type: str = "spot",
    testnet: bool = False,
) -> Iterable[Bar]:
    ex = _build_exchange(
        exchange_id=exchange_id,
        api_key=api_key,
        api_secret=api_secret,
        market_type=market_type,
        testnet=testnet,
    )

    while True:
        try:
            ohlcv = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=2)
            if not ohlcv:
                time.sleep(poll_sec)
                continue
            t, o, h, l, c, v = ohlcv[-1]
            yield Bar(symbol=symbol, timestamp=int(t), open=float(o), high=float(h), low=float(l), close=float(c), volume=float(v))
        except Exception:
            time.sleep(max(5.0, poll_sec))
            continue
        time.sleep(poll_sec)


def fetch_mark_price(exchange_id: str, symbol: str, api_key: Optional[str] = None, api_secret: Optional[str] = None, market_type: str = "spot", testnet: bool = False) -> Optional[float]:
    """Best-effort mark price fetch. Attempts multiple symbol variants and falls back to last price."""
    ex = _build_exchange(exchange_id=exchange_id, api_key=api_key, api_secret=api_secret, market_type=market_type, testnet=testnet)

    def _candidates(sym: str, mtype: str) -> List[str]:
        # Generate common CCXT symbol variants across exchanges (spot/perp)
        cands: List[str] = []
        base = sym
        # Strip CCXT contract suffix if present (e.g., BTC/USDT:USDT -> BTC/USDT)
        if ":" in base:
            base = base.split(":")[0]
        # Common base forms
        cands.append(base)  # e.g., BTC/USDT
        # Linear perps (most common)
        if base.endswith("/USDT"):
            cands.append(base + ":USDT")  # e.g., BTC/USDT:USDT
        # Inverse perps
        if base.endswith("/USD"):
            cands.append(base + ":USD")   # e.g., BTC/USD:USD
            cands.append(base.replace("/USD", "/USDT"))
        # Alternate quote form fallback
        if "/USDT" in base and ":USDT" not in base:
            cands.append(base.replace("/USDT", "/USD"))
        # Deduplicate while preserving order
        seen = set()
        uniq: List[str] = []
        for c in cands:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        # For futures/perp, prioritize contract symbols first
        if str(mtype).lower().startswith(("future", "perp")):
            uniq = [c for c in uniq if ":" in c] + [c for c in uniq if ":" not in c]
        return uniq

    try_syms = _candidates(symbol, market_type)
    try:
        markets = getattr(ex, "markets", None) or {}
    except Exception:
        markets = {}

    for sym in try_syms:
        try:
            # If markets are loaded, skip unknown symbols to avoid noisy errors
            if markets and sym not in markets:
                continue
            tkr = ex.fetch_ticker(sym)
            info = tkr.get("info", {}) if isinstance(tkr, dict) else {}
            mark = None
            if isinstance(info, dict):
                mark = info.get("markPrice") or info.get("indexPrice") or info.get("lastPrice")
            if mark is not None:
                return float(mark)
            last = tkr.get("last") if isinstance(tkr, dict) else None
            if last is not None:
                return float(last)
        except Exception:
            continue
    return None
