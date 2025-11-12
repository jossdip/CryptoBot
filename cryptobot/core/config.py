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
    market_type: str = "spot"  # "spot" | "futures"
    exchange_id: str = "binance"  # e.g., "binance", "binanceusdm", "bybit", "okx"


class DataConfig(BaseModel):
    provider: str = "random_walk"
    steps_per_bar: int = 20
    drift: float = 0.0
    volatility: PositiveFloat = 0.02
    # Hyperliquid-specific toggles
    monitor_new_listings: bool = False


class BrokerConfig(BaseModel):
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    # Futures-specific (ignored for spot)
    testnet: bool = False
    margin_mode: str = "isolated"  # "isolated" | "cross"
    default_leverage: int = 5
    max_leverage: int = 20
    place_on_testnet: bool = False  # mirror paper orders to exchange testnet when keys provided


class RiskConfig(BaseModel):
    max_position_pct: float = 0.2
    max_daily_drawdown_pct: float = 5.0


class StrategyConfig(BaseModel):
    name: str = "nof1_baseline"
    params: Dict[str, float] = Field(default_factory=dict)


class EnsembleConfig(BaseModel):
    weights: Dict[str, float] = Field(default_factory=dict)
    llm_overlay: Dict[str, Optional[bool]] = Field(default_factory=lambda: {"enabled": False})


class HyperliquidConfig(BaseModel):
    testnet: bool = True
    wallet_address: str = ""
    private_key: str = ""
    default_leverage: int = 10
    max_leverage: int = 50
    margin_mode: str = "isolated"


class LLMConfig(BaseModel):
    enabled: bool = True
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    decision_interval_sec: int = 30
    context_window_bars: int = 60
    allocation_interval_sec: int = 30  # Intervalle pour allocation stratégies (peut être > decision_interval_sec)
    max_opportunities_per_cycle: int = 999  # Limite opportunités par cycle (filtre pour réduire coûts)
    min_opportunity_score: float = 0.0  # Score minimum avant appel LLM (0.0 = pas de filtre, 0.6+ = filtre actif)
    monthly_budget_usd: float = 0.0  # Budget mensuel max (0.0 = illimité)
    min_confidence_to_execute: float = 0.6  # Seuil d'exécution des trades (par défaut 0.6)
    evaluation_horizon_sec: int = 60  # Horizon d'évaluation pour feedback (PNL proxy)
    adaptive_fallback_enabled: bool = True  # Active le fallback adaptatif quand LLM est indisponible


class StrategyWeightsConfig(BaseModel):
    initial_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "market_making": 0.35,  # Base stable, #1 strategy
            "momentum": 0.25,  # Follow trends, #2 strategy
            "scalping": 0.15,  # Frequent trades, #3 strategy
            "arbitrage": 0.12,  # Safe but limited, #4 strategy
            "breakout": 0.08,  # Less frequent but big moves, #5 strategy
            "sniping": 0.05,  # Very risky, limit exposure, #6 strategy
        }
    )


class SentimentSubConfig(BaseModel):
    enabled: bool = False
    subreddits: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    check_interval_sec: int = 300


class SentimentConfig(BaseModel):
    reddit: SentimentSubConfig = Field(default_factory=SentimentSubConfig)
    twitter: SentimentSubConfig = Field(default_factory=SentimentSubConfig)
    polymarket: SentimentSubConfig = Field(default_factory=SentimentSubConfig)


class BacktestReportConfig(BaseModel):
    output_dir: str = "logs/reports"


class BacktestConfig(BaseModel):
    report: BacktestReportConfig = Field(default_factory=BacktestReportConfig)


class CLIConfig(BaseModel):
    interactive: bool = True
    logo_enabled: bool = True
    prompt_format: str = "[C4$H@{exchange}:{status}] > "


class MonitorConfig(BaseModel):
    enabled: bool = True
    storage_type: str = "sqlite"  # "sqlite" | "json"
    storage_path: str = "~/.cryptobot/monitor.db"
    collect_interval_sec: int = 5
    retention_days: int = 30
    llm_insights_enabled: bool = True


class LearningMemoryConfig(BaseModel):
    enabled: bool = True
    knn_k: int = 8
    max_episodes: int = 50000
    # none | sbert-mini | openai-text-ada (we only implement 'none' + optional 'sbert-mini' fallback)
    embedder: str = "none"


class LearningBanditsConfig(BaseModel):
    update_cadence_sec: int = 60
    reward_cvar_alpha: float = 0.2
    reward_scale: float = 1.0
    # per_strategy is a free-form mapping where each strategy may override grids.
    # Example:
    #   {
    #     "default": {
    #       "leverage_grid": [2,4,6,8,10],
    #       "tp_grid_pct": [0.006,0.008,0.010,0.012,0.015],
    #       "sl_grid_pct": [0.004,0.005,0.006,0.008,0.010],
    #       "min_conf_grid": [0.50,0.55,0.60,0.65,0.70]
    #     },
    #     "momentum": {"leverage_grid": [6,10,14,18,20]},
    #     ...
    #   }
    per_strategy: Dict[str, Dict[str, List[float]]] = Field(
        default_factory=lambda: {
            "default": {
                "leverage_grid": [2, 4, 6, 8, 10],
                "tp_grid_pct": [0.006, 0.008, 0.010, 0.012, 0.015],
                "sl_grid_pct": [0.004, 0.005, 0.006, 0.008, 0.010],
                "min_conf_grid": [0.50, 0.55, 0.60, 0.65, 0.70],
            },
            "momentum": {"leverage_grid": [6, 10, 14, 18, 20]},
            "breakout": {"leverage_grid": [6, 10, 14, 18, 20]},
            "scalping": {"leverage_grid": [4, 8, 10, 12]},
            "sniping": {"leverage_grid": [8, 12, 16, 20, 25]},
        }
    )


class LearningBOConfig(BaseModel):
    enabled: bool = False
    min_samples: int = 100
    update_cadence_sec: int = 180


class LearningRLConfig(BaseModel):
    enabled: bool = False
    policy_path: str = "models/policy_rl.pt"
    blend_weight: float = 0.25


class LearningConfig(BaseModel):
    enabled: bool = False
    # allocation_mode: llm_only | bandit_only | hybrid
    allocation_mode: str = "hybrid"
    allocation_hybrid_blend: float = 0.5  # contribution of bandit when hybrid
    # param_mode: static | bandit | bo
    param_mode: str = "bandit"
    memory: LearningMemoryConfig = Field(default_factory=LearningMemoryConfig)
    bandits: LearningBanditsConfig = Field(default_factory=LearningBanditsConfig)
    bo: LearningBOConfig = Field(default_factory=LearningBOConfig)
    rl: LearningRLConfig = Field(default_factory=LearningRLConfig)


class AppConfig(BaseModel):
    general: GeneralConfig
    data: DataConfig
    broker: BrokerConfig
    risk: RiskConfig
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    ensemble: EnsembleConfig = Field(default_factory=EnsembleConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)
    # Optional sections for Hyperliquid/LLM live trading
    hyperliquid: HyperliquidConfig = Field(default_factory=HyperliquidConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    strategy_weights: StrategyWeightsConfig = Field(default_factory=StrategyWeightsConfig)
    sentiment: SentimentConfig = Field(default_factory=SentimentConfig)
    cli: CLIConfig = Field(default_factory=CLIConfig)
    monitor: MonitorConfig = Field(default_factory=MonitorConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)

    @staticmethod
    def load(path: str | Path) -> "AppConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return AppConfig(**data)
