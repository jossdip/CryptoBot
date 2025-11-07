from __future__ import annotations

from typing import Dict, Any, List
import statistics

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

        # 1) Prefer orderbook mid when available (best bid/ask)
        mid_price: float = 0.0
        try:
            ob_map: Dict[str, Any] = context.get("orderbook_depths", {}) or context.get("market", {}).get("orderbook_depths", {}) or {}
            ob = ob_map.get(symbol, {})
            bids: List[List[float]] = ob.get("bids", []) if isinstance(ob, dict) else []
            asks: List[List[float]] = ob.get("asks", []) if isinstance(ob, dict) else []
            if bids and asks and isinstance(bids[0], list) and isinstance(asks[0], list):
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                if best_bid > 0 and best_ask > 0:
                    mid_price = (best_bid + best_ask) / 2.0
        except Exception:
            pass

        # 2) Fallback to robust cross-venue median (after aggregator outlier filtering)
        if mid_price <= 0.0:
            try:
                price_map: Dict[str, float] = context.get("prices", {}).get(symbol, {})  # exchange -> price
                vals = [float(v) for v in price_map.values() if float(v) > 0]
                if vals:
                    mid_price = float(statistics.median(vals))
            except Exception:
                mid_price = 0.0

        # 3) Last resort: leave as zero (or very small) rather than stale 30000.0
        if mid_price <= 0.0:
            mid_price = 0.0

        vol = float(context.get("volatility", {}).get(symbol, 0.01))
        spread = self.calculate_spread(symbol, vol)
        return [{"symbol": symbol, "mid": mid_price, "spread": spread}]


