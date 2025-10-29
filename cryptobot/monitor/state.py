from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Dict, List, Optional

from cryptobot.core.types import PortfolioSnapshot, Position


class MonitorState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.equity_curve: List[Dict] = []
        self.positions: Dict[str, Dict] = {}
        self.events: List[Dict] = []
        self.last_llm_multiplier: Optional[float] = None
        self.max_events: int = 500

    def add_equity(self, snap: PortfolioSnapshot) -> None:
        with self._lock:
            self.equity_curve.append({
                "timestamp": snap.timestamp,
                "equity": float(snap.equity),
                "cash": float(snap.cash),
                "unrealized_pnl": float(snap.unrealized_pnl),
            })
            if len(self.equity_curve) > 10000:
                self.equity_curve = self.equity_curve[-10000:]

    def set_positions(self, symbol_to_pos: Dict[str, Position]) -> None:
        with self._lock:
            self.positions = {
                sym: {"symbol": p.symbol, "qty": float(p.qty), "avg_price": float(p.avg_price)}
                for sym, p in symbol_to_pos.items()
            }

    def add_event(self, event: Dict) -> None:
        with self._lock:
            self.events.append(event)
            if len(self.events) > self.max_events:
                self.events = self.events[-self.max_events:]

    def set_llm_multiplier(self, mult: Optional[float]) -> None:
        with self._lock:
            self.last_llm_multiplier = mult

    def snapshot(self) -> Dict:
        with self._lock:
            return {
                "equity_curve": list(self.equity_curve),
                "positions": dict(self.positions),
                "events": list(self.events)[-200:],
                "last_llm_multiplier": self.last_llm_multiplier,
            }


state = MonitorState()
