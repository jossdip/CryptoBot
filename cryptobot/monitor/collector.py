from __future__ import annotations

from typing import Any, Dict


class DataCollector:
    """Thin collector facade. In this version, collection is driven by MonitorEngine.

    This class exists to match the architecture and allow future extensions.
    """

    def collect_portfolio(self, broker: Any) -> Dict[str, Any]:
        try:
            portfolio = broker.get_portfolio()
            positions = {
                sym: {
                    "symbol": getattr(p, "symbol", sym),
                    "qty": float(getattr(p, "qty", 0.0)),
                    "avg_price": float(getattr(p, "avg_price", 0.0)),
                }
                for sym, p in getattr(portfolio, "positions", {}).items()
            }
            equity = float(getattr(portfolio, "equity", lambda: 0.0)() if callable(getattr(portfolio, "equity", None)) else getattr(portfolio, "cash", 0.0))
            return {
                "balance": float(getattr(portfolio, "cash", 0.0)),
                "equity": equity,
                "unrealized_pnl": float(getattr(portfolio, "unrealized_pnl", 0.0)),
                "positions": positions,
            }
        except Exception:
            return {"balance": 0.0, "equity": 0.0, "unrealized_pnl": 0.0, "positions": {}}


