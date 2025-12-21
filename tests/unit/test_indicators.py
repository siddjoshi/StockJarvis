# tests/unit/test_indicators.py
"""
Unit tests for technical indicators.
Tests SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Supertrend, and other indicators.
"""

import pytest
import pandas as pd
import numpy as np
from typing import Tuple

from indicators.technical import (
    sma,
    ema,
    rsi,
    macd,
    bollinger_bands,
    atr,
    stochastic,
    adx,
    obv,
    support_resistance_levels
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_price_series() -> pd.Series:
    """
    Create sample price series for testing.
    
    Returns:
        Series: 50 price data points
    """
    np.random.seed(42)
    # Generate realistic price movement using random walk
    returns = np.random.normal(0.001, 0.02, 50)
    prices = 100 * (1 + returns).cumprod()
    return pd.Series(prices)


@pytest.fixture
def sample_ohlc_data() -> pd.DataFrame:
    """
    Create sample OHLC data for testing.
    
    Returns:
        DataFrame: 50 bars of OHLC data
    """
    np.random.seed(42)
    dates = pd.date_range(end='2024-01-01', periods=50, freq='D')
    
    close_prices = 100 * (1 + np.random.normal(0.001, 0.02, 50)).cumprod()
    
    # Generate realistic OHLC
    data = pd.DataFrame({
        'open': close_prices * (1 + np.random.uniform(-0.01, 0.01, 50)),
        'high': close_prices * (1 + np.random.uniform(0, 0.02, 50)),
        'low': close_prices * (1 + np.random.uniform(-0.02, 0, 50)),
        'close': close_prices,
        'volume': np.random.randint(100000, 1000000, 50)
    }, index=dates)
    
    return data


@pytest.fixture
def trending_up_series() -> pd.Series:
    """
    Create consistently upward trending price series.
    
    Returns:
        Series: Uptrending prices
    """
    return pd.Series([100 + i for i in range(50)])


@pytest.fixture
def trending_down_series() -> pd.Series:
    """
    Create consistently downward trending price series.
    
    Returns:
        Series: Downtrending prices
    """
    return pd.Series([150 - i for i in range(50)])


# ============================================================================
# Test SMA (Simple Moving Average)
# ============================================================================

class TestSMA:
    """Test Simple Moving Average indicator."""
    
    def test_sma_calculation(self, sample_price_series):
        """Test SMA calculation with valid data."""
        result = sma(sample_price_series, period=10)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_price_series)
        assert not result.iloc[-1] != result.iloc[-1]  # Check not NaN at end
    
    def test_sma_first_values_nan(self, sample_price_series):
        """Test that first (period-1) values are NaN."""
        period = 10
        result = sma(sample_price_series, period=period)
        
        # First 9 values should be NaN
        assert result.iloc[:period-1].isna().all()
        # 10th value onwards should not be NaN
        assert not result.iloc[period-1:].isna().any()
    
    def test_sma_value_correctness(self):
        """Test SMA calculation with known values."""
        prices = pd.Series([10, 20, 30, 40, 50])
        result = sma(prices, period=3)
        
        # Expected: [NaN, NaN, 20, 30, 40]
        assert pd.isna(result.iloc[0])
        assert pd.isna(result.iloc[1])
        assert result.iloc[2] == 20.0  # (10+20+30)/3
        assert result.iloc[3] == 30.0  # (20+30+40)/3
        assert result.iloc[4] == 40.0  # (30+40+50)/3
    
    def test_sma_period_one(self, sample_price_series):
        """Test SMA with period=1 (should equal original series)."""
        result = sma(sample_price_series, period=1)
        
        pd.testing.assert_series_equal(result, sample_price_series)
    
    def test_sma_different_periods(self, sample_price_series):
        """Test SMA with different periods."""
        sma_10 = sma(sample_price_series, period=10)
        sma_20 = sma(sample_price_series, period=20)
        
        # SMA with longer period should be smoother (less volatile)
        assert sma_10.std() >= sma_20.std()


# ============================================================================
# Test EMA (Exponential Moving Average)
# ============================================================================

class TestEMA:
    """Test Exponential Moving Average indicator."""
    
    def test_ema_calculation(self, sample_price_series):
        """Test EMA calculation with valid data."""
        result = ema(sample_price_series, period=10)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_price_series)
        assert not result.iloc[-1] != result.iloc[-1]  # Check not NaN at end
    
    def test_ema_responds_faster_than_sma(self, trending_up_series):
        """Test that EMA responds faster to price changes than SMA."""
        ema_10 = ema(trending_up_series, period=10)
        sma_10 = sma(trending_up_series, period=10)
        
        # In uptrend, EMA should be higher than SMA (responds faster)
        # Compare last 10 values
        assert (ema_10.iloc[-10:] > sma_10.iloc[-10:]).all()
    
    def test_ema_value_correctness(self):
        """Test EMA calculation with known values."""
        prices = pd.Series([10, 11, 12, 13, 14])
        result = ema(prices, period=3)
        
        # EMA gives more weight to recent prices
        assert len(result) == 5
        assert result.iloc[-1] > 12.5  # Should be closer to recent values


