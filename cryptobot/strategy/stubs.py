from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class ArbitrageStrategy:
    threshold_bps: float = 5.0

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def decide(self, df: pd.DataFrame, position_qty: float) -> Optional[str]:
        return None


@dataclass
class HalvingBiasStrategy:
    bias_days: int = 90

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def decide(self, df: pd.DataFrame, position_qty: float) -> Optional[str]:
        return None


@dataclass
class SnipingStrategy:
    spike_sigma: float = 3.0

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        return df

    def decide(self, df: pd.DataFrame, position_qty: float) -> Optional[str]:
        return None
