from __future__ import annotations

from typing import Optional

import ccxt


class TestnetReplicator:
    def __init__(self, exchange_id: str, api_key: str, api_secret: str, market_type: str = "futures", testnet: bool = True) -> None:
        ex_class = getattr(ccxt, exchange_id)
        options = {}
        if market_type == "futures":
            options["defaultType"] = "future"
        self.ex = ex_class({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": options,
        })
        try:
            self.ex.set_sandbox_mode(bool(testnet))  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            self.ex.load_markets()
        except Exception:
            pass

    def market_order(self, symbol: str, side: str, amount: float) -> Optional[dict]:
        try:
            return self.ex.create_order(symbol=symbol, type="market", side=side, amount=float(amount))
        except Exception:
            return None


