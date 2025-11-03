from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

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
    """Best-effort mark price fetch. Falls back to last price when mark is unavailable."""
    ex = _build_exchange(exchange_id=exchange_id, api_key=api_key, api_secret=api_secret, market_type=market_type, testnet=testnet)
    try:
        tkr = ex.fetch_ticker(symbol)
        # Prefer mark price when present (e.g., Binance futures)
        info = tkr.get("info", {}) if isinstance(tkr, dict) else {}
        mark = None
        if isinstance(info, dict):
            mark = info.get("markPrice") or info.get("lastPrice")
        if mark is not None:
            return float(mark)
        last = tkr.get("last") if isinstance(tkr, dict) else None
        return float(last) if last is not None else None
    except Exception:
        return None
