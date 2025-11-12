from __future__ import annotations

from cryptobot.core.config import LearningBanditsConfig
from cryptobot.learn.bandits import StrategyAllocationBandit, ParamBandit


def test_allocation_bandit_updates_and_proposes() -> None:
    cfg = LearningBanditsConfig()
    bandit = StrategyAllocationBandit(
        strategies=["market_making", "momentum", "scalping", "arbitrage", "breakout", "sniping"],
        config=cfg,
    )
    # Provide some rewards to bias momentum positively
    for _ in range(10):
        bandit.update(strategy="momentum", reward=1.0)
        bandit.update(strategy="market_making", reward=0.0)
        bandit.update(strategy="sniping", reward=-0.5)
    w = bandit.propose_weights()
    assert isinstance(w, dict) and all(k in w for k in ["momentum", "market_making"])
    assert w["momentum"] > 0.0


def test_param_bandit_proposes_and_updates() -> None:
    cfg = LearningBanditsConfig()
    pb = ParamBandit(config=cfg)
    s = "momentum"
    props = pb.propose(strategy=s, features={"volatility_1m": 0.01})
    assert "leverage" in props and "tp_pct" in props and "sl_pct" in props
    # Reward this choice and ensure stats update without error
    pb.update(strategy=s, reward=0.5, features={"volatility_1m": 0.01})

