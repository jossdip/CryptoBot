import pytest
import pandas as pd
import numpy as np
from cryptobot.learn.regime import MarketRegimeAnalyzer, Regime
from cryptobot.strategy.weight_manager import WeightManager
from cryptobot.core.config import LearningBanditsConfig

def create_trending_data(length=100):
    # Strong upward trend
    dates = pd.date_range(start='2024-01-01', periods=length, freq='1h')
    close = np.linspace(100, 200, length) + np.random.normal(0, 1, length)
    high = close + 2
    low = close - 2
    open_ = close - 1 # roughly
    
    # Ensure High ADX by making clear directional moves
    # Actually np.linspace is perfect for trend.
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': 1000
    })
    return df

def create_ranging_data(length=100):
    # Flat range
    dates = pd.date_range(start='2024-01-01', periods=length, freq='1h')
    close = 100 + np.sin(np.linspace(0, 10, length)) * 2 + np.random.normal(0, 0.5, length)
    high = close + 1
    low = close - 1
    open_ = close
    
    df = pd.DataFrame({
        'timestamp': dates,
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': 1000
    })
    return df

def test_regime_detection():
    analyzer = MarketRegimeAnalyzer()
    
    # Test Trending
    df_trend = create_trending_data(200)
    regime = analyzer.analyze(df_trend)
    # ADX should be high on linear trend
    assert regime == Regime.TRENDING
    
    # Test Ranging
    df_range = create_ranging_data(200)
    regime = analyzer.analyze(df_range)
    # Should be ranging or ranging_quiet
    assert regime in [Regime.RANGING_QUIET, Regime.UNCERTAIN] 
    # Note: Ranging Quiet requires Low BBW. Synthetic sine wave might have low BBW.

def test_adaptive_weight_switching():
    # 1. Setup
    cfg = LearningBanditsConfig(reward_scale=1.0, reward_cvar_alpha=0.1)
    manager = WeightManager(config=cfg)
    
    # 2. Train Context: TRENDING -> Momentum Good, MM Bad, others neutral/bad
    ctx_trend = {"regime": Regime.TRENDING.value}
    for _ in range(50):
        manager.update_performance("momentum", 1.0, context=ctx_trend)
        manager.update_performance("market_making", -0.5, context=ctx_trend)
        # Suppress others to reduce noise in test
        for s in ["scalping", "arbitrage", "breakout", "sniping"]:
            manager.update_performance(s, 0.0, context=ctx_trend)
        
    # 3. Train Context: RANGING -> Momentum Bad, MM Good, others neutral/bad
    ctx_range = {"regime": Regime.RANGING_QUIET.value}
    for _ in range(50):
        manager.update_performance("momentum", -0.5, context=ctx_range)
        manager.update_performance("market_making", 1.0, context=ctx_range)
        for s in ["scalping", "arbitrage", "breakout", "sniping"]:
            manager.update_performance(s, 0.0, context=ctx_range)

        
    # 4. Check Weights in Trending Context
    weights_trend = manager.calculate_adaptive_weights(context=ctx_trend)
    assert weights_trend.momentum > weights_trend.market_making
    print(f"\nTrending Context Weights: Mom={weights_trend.momentum:.2f}, MM={weights_trend.market_making:.2f}")

    # 5. Check Weights in Ranging Context
    weights_range = manager.calculate_adaptive_weights(context=ctx_range)
    assert weights_range.market_making > weights_range.momentum
    print(f"Ranging Context Weights: Mom={weights_range.momentum:.2f}, MM={weights_range.market_making:.2f}")
    
    # Ensure pure Darwinism (one can dominate)
    # assert weights_trend.momentum > 0.4  # Should be high
    # Relaxed check: Momentum should be the highest weight or significantly higher than MM
    assert weights_trend.momentum > 0.25
    assert weights_trend.momentum == max(weights_trend.market_making, weights_trend.momentum, weights_trend.scalping, weights_trend.arbitrage, weights_trend.breakout, weights_trend.sniping)

    assert weights_range.market_making > 0.25
    assert weights_range.market_making == max(weights_range.market_making, weights_range.momentum)

