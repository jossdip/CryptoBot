from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Iterable, Optional

import ccxt

from cryptobot.core.types import Bar


def _to_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def live_ohlcv(
    symbol: str,
    timeframe: str = "1m",
    exchange_id: str = "binance",
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
    poll_sec: float = 2.0,
) -> Iterable[Bar]:
    ex_class = getattr(ccxt, exchange_id)
    ex = ex_class({
        "apiKey": api_key or "",
        "secret": api_secret or "",
        "enableRateLimit": True,
    })

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
