from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from cryptobot.monitor.storage import StorageManager


@dataclass
class MonitorEngineConfig:
    interval_sec: int = 5


class MonitorEngine:
    """Background engine that periodically collects runtime data into storage.

    Integration points:
      - call record_trade() when a trade is completed
      - call record_llm_decision() from LLM orchestration
    """

    def __init__(
        self,
        *,
        broker: Any,
        orchestrator: Any,
        performance_tracker: Any,
        storage_path: str,
        interval_sec: int = 5,
    ) -> None:
        self.broker = broker
        self.orchestrator = orchestrator
        self.performance_tracker = performance_tracker
        self.storage = StorageManager(storage_path)
        self.cfg = MonitorEngineConfig(interval_sec=interval_sec)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_trade_count = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    # Hooks from other components
    def record_llm_decision(
        self,
        *,
        timestamp: float,
        decision_type: str,
        prompt: str,
        response: str,
        reasoning: str,
        sentiment: str,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.storage.record_llm_decision(
            timestamp=timestamp,
            decision_type=decision_type,
            prompt=prompt,
            response=response,
            reasoning=reasoning,
            sentiment=sentiment,
            confidence=confidence,
            metadata=metadata,
        )

    def record_trade(
        self,
        *,
        timestamp: float,
        strategy: str,
        symbol: str,
        side: str,
        size: float,
        entry: float,
        exit: float,
        pnl: float,
        fees: float = 0.0,
        confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.storage.record_trade(
            timestamp=timestamp,
            strategy=strategy,
            symbol=symbol,
            side=side,
            size=size,
            entry=entry,
            exit=exit,
            pnl=pnl,
            fees=fees,
            confidence=confidence,
            metadata=metadata,
        )

    # Loop
    def _run_loop(self) -> None:  # pragma: no cover - background thread
        while not self._stop.is_set():
            try:
                self._collect_once()
            except Exception:
                pass
            time.sleep(self.cfg.interval_sec)

    def _collect_once(self) -> None:
        # Portfolio snapshot
        try:
            raw = self.broker.get_portfolio()
            # Normalize dictionary-like responses
            portfolio = raw.get("response", raw) if isinstance(raw, dict) else raw

            # Extract balance/equity/unrealized PnL best-effort
            def _num(*keys: str, default: float = 0.0) -> float:
                cur = portfolio
                for k in keys:
                    if isinstance(cur, dict) and k in cur:
                        cur = cur[k]
                    else:
                        return default
                try:
                    return float(cur)
                except Exception:
                    return default

            balance = _num("balance", default=_num("cash", default=0.0))
            equity = _num("equity", default=balance)
            unrealized = _num("unrealized_pnl", default=_num("unrealizedPnl", default=0.0))

            # Positions: store as-is if we find a positions-like key; else store whole portfolio
            positions_obj: Any = None
            for k in ("positions", "openPositions", "positionsMap", "perpPositions"):
                if isinstance(portfolio, dict) and k in portfolio:
                    positions_obj = portfolio[k]
                    break
            positions_dict: Dict[str, Any] = positions_obj if isinstance(positions_obj, dict) else {"data": positions_obj} if positions_obj is not None else (portfolio if isinstance(portfolio, dict) else {})

            self.storage.record_portfolio_snapshot(
                timestamp=time.time(),
                balance=float(balance),
                equity=float(equity),
                unrealized_pnl=float(unrealized),
                positions=positions_dict or {},
            )
        except Exception:
            pass

        # Performance snapshot (coarse)
        try:
            for t in self.performance_tracker.trades[self._last_trade_count:]:
                self.storage.record_performance_metric(
                    timestamp=float(t.get("ts", time.time())),
                    strategy=str(t.get("strategy", "unknown")),
                    pnl=float(t.get("pnl", 0.0)),
                )
            self._last_trade_count = len(self.performance_tracker.trades)
        except Exception:
            pass


