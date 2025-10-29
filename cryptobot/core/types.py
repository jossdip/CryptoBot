from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class Bar:
    symbol: str
    timestamp: int  # epoch ms
    open: float
    high: float
    low: float
    close: float
    volume: float


Side = Literal["buy", "sell"]
OrderType = Literal["market"]


@dataclass
class Order:
    id: str
    symbol: str
    side: Side
    type: OrderType
    qty: float
    price: Optional[float]  # None for market
    timestamp: int


@dataclass
class Fill:
    order_id: str
    symbol: str
    side: Side
    qty: float
    price: float
    fee: float
    timestamp: int


@dataclass
class Position:
    symbol: str
    qty: float
    avg_price: float


@dataclass
class PortfolioSnapshot:
    timestamp: int
    cash: float
    equity: float
    unrealized_pnl: float
