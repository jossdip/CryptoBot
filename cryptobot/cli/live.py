from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
import threading

import pandas as pd
from dotenv import load_dotenv

from cryptobot.broker.paper import PaperBroker
from cryptobot.broker.risk import RiskManager
from cryptobot.core.config import AppConfig
from cryptobot.core.logging import get_logger, setup_logging
from cryptobot.core.types import Bar
from cryptobot.data.ccxt_live import live_ohlcv
from cryptobot.data.random_walk import RandomWalkParams, random_walk_bars
from cryptobot.llm.client import LLMClient
from cryptobot.llm.overlay import LLMRiskOverlay
from cryptobot.monitor.state import state as monitor_state
from cryptobot.strategy.ensemble import EnsembleStrategy
from cryptobot.strategy.llm_strategy import LLMStrategy
from cryptobot.strategy.nof1 import Nof1Params, Nof1Strategy


def main() -> None:
    parser = argparse.ArgumentParser(description="CryptoBot Live Runner")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config")
    parser.add_argument("--provider", type=str, choices=["ccxt", "random"], default="random")
    parser.add_argument("--exchange", type=str, default="binance")
    parser.add_argument("--with-dashboard", action="store_true")
    parser.add_argument("--dashboard-host", type=str, default="0.0.0.0")
    parser.add_argument("--dashboard-port", type=int, default=8000)
    args = parser.parse_args()

    load_dotenv()
    cfg = AppConfig.load(args.config)
    setup_logging(level="INFO")
    log = get_logger()

    symbol = cfg.general.symbols[0]

    broker = PaperBroker(
        fee_bps=cfg.broker.fee_bps,
        slippage_bps=cfg.broker.slippage_bps,
        starting_cash=cfg.general.capital,
    )
    risk = RiskManager(cfg=cfg.risk)

    # strategies
    nof1 = Nof1Strategy(Nof1Params(
        rsi_period=int(cfg.strategy.params.get("rsi_period", 14)),
        rsi_buy=float(cfg.strategy.params.get("rsi_buy", 30)),
        rsi_sell=float(cfg.strategy.params.get("rsi_sell", 70)),
        ema_fast=int(cfg.strategy.params.get("ema_fast", 12)),
        ema_slow=int(cfg.strategy.params.get("ema_slow", 26)),
        atr_period=int(cfg.strategy.params.get("atr_period", 14)),
        volatility_floor=float(cfg.strategy.params.get("volatility_floor", 0.002)),
    ))

    llm_client = LLMClient.from_env()
    llm_strat = LLMStrategy(client=llm_client)

    strategies = {"nof1_baseline": nof1, "llm": llm_strat}
    weights = cfg.ensemble.weights or {"nof1_baseline": 0.5, "llm": 1.5}
    ensemble = EnsembleStrategy(strategies=strategies, weights=weights)

    overlay_cfg = cfg.ensemble.llm_overlay or {"enabled": True}
    overlay = LLMRiskOverlay(enabled=bool(overlay_cfg.get("enabled", True)), client=llm_client)

    original_additional = risk.additional_qty_allowed

    def overlay_additional_qty_allowed(equity: float, price: float, current_qty: float) -> float:
        mult = overlay.risk_multiplier({"equity": equity, "price": price, "qty": current_qty})
        monitor_state.set_llm_multiplier(mult)
        return max(0.0, original_additional(equity=equity, price=price, current_qty=current_qty) * float(mult))

    risk.additional_qty_allowed = overlay_additional_qty_allowed  # type: ignore

    # Dashboard thread
    if args.with_dashboard:
        def run_dashboard():
            import uvicorn
            uvicorn.run("cryptobot.webapp.api:app", host=args.dashboard_host, port=args.dashboard_port, reload=False, workers=1)
        t = threading.Thread(target=run_dashboard, daemon=True)
        t.start()

    # Live loop
    history: list[dict] = []

    def publish_state(ts: int, price: float) -> None:
        monitor_state.set_positions(broker.portfolio.positions)
        from cryptobot.core.types import PortfolioSnapshot
        eq = broker.portfolio.equity({symbol: price})
        cash = broker.portfolio.cash
        unreal = eq - cash - sum((p.qty * p.avg_price) for p in broker.portfolio.positions.values())
        monitor_state.add_equity(PortfolioSnapshot(timestamp=ts, cash=cash, equity=eq, unrealized_pnl=unreal))

    def handle_bar(bar: Bar) -> None:
        history.append({
            "timestamp": bar.timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        })
        if len(history) < 50:
            publish_state(bar.timestamp, bar.close)
            return
        df = pd.DataFrame(history)
        sig = ensemble.generate_signals(df)
        pos = broker.portfolio.positions.get(symbol)
        qty = pos.qty if pos else 0.0
        decision = ensemble.decide(sig, qty)
        price = float(df.iloc[-1]["close"])    
        if decision == "buy":
            equity = broker.portfolio.equity({symbol: price})
            add_qty = risk.additional_qty_allowed(equity=equity, price=price, current_qty=qty)
            if add_qty > 0:
                from cryptobot.core.types import Order
                import uuid
                order = Order(id=str(uuid.uuid4()), symbol=symbol, side="buy", type="market", qty=add_qty, price=None, timestamp=int(df.iloc[-1]["timestamp"]))
                broker.market_order(order, price)
                log.info(f"BUY {add_qty:.6f} {symbol} @ {price:.2f}")
                monitor_state.add_event({"type": "BUY", "qty": add_qty, "symbol": symbol, "price": price, "ts": int(df.iloc[-1]["timestamp"])})
        elif decision == "sell" and qty > 0:
            from cryptobot.core.types import Order
            import uuid
            order = Order(id=str(uuid.uuid4()), symbol=symbol, side="sell", type="market", qty=qty, price=None, timestamp=int(df.iloc[-1]["timestamp"]))
            broker.market_order(order, price)
            log.info(f"SELL {qty:.6f} {symbol} @ {price:.2f}")
            monitor_state.add_event({"type": "SELL", "qty": qty, "symbol": symbol, "price": price, "ts": int(df.iloc[-1]["timestamp"])})

        publish_state(int(df.iloc[-1]["timestamp"]), price)

    if args.provider == "ccxt":
        api_key = os.getenv("EXCHANGE_API_KEY", "")
        api_secret = os.getenv("EXCHANGE_API_SECRET", "")
        for bar in live_ohlcv(symbol=symbol, timeframe=cfg.general.timeframe, exchange_id=args.exchange, api_key=api_key, api_secret=api_secret):
            handle_bar(bar)
    else:
        start = datetime.fromisoformat(cfg.general.start)
        end = start + timedelta(days=3650)
        params = RandomWalkParams(
            seed=cfg.general.seed,
            start=start,
            end=end,
            timeframe=cfg.general.timeframe,
            steps_per_bar=cfg.data.steps_per_bar,
            drift=cfg.data.drift,
            volatility=cfg.data.volatility,
        )
        for bar in random_walk_bars(symbol=symbol, p=params, start_price=30000.0):
            handle_bar(bar)
            time.sleep(1.0)


if __name__ == "__main__":
    main()
