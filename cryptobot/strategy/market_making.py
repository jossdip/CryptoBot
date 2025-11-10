from __future__ import annotations

from typing import Dict, Any, List, Optional
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

    def place_maker_orders(self, symbol: str, mid_price: float, spread: float, *, size_usd: Optional[float] = None, post_only: bool = True) -> None:
        """
        Place passive maker orders around mid. Size per side is derived from size_usd when provided.
        Prices are quantized and nudged by one tick to reduce the risk of crossing the spread.
        """
        if mid_price <= 0.0 or spread <= 0.0:
            return
        # Compute per-side size in coin if provided in USD
        buy_sz = sell_sz = 0.001  # conservative fallback
        try:
            if size_usd and size_usd > 0.0:
                coin = str(symbol).split("/", 1)[0].split(":", 1)[0]
                raw_sz = float(size_usd) / float(mid_price)
                q_fn = getattr(self.broker, "_quantize_size", None)
                if callable(q_fn):
                    buy_sz = sell_sz = float(q_fn(coin, raw_sz))
                    if buy_sz <= 0.0:
                        buy_sz = sell_sz = raw_sz
                else:
                    buy_sz = sell_sz = raw_sz
        except Exception:
            pass
        # Compute raw target prices
        bid_raw = mid_price * (1.0 - spread / 2.0)
        ask_raw = mid_price * (1.0 + spread / 2.0)
        # Quantize and de-cross by nudging one tick further away
        try:
            coin = str(symbol).split("/", 1)[0].split(":", 1)[0]
            q_px_fn = getattr(self.broker, "_quantize_price", None)
            get_tick_fn = getattr(self.broker, "_get_price_tick", None)
            tick = float(get_tick_fn(coin)) if callable(get_tick_fn) else 0.0
            bid_px = float(q_px_fn(coin, "buy", bid_raw)) if callable(q_px_fn) else bid_raw
            ask_px = float(q_px_fn(coin, "sell", ask_raw)) if callable(q_px_fn) else ask_raw
            if tick > 0.0:
                bid_px = max(tick, bid_px - tick)  # push deeper to stay maker
                ask_px = ask_px + tick
        except Exception:
            bid_px, ask_px = bid_raw, ask_raw
        # Place limits
        try:
            self.broker.place_order(symbol=symbol, side="buy", size=buy_sz, order_type="limit", price=bid_px)
            self.broker.place_order(symbol=symbol, side="sell", size=sell_sz, order_type="limit", price=ask_px)
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


