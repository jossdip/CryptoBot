from __future__ import annotations

from typing import Dict, Any

from loguru import logger as log

from cryptobot.broker.hyperliquid_broker import HyperliquidBroker


class MarketMakingStrategy:
    def __init__(self, broker: HyperliquidBroker) -> None:
        self.broker = broker

    def calculate_spread(self, symbol: str, volatility: float) -> float:
        # Simple function: spread as multiple of volatility
        base_spread = max(0.0005, volatility * 2.0)  # 5 bps min
        return base_spread

    def place_maker_orders(self, symbol: str, mid_price: float, spread: float) -> None:
        # Place small passive orders around mid; in real impl, use post-only flags
        bid = mid_price * (1.0 - spread / 2.0)
        ask = mid_price * (1.0 + spread / 2.0)
        try:
            self.broker.place_order(symbol=symbol, side="buy", size=0.001, order_type="limit", price=bid)
            self.broker.place_order(symbol=symbol, side="sell", size=0.001, order_type="limit", price=ask)
        except Exception as e:
            log.error(f"Failed to place maker orders: {e}")

    def detect_opportunities(self, context: Dict[str, Any]) -> list[Dict[str, Any]]:
        # For MM, opportunity is continuous; we synthesize a decision input
        symbol = next(iter(context.get("prices", {}).keys()), "BTC/USD:USD")
        mid = float(context.get("prices", {}).get(symbol, {}).get("hyperliquid", 30000.0))
        vol = float(context.get("volatility", {}).get(symbol, 0.01))
        spread = self.calculate_spread(symbol, vol)
        return [{"symbol": symbol, "mid": mid, "spread": spread}]


