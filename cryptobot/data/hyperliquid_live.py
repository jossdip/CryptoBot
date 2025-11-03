from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Iterable, Optional, Dict, Any

import math
import random
from loguru import logger as log

try:
    import websockets  # type: ignore
    import asyncio
except Exception:  # pragma: no cover - optional dependency
    websockets = None  # type: ignore
    asyncio = None  # type: ignore

from cryptobot.core.types import Bar


def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def hyperliquid_ohlcv(
    symbol: str,
    timeframe: str = "1m",
    testnet: bool = True,
    poll_sec: float = 1.0,
) -> Iterable[Bar]:
    """
    Stream OHLCV bars from Hyperliquid.

    Notes:
    - If the `websockets` package is available, a future implementation can attach
      to Hyperliquid's WS feed. For now, this function provides a safe synthetic
      fallback so the rest of the system can operate.
    - `timeframe` is accepted for compatibility; current fallback emits 1-second ticks
      and aggregates into minute bars.
    """
    log.warning(
        "Hyperliquid WS not configured; using synthetic fallback stream for symbol=%s",
        symbol,
    )

    # Simple synthetic walk for integration testing; replace with real WS stream
    last_price = 30000.0
    o = h = l = c = last_price
    vol = 0.0
    last_minute = None

    while True:
        now = datetime.now(tz=timezone.utc)
        minute_bucket = now.replace(second=0, microsecond=0)

        # New bar if minute changes
        if last_minute is None:
            last_minute = minute_bucket
            o = h = l = c = last_price
            vol = 0.0
        elif minute_bucket != last_minute:
            bar = Bar(
                symbol=symbol,
                timestamp=int(last_minute.timestamp() * 1000),
                open=float(o),
                high=float(h),
                low=float(l),
                close=float(c),
                volume=float(vol),
            )
            yield bar
            last_minute = minute_bucket
            o = h = l = c = last_price
            vol = 0.0

        # Tick update
        drift = 0.0
        volatility = 0.0008
        shock = random.gauss(0.0, 1.0)
        last_price = max(1e-8, last_price * math.exp(drift - 0.5 * volatility ** 2 + volatility * shock))
        c = last_price
        h = max(h, last_price)
        l = min(l, last_price)
        vol += abs(shock)

        time.sleep(poll_sec)


def hyperliquid_ticker(symbol: str, testnet: bool = True) -> Dict[str, Any]:
    """Return latest ticker snapshot; placeholder for WS/HTTP integration."""
    return {"symbol": symbol, "price": 30000.0, "ts": _now_ms()}


def hyperliquid_orderbook(symbol: str, depth: int = 20, testnet: bool = True) -> Dict[str, Any]:
    """Return a shallow orderbook structure; placeholder for WS integration."""
    return {"symbol": symbol, "bids": [], "asks": [], "ts": _now_ms()}


def hyperliquid_new_listings(testnet: bool = True) -> Iterable[Dict[str, Any]]:
    """Yield new listing events (placeholder)."""
    if False:  # pragma: no cover - placeholder
        yield {}