# ============================================================================
# Test RSI (Relative Strength Index)
# ============================================================================

class TestRSI:
    """Test RSI indicator."""
    
    def test_rsi_calculation(self, sample_price_series):
        """Test RSI calculation with valid data."""
        result = rsi(sample_price_series, period=14)
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_price_series)
    
    def test_rsi_range(self, sample_price_series):
        """Test RSI values are between 0 and 100."""
        result = rsi(sample_price_series, period=14)
        
        # Remove NaN values
        valid_values = result.dropna()
        
        assert (valid_values >= 0).all()
        assert (valid_values <= 100).all()
    
    def test_rsi_trending_up(self, trending_up_series):
        """Test RSI in uptrend should be > 50."""
        result = rsi(trending_up_series, period=14)
        
        # In strong uptrend, RSI should be elevated
        assert result.iloc[-5:].mean() > 50
    
    def test_rsi_trending_down(self, trending_down_series):
        """Test RSI in downtrend should be < 50."""
        result = rsi(trending_down_series, period=14)
        
        # In strong downtrend, RSI should be depressed
        assert result.iloc[-5:].mean() < 50
    
    def test_rsi_overbought_oversold(self):
        """Test RSI identifies overbought/oversold conditions."""
        # Create series with sharp movements
        prices = pd.Series([100] * 10 + [110, 120, 130, 140, 150] + [150] * 10)
        result = rsi(prices, period=14)
        
        # After sharp rally, RSI should be high (overbought)
        assert result.iloc[-5:].mean() > 70


# ============================================================================
# Test MACD (Moving Average Convergence Divergence)
# ============================================================================

class TestMACD:
    """Test MACD indicator."""
    
    def test_macd_calculation(self, sample_price_series):
        """Test MACD calculation returns three series."""
        macd_line, signal_line, histogram = macd(sample_price_series)
        
        assert isinstance(macd_line, pd.Series)
        assert isinstance(signal_line, pd.Series)
        assert isinstance(histogram, pd.Series)
        assert len(macd_line) == len(sample_price_series)
    
    def test_macd_histogram_relationship(self, sample_price_series):
        """Test histogram equals MACD - Signal."""
        macd_line, signal_line, histogram = macd(sample_price_series)
        
        # Histogram should equal MACD - Signal
        expected_histogram = macd_line - signal_line
        pd.testing.assert_series_equal(histogram, expected_histogram)
    
    def test_macd_trending_up(self, trending_up_series):
        """Test MACD in uptrend."""
        macd_line, signal_line, histogram = macd(trending_up_series)
        
        # In uptrend, MACD should eventually be positive
        assert macd_line.iloc[-5:].mean() > 0
    
    def test_macd_trending_down(self, trending_down_series):
        """Test MACD in downtrend."""
        macd_line, signal_line, histogram = macd(trending_down_series)
        
        # In downtrend, MACD should eventually be negative
        assert macd_line.iloc[-5:].mean() < 0
    
    def test_macd_crossover(self):
        """Test MACD crossover detection."""
        # Create series with trend reversal
        prices = pd.Series(
            [100 - i for i in range(30)] +  # Downtrend
            [70 + i for i in range(30)]     # Uptrend
        )
        
        macd_line, signal_line, histogram = macd(prices)
        
        # Should have crossover somewhere in the middle
        # Histogram changes sign at crossover
        hist_signs = histogram.apply(lambda x: 1 if x > 0 else -1)
        sign_changes = (hist_signs.diff() != 0).sum()
        
        assert sign_changes > 0  # At least one crossover occurred


# ============================================================================
# Test Bollinger Bands
# ============================================================================

