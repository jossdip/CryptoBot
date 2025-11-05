from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
import threading

import pandas as pd

from cryptobot.broker.paper import PaperBroker
from cryptobot.broker.futures_paper import FuturesPaperBroker
from cryptobot.broker.exchange_testnet import ExchangeTestnetBroker
from cryptobot.broker.risk import RiskManager
from cryptobot.core.config import AppConfig
from cryptobot.core.logging import get_logger, setup_logging
from cryptobot.core.types import Bar
from cryptobot.core.env import load_local_environment
from cryptobot.data.ccxt_live import live_ohlcv
from cryptobot.data.coingecko import fetch_market_metadata
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
    parser.add_argument("--exchange", type=str, default=None)
    parser.add_argument("--with-dashboard", action="store_true")
    parser.add_argument("--dashboard-host", type=str, default="0.0.0.0")
    parser.add_argument("--dashboard-port", type=int, default=8000)
    args = parser.parse_args()

    load_local_environment()
    cfg = AppConfig.load(args.config)
    setup_logging(level="INFO")
    log = get_logger()

    log.info("=" * 60)
    log.info("CryptoBot Live Runner starting...")
    log.info(f"Config: {args.config}")
    log.info(f"Provider: {args.provider}")
    ex_from_cfg = getattr(cfg.general, "exchange_id", None)
    exchange_id = args.exchange or ex_from_cfg or ("binanceusdm" if cfg.general.market_type == "futures" else "binance")
    log.info(f"Exchange: {exchange_id}")
    
    symbol = cfg.general.symbols[0]
    log.info(f"Symbol: {symbol}")
    log.info(f"Capital: {cfg.general.capital}")
    log.info(f"Timeframe: {cfg.general.timeframe}")

    market_type = getattr(cfg.general, "market_type", "spot")
    
    # Check if we should use real testnet exchange broker
    api_key = os.getenv("EXCHANGE_API_KEY", "")
    api_secret = os.getenv("EXCHANGE_API_SECRET", "")
    use_testnet_broker = bool(getattr(cfg.broker, "place_on_testnet", False)) and api_key and api_secret
    
    if use_testnet_broker:
        log.info("=" * 60)
        log.info("USING REAL EXCHANGE TESTNET BROKER")
        log.info("Orders will be placed on exchange testnet (virtual funds)")
        log.info("=" * 60)
        try:
            broker = ExchangeTestnetBroker(
                exchange_id=exchange_id,
                api_key=api_key,
                api_secret=api_secret,
                market_type=market_type,
                testnet=bool(cfg.broker.testnet),
            )
            log.info(f"Connected to {exchange_id} testnet successfully")
        except Exception as e:
            log.error(f"Failed to connect to exchange testnet: {e}")
            log.error("Falling back to paper broker")
            use_testnet_broker = False
            if market_type == "futures":
                broker = FuturesPaperBroker(
                    fee_bps=max(2.0, cfg.broker.fee_bps),
                    slippage_bps=cfg.broker.slippage_bps,
                    starting_cash=cfg.general.capital,
                    default_leverage=cfg.broker.default_leverage,
                    max_leverage=cfg.broker.max_leverage,
                    margin_mode=cfg.broker.margin_mode,
                )
            else:
                broker = PaperBroker(
                    fee_bps=cfg.broker.fee_bps,
                    slippage_bps=cfg.broker.slippage_bps,
                    starting_cash=cfg.general.capital,
                )
    else:
        # Use paper broker simulation
        log.info("Using paper broker simulation (no real orders)")
        if market_type == "futures":
            broker = FuturesPaperBroker(
                fee_bps=max(2.0, cfg.broker.fee_bps),
                slippage_bps=cfg.broker.slippage_bps,
                starting_cash=cfg.general.capital,
                default_leverage=cfg.broker.default_leverage,
                max_leverage=cfg.broker.max_leverage,
                margin_mode=cfg.broker.margin_mode,
            )
        else:
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
    
    log.info(f"Ensemble weights: {weights}")
    overlay_cfg = cfg.ensemble.llm_overlay or {"enabled": True}
    log.info(f"LLM overlay enabled: {bool(overlay_cfg.get('enabled', True))}")
    if llm_client.api_key:
        log.info("DeepSeek API key: CONFIGURED")
    else:
        log.warning("DeepSeek API key: NOT CONFIGURED (LLM will use defaults)")

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
        if use_testnet_broker:
            portfolio = broker.get_portfolio()
            monitor_state.set_positions(portfolio.positions)
        else:
            monitor_state.set_positions(broker.portfolio.positions)
        from cryptobot.core.types import PortfolioSnapshot
        if use_testnet_broker:
            # Exchange testnet broker provides equity directly
            eq = broker.equity()
            portfolio = broker.get_portfolio()
            cash = portfolio.cash
            unreal = eq - cash
        else:
            # Paper broker needs current price
            eq = broker.portfolio.equity({symbol: price})
            cash = broker.portfolio.cash
            unreal = eq - cash - sum((p.qty * p.avg_price) for p in broker.portfolio.positions.values())
        monitor_state.add_equity(PortfolioSnapshot(timestamp=ts, cash=cash, equity=eq, unrealized_pnl=unreal))


    # Optional coin metadata for LLM context
    coin_meta = {}
    try:
        coin_meta = fetch_market_metadata(symbol)
    except Exception:
        coin_meta = {}

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
            if len(history) == 1:
                log.info(f"Collecting market data... ({len(history)}/50 bars) - First bar: {bar.close:.2f}")
            elif len(history) % 10 == 0:
                log.info(f"Collecting market data... ({len(history)}/50 bars)")
            publish_state(bar.timestamp, bar.close)
            return
        df = pd.DataFrame(history)
        sig = ensemble.generate_signals(df)
        if use_testnet_broker:
            portfolio = broker.get_portfolio()
            pos = portfolio.positions.get(symbol)
            qty = pos.qty if pos else 0.0
        else:
            pos = broker.portfolio.positions.get(symbol)
            qty = pos.qty if pos else 0.0
        price = float(df.iloc[-1]["close"]) 

        if market_type == "futures":
            # LLM-driven direction + leverage
            decision = llm_strat.decide_futures(sig, extra_context={"coin": coin_meta, "position_qty": float(qty)})
            direction = str(decision.get("direction", "flat"))
            lev = int(decision.get("leverage", cfg.broker.default_leverage))
            lev = max(1, min(cfg.broker.max_leverage, lev))
            if use_testnet_broker:
                equity = broker.equity()
            else:
                equity = broker.portfolio.equity({symbol: price})
            add_qty = risk.additional_qty_allowed(equity=equity, price=price, current_qty=qty, leverage=float(lev))
            from cryptobot.core.types import Order
            import uuid
            ts = int(df.iloc[-1]["timestamp"])
            if direction == "long" and add_qty > 0:
                order = Order(id=str(uuid.uuid4()), symbol=symbol, side="buy", type="market", qty=add_qty, price=None, timestamp=ts)
                if use_testnet_broker:
                    fill = broker.market_order(order, leverage=lev)  # type: ignore[arg-type]
                    exec_price = fill.price if fill else price
                else:
                    fill = broker.market_order(order, price, leverage=lev)  # type: ignore[arg-type]
                    exec_price = fill.price if fill else price
                log.info(f"OPEN/LONG +{add_qty:.6f}x @ {exec_price:.2f} lev={lev}")
                monitor_state.add_event({"type": "OPEN_LONG", "qty": add_qty, "symbol": symbol, "price": exec_price, "lev": lev, "ts": ts})
            elif direction == "short" and add_qty > 0:
                order = Order(id=str(uuid.uuid4()), symbol=symbol, side="sell", type="market", qty=add_qty, price=None, timestamp=ts)
                if use_testnet_broker:
                    fill = broker.market_order(order, leverage=lev)  # type: ignore[arg-type]
                    exec_price = fill.price if fill else price
                else:
                    fill = broker.market_order(order, price, leverage=lev)  # type: ignore[arg-type]
                    exec_price = fill.price if fill else price
                log.info(f"OPEN/SHORT -{add_qty:.6f}x @ {exec_price:.2f} lev={lev}")
                monitor_state.add_event({"type": "OPEN_SHORT", "qty": add_qty, "symbol": symbol, "price": exec_price, "lev": lev, "ts": ts})
            elif direction == "flat" and qty != 0.0:
                # Close entire position
                side = "buy" if qty < 0 else "sell"
                close_qty = abs(qty)
                order = Order(id=str(uuid.uuid4()), symbol=symbol, side=side, type="market", qty=close_qty, price=None, timestamp=ts)
                if use_testnet_broker:
                    fill = broker.market_order(order, leverage=lev)  # type: ignore[arg-type]
                    exec_price = fill.price if fill else price
                else:
                    fill = broker.market_order(order, price, leverage=lev)  # type: ignore[arg-type]
                    exec_price = fill.price if fill else price
                log.info(f"CLOSE {close_qty:.6f} @ {exec_price:.2f}")
                monitor_state.add_event({"type": "CLOSE", "qty": close_qty, "symbol": symbol, "price": exec_price, "ts": ts})
        else:
            decision = ensemble.decide(sig, qty)
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
        for bar in live_ohlcv(
            symbol=symbol,
            timeframe=cfg.general.timeframe,
            exchange_id=exchange_id,
            api_key=api_key,
            api_secret=api_secret,
            market_type=market_type,
            testnet=bool(cfg.broker.testnet),
        ):
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
        log.info("Starting random walk data provider...")
        log.info(f"Starting price: 30000.0, Seed: {params.seed}, Volatility: {params.volatility}")
        bar_count = 0
        for bar in random_walk_bars(symbol=symbol, p=params, start_price=30000.0):
            handle_bar(bar)
            bar_count += 1
            if bar_count == 1:
                log.info("Processing bars... (waiting for 50 bars before trading)")
            time.sleep(1.0)


if __name__ == "__main__":
    main()
