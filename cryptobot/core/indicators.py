from __future__ import annotations

import pandas as pd
import numpy as np


def ema(series: pd.Series, window: int) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    return series.ewm(span=window, adjust=False, min_periods=window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-12)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr_series = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    return atr_series.bfill().fillna(0.0)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate Average Directional Index (ADX)."""
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")

    # 1. Calculate Directional Movement
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)

    plus_dm[(up_move > down_move) & (up_move > 0)] = up_move
    minus_dm[(down_move > up_move) & (down_move > 0)] = down_move

    # 2. Calculate Smoothed TR, +DM, -DM using Wilder's smoothing (alpha=1/period)
    # Re-calculate TR specifically for ADX to ensure alignment, though atr() helper is similar
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    alpha = 1 / period
    tr_smooth = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    # 3. Calculate +DI, -DI
    plus_di = 100 * (plus_dm_smooth / (tr_smooth + 1e-12))
    minus_di = 100 * (minus_dm_smooth / (tr_smooth + 1e-12))

    # 4. Calculate DX and ADX
    dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-12))
    adx_s = dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()

    return adx_s.fillna(0.0)


def bollinger_bandwidth(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.Series:
    """Calculate Bollinger Bandwidth: (Upper - Lower) / Middle."""
    close = pd.to_numeric(close, errors="coerce")
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    bandwidth = (upper - lower) / (sma + 1e-12)
    return bandwidth.fillna(0.0)


def donchian_channels(high: pd.Series, low: pd.Series, window: int = 20) -> pd.DataFrame:
    """Calculate Donchian Channels (Upper, Lower, Mid)."""
    high = pd.to_numeric(high, errors="coerce")
    low = pd.to_numeric(low, errors="coerce")
    upper = high.rolling(window=window).max()
    lower = low.rolling(window=window).min()
    mid = (upper + lower) / 2.0
    return pd.DataFrame({
        "donchian_upper": upper,
        "donchian_lower": lower,
        "donchian_mid": mid
    }).fillna(method='bfill')