class TestBollingerBands:
    """Test Bollinger Bands indicator."""
    
    def test_bollinger_bands_calculation(self, sample_price_series):
        """Test Bollinger Bands calculation."""
        upper, middle, lower = bollinger_bands(sample_price_series, period=20, std_dev=2.0)
        
        assert isinstance(upper, pd.Series)
        assert isinstance(middle, pd.Series)
        assert isinstance(lower, pd.Series)
        assert len(upper) == len(sample_price_series)
    
    def test_bollinger_bands_relationship(self, sample_price_series):
        """Test upper > middle > lower."""
        upper, middle, lower = bollinger_bands(sample_price_series, period=20)
        
        # Remove NaN values
        valid_idx = ~upper.isna()
        
        assert (upper[valid_idx] >= middle[valid_idx]).all()
        assert (middle[valid_idx] >= lower[valid_idx]).all()
    
    def test_bollinger_bands_middle_is_sma(self, sample_price_series):
        """Test that middle band equals SMA."""
        upper, middle, lower = bollinger_bands(sample_price_series, period=20)
        expected_middle = sma(sample_price_series, period=20)
        
        pd.testing.assert_series_equal(middle, expected_middle)
    
    def test_bollinger_bands_width(self, sample_price_series):
        """Test Bollinger Bands width changes with volatility."""
        # Narrow bands (1 std dev)
        upper1, middle1, lower1 = bollinger_bands(sample_price_series, period=20, std_dev=1.0)
        
        # Wide bands (3 std dev)
        upper3, middle3, lower3 = bollinger_bands(sample_price_series, period=20, std_dev=3.0)
        
        # Wider bands should have greater distance
        width1 = (upper1 - lower1).iloc[-10:].mean()
        width3 = (upper3 - lower3).iloc[-10:].mean()
        
        assert width3 > width1
    
    def test_bollinger_bands_price_within_bands(self, sample_price_series):
        """Test that most prices fall within 2 std dev bands."""
        upper, middle, lower = bollinger_bands(sample_price_series, period=20, std_dev=2.0)
        
        # Remove initial NaN values
        valid_idx = ~upper.isna()
        prices = sample_price_series[valid_idx]
        upper_valid = upper[valid_idx]
        lower_valid = lower[valid_idx]
        
        # ~95% of prices should be within 2 std dev
        within_bands = ((prices >= lower_valid) & (prices <= upper_valid)).sum()
        total = len(prices)
        
        assert within_bands / total > 0.90  # At least 90%


# ============================================================================
# Test ATR (Average True Range)
# ============================================================================

class TestATR:
    """Test ATR indicator."""
    
    def test_atr_calculation(self, sample_ohlc_data):
        """Test ATR calculation."""
        result = atr(
            sample_ohlc_data['high'],
            sample_ohlc_data['low'],
            sample_ohlc_data['close'],
            period=14
        )
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlc_data)
    
    def test_atr_positive_values(self, sample_ohlc_data):
        """Test ATR values are always positive."""
        result = atr(
            sample_ohlc_data['high'],
            sample_ohlc_data['low'],
            sample_ohlc_data['close'],
            period=14
        )
        
        valid_values = result.dropna()
        assert (valid_values >= 0).all()
    
    def test_atr_measures_volatility(self):
        """Test ATR increases with volatility."""
        # Low volatility data
        low_vol_data = pd.DataFrame({
            'high': [101] * 30,
            'low': [99] * 30,
            'close': [100] * 30
        })
        
        # High volatility data
        high_vol_data = pd.DataFrame({
            'high': [110] * 30,
            'low': [90] * 30,
            'close': [100] * 30
        })
        
        atr_low = atr(low_vol_data['high'], low_vol_data['low'], low_vol_data['close'], 14)
        atr_high = atr(high_vol_data['high'], high_vol_data['low'], high_vol_data['close'], 14)
        
        assert atr_high.iloc[-1] > atr_low.iloc[-1]


# ============================================================================
# Test Stochastic Oscillator
# ============================================================================

class TestStochastic:
    """Test Stochastic Oscillator."""
    
    def test_stochastic_calculation(self, sample_ohlc_data):
        """Test Stochastic calculation."""
        k, d = stochastic(
            sample_ohlc_data['high'],
            sample_ohlc_data['low'],
            sample_ohlc_data['close'],
            period=14
        )
        
        assert isinstance(k, pd.Series)
        assert isinstance(d, pd.Series)
        assert len(k) == len(sample_ohlc_data)
    
    def test_stochastic_range(self, sample_ohlc_data):
        """Test Stochastic values are between 0 and 100."""
        k, d = stochastic(
            sample_ohlc_data['high'],
            sample_ohlc_data['low'],
            sample_ohlc_data['close'],
            period=14
        )
        
        k_valid = k.dropna()
        d_valid = d.dropna()
        
        assert (k_valid >= 0).all() and (k_valid <= 100).all()
        assert (d_valid >= 0).all() and (d_valid <= 100).all()


# ============================================================================
# Test ADX (Average Directional Index)
# ============================================================================

class TestADX:
    """Test ADX indicator."""
    
    def test_adx_calculation(self, sample_ohlc_data):
        """Test ADX calculation."""
        result = adx(
            sample_ohlc_data['high'],
            sample_ohlc_data['low'],
            sample_ohlc_data['close'],
            period=14
        )
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlc_data)
    
    def test_adx_range(self, sample_ohlc_data):
        """Test ADX values are between 0 and 100."""
        result = adx(
            sample_ohlc_data['high'],
            sample_ohlc_data['low'],
            sample_ohlc_data['close'],
            period=14
        )
        
        valid_values = result.dropna()
        
        assert (valid_values >= 0).all()
        assert (valid_values <= 100).all()


