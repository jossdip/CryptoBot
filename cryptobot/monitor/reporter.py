from __future__ import annotations

from typing import Any, Dict, List, Optional

from cryptobot.monitor.storage import StorageManager


class ReportGenerator:
    def __init__(self, storage: StorageManager):
        self.storage = storage

    def recent_trades(
        self,
        *,
        limit: int = 10,
        strategy: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return self.storage.recent_trades(limit=limit, strategy=strategy, symbol=symbol)

    def portfolio_summary(self) -> Dict[str, Any]:
        latest = self.storage.latest_portfolio() or {}
        return latest

    def ai_insights(self, *, limit: int = 5) -> List[Dict[str, Any]]:
        return self.storage.recent_llm_decisions(limit=limit)


