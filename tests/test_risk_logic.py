import unittest
import pandas as pd
import numpy as np
from cryptobot.core.config import RiskConfig
from cryptobot.broker.risk import RiskManager

class TestRiskLogic(unittest.TestCase):
    def setUp(self):
        self.cfg = RiskConfig(max_position_pct=0.1, max_daily_drawdown_pct=10.0)
        self.risk = RiskManager(cfg=self.cfg)

    def test_conviction_leverage_mapping(self):
        equity = 1000.0
        
        # Score < 70 -> No trade
        size, lev = self.risk.get_position_size_and_leverage(60, equity)
        self.assertEqual(size, 0.0)
        self.assertEqual(lev, 0)

        # Score 75 (Range 70-85) -> Lev 2 (based on my impl, plan said 1x-2x)
        size, lev = self.risk.get_position_size_and_leverage(75, equity)
        self.assertEqual(lev, 2)
        # Size = Equity * max_pos_pct * lev = 1000 * 0.1 * 2 = 200
        self.assertAlmostEqual(size, 200.0)

        # Score 95 (Range > 90) -> Lev 5 (Plan: 3x-5x)
        size, lev = self.risk.get_position_size_and_leverage(95, equity)
        self.assertEqual(lev, 5)
        self.assertAlmostEqual(size, 500.0)

    def test_circuit_breaker(self):
        self.risk.daily_start_equity = 1000.0
        
        # 5% loss -> OK
        is_tripped = self.risk.check_drawdown_circuit_breaker(950.0)
        self.assertFalse(is_tripped)
        
        # 11% loss -> Tripped
        is_tripped = self.risk.check_drawdown_circuit_breaker(890.0)
        self.assertTrue(is_tripped)
        self.assertTrue(self.risk.circuit_breaker_tripped)
        
        # Subsequent check
        is_tripped = self.risk.check_drawdown_circuit_breaker(890.0)
        self.assertTrue(is_tripped)

    def test_conviction_score_calculation(self):
        # Create synthetic market data
        dates = pd.date_range(start='2023-01-01', periods=300, freq='5min')
        df = pd.DataFrame(index=dates)
        
        # Uptrend: Price > EMA200
        # EMA200 starts effectively after 200 periods.
        # Linear growth
        df['close'] = np.linspace(100, 200, 300)
        df['high'] = df['close'] + 1
        df['low'] = df['close'] - 1
        df['volume'] = 1000.0
        
        # Spike volume at end
        df.iloc[-1, df.columns.get_loc('volume')] = 2000.0 # 2x average
        
        score = self.risk.calculate_conviction_score(df)
        # Should be high: Trend (40) + Volume (30) + Volatility (Healthy)
        # Trend: 40 (Price > EMA)
        # Volume: 30 (Current 2000 > Avg 1000 * 1.5)
        # ATR: 2.0 / 200 = 1% -> Score 30
        # Total 100
        self.assertGreaterEqual(score, 90)

if __name__ == '__main__':
    unittest.main()