# ============================================================================
# Test OBV (On-Balance Volume)
# ============================================================================

class TestOBV:
    """Test OBV indicator."""
    
    def test_obv_calculation(self, sample_ohlc_data):
        """Test OBV calculation."""
        result = obv(sample_ohlc_data['close'], sample_ohlc_data['volume'])
        
        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_ohlc_data)
    
    def test_obv_trending_up(self):
        """Test OBV increases in uptrend with volume."""
        prices = pd.Series([100, 101, 102, 103, 104])
        volume = pd.Series([1000, 1000, 1000, 1000, 1000])
        
        result = obv(prices, volume)
        
        # OBV should be increasing
        assert result.iloc[-1] > result.iloc[0]
    
    def test_obv_trending_down(self):
        """Test OBV decreases in downtrend with volume."""
        prices = pd.Series([100, 99, 98, 97, 96])
        volume = pd.Series([1000, 1000, 1000, 1000, 1000])
        
        result = obv(prices, volume)
        
        # OBV should be decreasing
        assert result.iloc[-1] < result.iloc[0]


# ============================================================================
# Test Support/Resistance Levels
# ============================================================================

class TestSupportResistance:
    """Test support and resistance level calculation."""
    
    def test_support_resistance_calculation(self, sample_ohlc_data):
        """Test support/resistance calculation."""
        resistance, pivot, support = support_resistance_levels(
            sample_ohlc_data['high'],
            sample_ohlc_data['low'],
            sample_ohlc_data['close'],
            lookback=20
        )
        
        assert isinstance(resistance, float)
        assert isinstance(pivot, float)
        assert isinstance(support, float)
    
    def test_support_resistance_relationship(self, sample_ohlc_data):
        """Test resistance > pivot > support."""
        resistance, pivot, support = support_resistance_levels(
            sample_ohlc_data['high'],
            sample_ohlc_data['low'],
            sample_ohlc_data['close'],
            lookback=20
        )
        
        assert resistance >= pivot
        assert pivot >= support
    
    def test_support_resistance_values(self):
        """Test support/resistance with known values."""
        high = pd.Series([110] * 10)
        low = pd.Series([90] * 10)
        close = pd.Series([100] * 10)
        
        resistance, pivot, support = support_resistance_levels(high, low, close, lookback=10)
        
        # Pivot = (H + L + C) / 3 = (110 + 90 + 100) / 3 = 100
        assert abs(pivot - 100.0) < 0.01
        
        # Resistance = 2*P - L = 2*100 - 90 = 110
        assert abs(resistance - 110.0) < 0.01
        
        # Support = 2*P - H = 2*100 - 110 = 90
        assert abs(support - 90.0) < 0.01


# ============================================================================
# Integration Tests
# ============================================================================

class TestIndicatorIntegration:
    """Integration tests for using multiple indicators together."""
    
    def test_multiple_indicators_on_same_data(self, sample_ohlc_data):
        """Test using multiple indicators on same dataset."""
        close = sample_ohlc_data['close']
        high = sample_ohlc_data['high']
        low = sample_ohlc_data['low']
        volume = sample_ohlc_data['volume']
        
        # Calculate multiple indicators
        sma_20 = sma(close, 20)
        ema_20 = ema(close, 20)
        rsi_14 = rsi(close, 14)
        macd_line, signal_line, histogram = macd(close)
        upper, middle, lower = bollinger_bands(close, 20)
        atr_14 = atr(high, low, close, 14)
        obv_val = obv(close, volume)
        
        # All indicators should have same length as input
        assert len(sma_20) == len(sample_ohlc_data)
        assert len(ema_20) == len(sample_ohlc_data)
        assert len(rsi_14) == len(sample_ohlc_data)
        assert len(macd_line) == len(sample_ohlc_data)
        assert len(upper) == len(sample_ohlc_data)
        assert len(atr_14) == len(sample_ohlc_data)
        assert len(obv_val) == len(sample_ohlc_data)
    
    def test_indicator_combination_strategy(self, sample_ohlc_data):
        """Test combining indicators for trading signals."""
        close = sample_ohlc_data['close']
        
        # Calculate indicators
        rsi_val = rsi(close, 14)
        macd_line, signal_line, histogram = macd(close)
        
        # Find potential BUY signal: RSI < 30 and MACD bullish crossover
        last_rsi = rsi_val.iloc[-1]
        last_macd = macd_line.iloc[-1]
        last_signal = signal_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]
        
        bullish_crossover = (prev_macd < prev_signal) and (last_macd > last_signal)
        oversold = last_rsi < 30
        
        # Test passes if we can calculate conditions without errors
        assert isinstance(bullish_crossover, (bool, np.bool_))
        assert isinstance(oversold, (bool, np.bool_))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
