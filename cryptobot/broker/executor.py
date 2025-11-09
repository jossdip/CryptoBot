from __future__ import annotations

from typing import Dict, Any, Optional

from cryptobot.llm.orchestrator import StrategyWeight
from loguru import logger as log


class MultiStrategyExecutor:
    def __init__(self, broker, orchestrator) -> None:
        self.broker = broker
        self.orchestrator = orchestrator
        # Portfolio handle expected on broker.get_portfolio() path

    @property
    def total_capital(self) -> float:
        pf = self.broker.get_portfolio() or {}
        resp = pf.get("response", {})
        # Best effort extraction
        for k in ("equity", "cash", "balance"):
            if k in resp:
                try:
                    return float(resp[k])
                except Exception:
                    continue
        return 0.0

    def execute_strategy(self, strategy_name: str, decision: Dict[str, Any], weights: StrategyWeight) -> Optional[Dict[str, Any]]:
        allocated_capital = float(self.total_capital) * float(getattr(weights, strategy_name, 0.0))
        symbol = str(decision.get("symbol")) if "symbol" in decision else None
        direction = str(decision.get("direction", "flat"))
        if not symbol or direction == "flat":
            try:
                log.debug(f"Executor skip: missing symbol or flat direction | sym={symbol} dir={direction} alloc={allocated_capital:.2f}")
            except Exception:
                pass
            return None
        size_usd = min(float(decision.get("size_usd", 0.0)), allocated_capital)
        if size_usd <= 0:
            try:
                log.debug(f"Executor skip: non-positive size | size_usd={float(decision.get('size_usd', 0.0)):.2f} alloc={allocated_capital:.2f}")
            except Exception:
                pass
            return None
        leverage = int(decision.get("leverage", 1))
        stop_loss = decision.get("stop_loss_pct")
        take_profit = decision.get("take_profit_pct")
        side = "buy" if direction == "long" else "sell"
        # Convert USD sizing to coin sizing using provided entry_price when available
        try:
            entry_price = float(decision.get("entry_price", 0.0) or 0.0)
        except Exception:
            entry_price = 0.0
        coin_size = float(size_usd) / float(entry_price) if entry_price and entry_price > 0 else 0.0
        if coin_size <= 0:
            # Fallback: attempt a conservative nominal size if price missing to avoid skipping forever
            try:
                log.debug(f"Executor fallback: missing/invalid entry_price for {symbol} (entry_price={entry_price}), cannot convert USD->{symbol}. Skipping.")
            except Exception:
                pass
            return None
        # Quantize size using broker helper if available to avoid wire rounding
        q_coin_size = coin_size
        try:
            norm_fn = getattr(self.broker, "_normalize_symbol_for_hyperliquid", None)
            q_fn = getattr(self.broker, "_quantize_size", None)
            coin_tkr = norm_fn(symbol) if callable(norm_fn) else (symbol.split("/", 1)[0].split(":", 1)[0] if isinstance(symbol, str) else "")
            if callable(q_fn) and coin_tkr:
                q_coin_size = float(q_fn(coin_tkr, coin_size))
                if q_coin_size <= 0.0 and coin_size > 0.0:
                    q_coin_size = coin_size
        except Exception:
            q_coin_size = coin_size
        try:
            log.info(f"Placing order | strat={strategy_name} sym={symbol} side={side} coin_sz={q_coin_size:.6f} lev={leverage} usd_sz={size_usd:.2f} entry={entry_price:.2f}")
        except Exception:
            pass
        # Prefer passive limit orders for market_making to avoid taker fees
        order_type = "market"
        price = None
        if strategy_name == "market_making" and entry_price > 0.0:
            try:
                spread = float(decision.get("spread", 0.0) or 0.0)
            except Exception:
                spread = 0.0
            if spread and spread > 0.0:
                # Place limit inside the spread (post-only would be ideal, but not all SDKs expose it)
                px = entry_price * (1.0 - spread / 2.0) if side == "buy" else entry_price * (1.0 + spread / 2.0)
                if px > 0.0:
                    order_type = "limit"
                    price = float(px)
        resp = self.broker.place_order(
            symbol=symbol,
            side=side,
            size=q_coin_size,
            leverage=leverage,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        try:
            if isinstance(resp, dict) and resp.get("ok"):
                # Prefer the broker-reported request size for clarity
                try:
                    req = resp.get("request", {}) if isinstance(resp.get("request"), dict) else {}
                    logged_sz = float(req.get("sz", q_coin_size))
                except Exception:
                    logged_sz = q_coin_size
                log.info(f"Order placed | strat={strategy_name} sym={symbol} side={side} coin_sz={logged_sz:.6f} lev={leverage}")
            else:
                log.error(f"Order failed | strat={strategy_name} sym={symbol} side={side} resp={resp}")
        except Exception:
            pass
        return resp

    def close_position(
        self,
        *,
        symbol: str,
        qty: float,
        order_type: str = "market",
        limit_price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Close an existing position by placing the opposing order for the given qty.
        qty: positive absolute coin size to close
        """
        try:
            coin = str(symbol).split("/", 1)[0].split(":", 1)[0]
        except Exception:
            coin = symbol
        side = "sell" if float(qty) > 0 else "buy"
        abs_qty = abs(float(qty))
        # Quantize per broker rules
        q_qty = abs_qty
        try:
            norm_fn = getattr(self.broker, "_normalize_symbol_for_hyperliquid", None)
            q_fn = getattr(self.broker, "_quantize_size", None)
            coin_tkr = norm_fn(symbol) if callable(norm_fn) else coin
            if callable(q_fn) and coin_tkr:
                q_qty = float(q_fn(coin_tkr, abs_qty))
                if q_qty <= 0.0 and abs_qty > 0.0:
                    q_qty = abs_qty
        except Exception:
            q_qty = abs_qty
        try:
            log.info(f"Closing position | sym={symbol} side={side} coin_sz={q_qty:.6f} type={order_type} limit={limit_price if limit_price else '-'}")
        except Exception:
            pass
        resp = self.broker.place_order(
            symbol=symbol,
            side=side,
            size=q_qty,
            leverage=1,
            order_type="limit" if str(order_type).lower() == "limit" else "market",
            price=float(limit_price) if (order_type == "limit" and limit_price) else None,
            stop_loss=None,
            take_profit=None,
        )
        return resp


