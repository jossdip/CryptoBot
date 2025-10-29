from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Generator, Iterable, List, Tuple

import numpy as np

from cryptobot.core.types import Bar


_TIMEFRAME_TO_MIN = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
}


def _to_epoch_ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


@dataclass
class RandomWalkParams:
    seed: int
    start: datetime
    end: datetime
    timeframe: str
    steps_per_bar: int
    drift: float
    volatility: float


def random_walk_bars(symbol: str, p: RandomWalkParams, start_price: float = 30000.0) -> Iterable[Bar]:
    random.seed(p.seed)
    np.random.seed(p.seed)

    minutes = _TIMEFRAME_TO_MIN.get(p.timeframe, 5)
    bar_delta = timedelta(minutes=minutes)

    cur_time = p.start
    price = float(start_price)
    step_dt = bar_delta / p.steps_per_bar

    while cur_time <= p.end:
        # simulate fine-grained steps within bar
        prices = [price]
        for _ in range(p.steps_per_bar):
            shock = np.random.normal(loc=p.drift / p.steps_per_bar, scale=p.volatility / math.sqrt(p.steps_per_bar))
            price = max(0.01, price * (1.0 + shock))
            prices.append(price)

        bar_open = prices[0]
        bar_close = prices[-1]
        bar_high = max(prices)
        bar_low = min(prices)
        volume = float(abs(np.random.normal(loc=10.0, scale=3.0)))

        yield Bar(
            symbol=symbol,
            timestamp=_to_epoch_ms(cur_time),
            open=float(bar_open),
            high=float(bar_high),
            low=float(bar_low),
            close=float(bar_close),
            volume=volume,
        )

        cur_time += bar_delta
