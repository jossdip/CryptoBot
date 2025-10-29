from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, PositiveFloat


class GeneralConfig(BaseModel):
    seed: int = 42
    start: str
    end: str
    timeframe: str = "5m"
    capital: PositiveFloat = 10000.0
    symbols: List[str] = Field(default_factory=lambda: ["BTC/USDT"]) 


class DataConfig(BaseModel):
    provider: str = "random_walk"
    steps_per_bar: int = 20
    drift: float = 0.0
    volatility: PositiveFloat = 0.02


class BrokerConfig(BaseModel):
    fee_bps: float = 10.0
    slippage_bps: float = 5.0


class RiskConfig(BaseModel):
    max_position_pct: float = 0.2
    max_daily_drawdown_pct: float = 5.0


class StrategyConfig(BaseModel):
    name: str
    params: Dict[str, float] = Field(default_factory=dict)


class EnsembleConfig(BaseModel):
    weights: Dict[str, float] = Field(default_factory=dict)
    llm_overlay: Dict[str, Optional[bool]] = Field(default_factory=lambda: {"enabled": False})


class BacktestReportConfig(BaseModel):
    output_dir: str = "logs/reports"


class BacktestConfig(BaseModel):
    report: BacktestReportConfig = Field(default_factory=BacktestReportConfig)


class AppConfig(BaseModel):
    general: GeneralConfig
    data: DataConfig
    broker: BrokerConfig
    risk: RiskConfig
    strategy: StrategyConfig
    ensemble: EnsembleConfig
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)

    @staticmethod
    def load(path: str | Path) -> "AppConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return AppConfig(**data)
