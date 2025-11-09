from __future__ import annotations

import time
from typing import Dict, List, Any


class PerformanceTracker:
    def __init__(self) -> None:
        self.trades: List[Dict[str, Any]] = []
        self._open_trades: Dict[str, Dict[str, Any]] = {}

    def record_trade_start(self, strategy: str, entry_price: float, size: float, symbol: str = "BTC/USD:USD", direction: str = "long") -> None:
        self._open_trades[strategy] = {
            "strategy": strategy,
            "symbol": symbol,
            "entry": float(entry_price),
            "size": float(size),
            "direction": str(direction).lower(),
            "ts_open": time.time(),
        }

    def update_positions(self, portfolio_snapshot: Dict[str, Any]) -> None:
        # Best-effort profit update when we have portfolio marks; here we leave as a stub
        pass

    def track_trade(self, strategy: str, entry: float, exit: float, size: float, fees: float) -> None:
        pnl = (float(exit) - float(entry)) * float(size) - float(fees)
        self.trades.append({
            "strategy": strategy,
            "entry": float(entry),
            "exit": float(exit),
            "size": float(size),
            "fees": float(fees),
            "pnl": pnl,
            "ts": time.time(),
        })

    def get_strategy_metrics(self, strategy: str, window: int = 1000) -> Dict[str, Any]:
        rows = [t for t in self.trades if t.get("strategy") == strategy][-window:]
        if not rows:
            return {"total_pnl": 0.0, "roi_pct": 0.0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "sharpe_ratio": 0.0, "max_drawdown": 0.0}
        pnls = [float(r["pnl"]) for r in rows]
        total_pnl = sum(pnls)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate = float(len(wins)) / float(max(1, len(rows)))
        avg_win = sum(wins) / float(len(wins)) if wins else 0.0
        avg_loss = sum(losses) / float(len(losses)) if losses else 0.0
        # Simple risk proxy
        sharpe = (sum(pnls) / float(max(1, len(pnls)))) / (1e-6 + (sum(abs(p) for p in pnls) / float(max(1, len(pnls)))))
        max_dd = min(0.0, min(pnls))
        return {
            "total_pnl": total_pnl,
            "roi_pct": 0.0,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_dd,
        }

    def get_overall_metrics(self) -> Dict[str, Any]:
        return self.get_strategy_metrics(strategy="__overall__")

    def feed_to_llm(self) -> Dict[str, Any]:
        strategies = ["market_making", "momentum", "scalping", "arbitrage", "breakout", "sniping"]
        return {
            "by_strategy": {s: self.get_strategy_metrics(s) for s in strategies},
            "overall": self.get_overall_metrics(),
        }


