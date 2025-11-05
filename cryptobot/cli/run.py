from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from cryptobot.backtest.engine import BacktestEngine
from cryptobot.broker.paper import PaperBroker
from cryptobot.broker.risk import RiskManager
from cryptobot.core.config import AppConfig
from cryptobot.core.logging import get_logger, setup_logging
from cryptobot.core.env import load_local_environment
from cryptobot.data.random_walk import RandomWalkParams, random_walk_bars
from cryptobot.strategy.ensemble import EnsembleStrategy
from cryptobot.strategy.nof1 import Nof1Params, Nof1Strategy
from cryptobot.llm.overlay import LLMRiskOverlay


def main() -> None:
    parser = argparse.ArgumentParser(description="CryptoBot Paper Trader")
    parser.add_argument("--config", type=str, required=True, help="Path to YAML config")
    args = parser.parse_args()

    load_local_environment()
    cfg = AppConfig.load(args.config)
    setup_logging(level="INFO")
    log = get_logger()

    symbol = cfg.general.symbols[0]

    # build components
    broker = PaperBroker(
        fee_bps=cfg.broker.fee_bps,
        slippage_bps=cfg.broker.slippage_bps,
        starting_cash=cfg.general.capital,
    )
    risk = RiskManager(cfg=cfg.risk)

    strat = Nof1Strategy(
        Nof1Params(
            rsi_period=int(cfg.strategy.params.get("rsi_period", 14)),
            rsi_buy=float(cfg.strategy.params.get("rsi_buy", 30)),
            rsi_sell=float(cfg.strategy.params.get("rsi_sell", 70)),
            ema_fast=int(cfg.strategy.params.get("ema_fast", 12)),
            ema_slow=int(cfg.strategy.params.get("ema_slow", 26)),
            atr_period=int(cfg.strategy.params.get("atr_period", 14)),
            volatility_floor=float(cfg.strategy.params.get("volatility_floor", 0.002)),
        )
    )

    # optional ensemble wrapper
    strategies = {"nof1_baseline": strat}
    weights = cfg.ensemble.weights or {"nof1_baseline": 1.0}
    ensemble = EnsembleStrategy(strategies=strategies, weights=weights)

    # LLM overlay stub
    overlay_cfg = cfg.ensemble.llm_overlay or {"enabled": False}
    overlay = LLMRiskOverlay(enabled=bool(overlay_cfg.get("enabled", False)))

    # inject overlay into risk sizing via simple monkey wrapper
    original_additional = risk.additional_qty_allowed

    def overlay_additional_qty_allowed(equity: float, price: float, current_qty: float) -> float:
        mult = overlay.risk_multiplier({"equity": equity, "price": price, "qty": current_qty})
        return max(0.0, original_additional(equity=equity, price=price, current_qty=current_qty) * float(mult))

    risk.additional_qty_allowed = overlay_additional_qty_allowed  # type: ignore

    engine = BacktestEngine(broker=broker, strategy=ensemble, symbol=symbol, risk=risk)

    start = datetime.fromisoformat(cfg.general.start)
    end = datetime.fromisoformat(cfg.general.end)
    rw = RandomWalkParams(
        seed=cfg.general.seed,
        start=start,
        end=end,
        timeframe=cfg.general.timeframe,
        steps_per_bar=cfg.data.steps_per_bar,
        drift=cfg.data.drift,
        volatility=cfg.data.volatility,
    )

    bars = random_walk_bars(symbol=symbol, p=rw, start_price=30000.0)
    result = engine.run(bars)

    # basic report
    eq = result.equity_curve
    eq["equity"] = eq["equity"].astype(float)
    ret = eq["equity"].pct_change().fillna(0.0)
    sharpe = (ret.mean() / (ret.std() + 1e-12)) * (252 ** 0.5)

    log.info(f"Final equity: {eq['equity'].iloc[-1]:.2f}")
    log.info(f"Sharpe (naive): {sharpe:.2f}")

    outdir = Path(cfg.backtest.report.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    out_csv = outdir / "equity_curve.csv"
    eq.to_csv(out_csv, index=False)
    log.info(f"Saved equity curve to {out_csv}")


if __name__ == "__main__":
    main()
