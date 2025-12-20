"""
Technical indicators using pandas and TA-Lib.
Replacement for the old deprecated pandas methods.
"""

import pandas as pd
import numpy as np
from typing import Tuple

def sma(data: pd.Series, period: int) -> pd.Series:
    """
    Simple Moving Average.
    
    Args:
        data: Price series
        period: Number of periods
    
    Returns:
        SMA series
    """
    return data.rolling(window=period).mean()


def ema(data: pd.Series, period: int) -> pd.Series:
    """
    Exponential Moving Average.
    
    Args:
        data: Price series
        period: Number of periods
    
    Returns:
        EMA series
    """
    return data.ewm(span=period, adjust=False).mean()


def rsi(data: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index.
    
    Args:
        data: Price series
        period: RSI period
    
    Returns:
        RSI series (0-100)
    """
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def macd(
    data: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Moving Average Convergence Divergence.
    
    Args:
        data: Price series
        fast_period: Fast EMA period
        slow_period: Slow EMA period
        signal_period: Signal line period
    
    Returns:
        Tuple of (MACD line, Signal line, Histogram)
    """
    fast = ema(data, fast_period)
    slow = ema(data, slow_period)
    macd_line = fast - slow
    signal_line = ema(macd_line, signal_period)
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram


def bollinger_bands(
    data: pd.Series,
    period: int = 20,
    std_dev: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Bollinger Bands.
    
    Args:
        data: Price series
        period: Moving average period
        std_dev: Number of standard deviations
    
    Returns:
        Tuple of (Upper band, Middle band, Lower band)
    """
    middle = sma(data, period)
    std = data.rolling(window=period).std()
    
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return upper, middle, lower


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Average True Range.
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ATR period
    
    Returns:
        ATR series
    """
    high_low = high - low
    high_close = abs(high - close.shift())
    low_close = abs(low - close.shift())
    
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    
    return atr


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    smooth_k: int = 3,
    smooth_d: int = 3
) -> Tuple[pd.Series, pd.Series]:
    """
    Stochastic Oscillator.
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: Stochastic period
        smooth_k: %K smoothing period
        smooth_d: %D smoothing period
    
    Returns:
        Tuple of (%K, %D)
    """
    lowest_low = low.rolling(window=period).min()
    highest_high = high.rolling(window=period).max()
    
    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    k = raw_k.rolling(window=smooth_k).mean()
    d = k.rolling(window=smooth_d).mean()
    
    return k, d


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Average Directional Index (trend strength).
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ADX period
    
    Returns:
        ADX series (0-100)
    """
    # Calculate +DM and -DM
    high_diff = high.diff()
    low_diff = -low.diff()
    
    plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0)
    minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0)
    
    # Calculate ATR
    atr_val = atr(high, low, close, period)
    
    # Calculate +DI and -DI
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_val)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_val)
    
    # Calculate DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    
    return adx


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """
    On-Balance Volume.
    
    Args:
        close: Close price series
        volume: Volume series
    
    Returns:
        OBV series
    """
    direction = np.where(close.diff() > 0, 1, np.where(close.diff() < 0, -1, 0))
    obv_values = (direction * volume).cumsum()
    
    return pd.Series(obv_values, index=close.index)


def support_resistance_levels(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 20
) -> Tuple[float, float, float]:
    """
    Calculate support and resistance levels using recent price action.
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        lookback: Number of periods to look back
    
    Returns:
        Tuple of (resistance, pivot, support)
    """
    recent_high = high.tail(lookback).max()
    recent_low = low.tail(lookback).min()
    recent_close = close.iloc[-1]
    
    pivot = (recent_high + recent_low + recent_close) / 3
    resistance = (2 * pivot) - recent_low
    support = (2 * pivot) - recent_high
    
    return resistance, pivot, support
