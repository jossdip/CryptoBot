from __future__ import annotations

from typing import Dict, List, Any

from loguru import logger as log

from cryptobot.broker.hyperliquid_broker import HyperliquidBroker


class ArbitrageStrategy:
    def __init__(self, broker: HyperliquidBroker) -> None:
        self.broker = broker

    def detect_opportunities(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Scan for arbitrage opportunities based on provided context.

        Expects context["prices"] to contain cross-exchange quotes like:
        {"BTC/USDT": {"hyperliquid": 30000.1, "binance": 29990.0}}
        """
        prices: Dict[str, Dict[str, float]] = context.get("prices", {})
        opportunities: List[Dict[str, Any]] = []
        for symbol, per_ex in prices.items():
            if len(per_ex) < 2:
                continue
            # Find best bid/ask approximation
            venues = list(per_ex.keys())
            v0, v1 = venues[0], venues[1]
            p0, p1 = float(per_ex[v0]), float(per_ex[v1])
            if p0 <= 0 or p1 <= 0:
                continue
            spread_pct = abs(p0 - p1) / min(p0, p1)
            if spread_pct >= 0.001:  # >= 0.1%
                opportunities.append({
                    "symbol": symbol,
                    "venue_a": v0,
                    "venue_b": v1,
                    "price_a": p0,
                    "price_b": p1,
                    "spread_pct": spread_pct,
                })
        if opportunities:
            log.info(f"Arbitrage opportunities: {len(opportunities)}")
        return opportunities

    def execute(self, opportunity: Dict[str, Any]) -> bool:
        """Execute arbitrage trade.

        For MVP, we place a single protective leg on Hyperliquid aligning with the cheaper side.
        """
        try:
            symbol = str(opportunity["symbol"])  # e.g., "BTC/USD:USD"
            price_a = float(opportunity["price_a"])  # venue A price
            price_b = float(opportunity["price_b"])  # venue B price
            # Take directional leg in the direction of mean reversion
            side = "buy" if price_a < price_b else "sell"
            resp = self.broker.place_order(symbol=symbol, side=side, size=0.001, order_type="market")
            return bool(resp.get("ok", False))
        except Exception as e:
            log.error(f"Arbitrage execution failed: {e}")
            return False


