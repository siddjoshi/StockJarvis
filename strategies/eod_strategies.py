"""
Example EOD (End-of-Day) trading strategies.
These serve as templates - actual strategies should be backtested before use.
"""

from typing import Optional
import pandas as pd

from core.strategy_engine import Strategy, SignalOutput
from core.logger import get_logger
from data.models import OrderAction
from indicators.technical import sma, rsi, macd, bollinger_bands, support_resistance_levels

logger = get_logger(__name__)


class SMAGoldenCrossStrategy(Strategy):
    """
    Golden Cross / Death Cross strategy using 50-day and 200-day SMAs.
    
    BUY: When 50-SMA crosses above 200-SMA
    SELL: When 50-SMA crosses below 200-SMA
    """
    
    def __init__(self):
        super().__init__(
            name="SMA_GoldenCross",
            description="Golden/Death cross using 50 and 200 day SMAs",
            parameters={"fast_period": 50, "slow_period": 200}
        )
        self.fast_period = 50
        self.slow_period = 200
    
    def get_required_history(self) -> int:
        return self.slow_period + 10  # Extra buffer
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        # Calculate SMAs
        fast_sma = sma(data['close'], self.fast_period)
        slow_sma = sma(data['close'], self.slow_period)
        
        # Check for crossover in last 2 periods
        if len(fast_sma) < 2 or fast_sma.isna().any() or slow_sma.isna().any():
            return None
        
        current_fast = fast_sma.iloc[-1]
        current_slow = slow_sma.iloc[-1]
        prev_fast = fast_sma.iloc[-2]
        prev_slow = slow_sma.iloc[-2]
        
        current_price = data['close'].iloc[-1]
        
        # Golden Cross - BUY signal
        if prev_fast <= prev_slow and current_fast > current_slow:
            # Calculate support/resistance for stop loss and target
            resistance, pivot, support = support_resistance_levels(
                data['high'], data['low'], data['close']
            )
            
            stop_loss = current_price * 0.95  # 5% stop loss
            target = resistance
            
            return SignalOutput(
                action=OrderAction.BUY,
                symbol=symbol,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                confidence=0.7,
                reason=f"Golden Cross: 50-SMA ({current_fast:.2f}) crossed above 200-SMA ({current_slow:.2f})"
            )
        
        # Death Cross - SELL signal
        elif prev_fast >= prev_slow and current_fast < current_slow:
            resistance, pivot, support = support_resistance_levels(
                data['high'], data['low'], data['close']
            )
            
            stop_loss = current_price * 1.05  # 5% stop loss
            target = support
            
            return SignalOutput(
                action=OrderAction.SELL,
                symbol=symbol,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                confidence=0.7,
                reason=f"Death Cross: 50-SMA ({current_fast:.2f}) crossed below 200-SMA ({current_slow:.2f})"
            )
        
        return None


class RSIOversoldStrategy(Strategy):
    """
    RSI Oversold/Overbought strategy.
    
    BUY: When RSI crosses above 30 (oversold recovery)
    SELL: When RSI crosses below 70 (overbought correction)
    """
    
    def __init__(self):
        super().__init__(
            name="RSI_OversoldOverbought",
            description="RSI oversold (<30) and overbought (>70) reversal",
            parameters={"rsi_period": 14, "oversold": 30, "overbought": 70}
        )
        self.rsi_period = 14
        self.oversold = 30
        self.overbought = 70
    
    def get_required_history(self) -> int:
        return self.rsi_period + 10
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        # Calculate RSI
        rsi_values = rsi(data['close'], self.rsi_period)
        
        if len(rsi_values) < 2 or rsi_values.isna().any():
            return None
        
        current_rsi = rsi_values.iloc[-1]
        prev_rsi = rsi_values.iloc[-2]
        current_price = data['close'].iloc[-1]
        
        # BUY: RSI crosses above 30 (oversold recovery)
        if prev_rsi <= self.oversold and current_rsi > self.oversold:
            atr_val = data['high'].tail(14).max() - data['low'].tail(14).min()
            stop_loss = current_price - (atr_val * 1.5)
            target = current_price + (atr_val * 3)  # 1:2 risk:reward
            
            return SignalOutput(
                action=OrderAction.BUY,
                symbol=symbol,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                confidence=0.65,
                reason=f"RSI oversold recovery: RSI {current_rsi:.1f} crossed above {self.oversold}"
            )
        
        # SELL: RSI crosses below 70 (overbought correction)
        elif prev_rsi >= self.overbought and current_rsi < self.overbought:
            atr_val = data['high'].tail(14).max() - data['low'].tail(14).min()
            stop_loss = current_price + (atr_val * 1.5)
            target = current_price - (atr_val * 3)
            
            return SignalOutput(
                action=OrderAction.SELL,
                symbol=symbol,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                confidence=0.65,
                reason=f"RSI overbought correction: RSI {current_rsi:.1f} crossed below {self.overbought}"
            )
        
        return None


class MACDCrossoverStrategy(Strategy):
    """
    MACD crossover strategy.
    
    BUY: MACD line crosses above signal line
    SELL: MACD line crosses below signal line
    """
    
    def __init__(self):
        super().__init__(
            name="MACD_Crossover",
            description="MACD line crossing signal line",
            parameters={"fast": 12, "slow": 26, "signal": 9}
        )
    
    def get_required_history(self) -> int:
        return 50  # Need enough for MACD calculation
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        # Calculate MACD
        macd_line, signal_line, histogram = macd(data['close'])
        
        if len(macd_line) < 2 or macd_line.isna().any() or signal_line.isna().any():
            return None
        
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_signal = signal_line.iloc[-2]
        
        current_price = data['close'].iloc[-1]
        
        # BUY: MACD crosses above signal
        if prev_macd <= prev_signal and current_macd > current_signal and current_macd < 0:
            # Stronger signal when MACD is negative (trend reversal)
            atr_val = data['high'].tail(14).max() - data['low'].tail(14).min()
            stop_loss = current_price - (atr_val * 1.5)
            target = current_price + (atr_val * 3)
            
            return SignalOutput(
                action=OrderAction.BUY,
                symbol=symbol,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                confidence=0.75,
                reason=f"MACD bullish crossover: MACD {current_macd:.2f} > Signal {current_signal:.2f}"
            )
        
        # SELL: MACD crosses below signal
        elif prev_macd >= prev_signal and current_macd < current_signal and current_macd > 0:
            atr_val = data['high'].tail(14).max() - data['low'].tail(14).min()
            stop_loss = current_price + (atr_val * 1.5)
            target = current_price - (atr_val * 3)
            
            return SignalOutput(
                action=OrderAction.SELL,
                symbol=symbol,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                confidence=0.75,
                reason=f"MACD bearish crossover: MACD {current_macd:.2f} < Signal {current_signal:.2f}"
            )
        
        return None


class BollingerBreakoutStrategy(Strategy):
    """
    Bollinger Bands breakout strategy.
    
    BUY: Price breaks above upper band with volume confirmation
    SELL: Price breaks below lower band with volume confirmation
    """
    
    def __init__(self):
        super().__init__(
            name="Bollinger_Breakout",
            description="Price breakout above/below Bollinger Bands",
            parameters={"period": 20, "std_dev": 2.0}
        )
        self.period = 20
        self.std_dev = 2.0
    
    def get_required_history(self) -> int:
        return self.period + 10
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        # Calculate Bollinger Bands
        upper, middle, lower = bollinger_bands(data['close'], self.period, self.std_dev)
        
        if upper.isna().any() or lower.isna().any():
            return None
        
        current_price = data['close'].iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]
        current_middle = middle.iloc[-1]
        
        # Volume confirmation
        avg_volume = data['volume'].tail(20).mean()
        current_volume = data['volume'].iloc[-1]
        volume_surge = current_volume > avg_volume * 1.5
        
        # BUY: Price breaks above upper band with volume
        if current_price > current_upper and volume_surge:
            stop_loss = current_middle
            target = current_price + (current_price - current_middle)
            
            return SignalOutput(
                action=OrderAction.BUY,
                symbol=symbol,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                confidence=0.70,
                reason=f"Bollinger breakout: Price {current_price:.2f} > Upper band {current_upper:.2f} with volume surge"
            )
        
        # SELL: Price breaks below lower band with volume
        elif current_price < current_lower and volume_surge:
            stop_loss = current_middle
            target = current_price - (current_middle - current_price)
            
            return SignalOutput(
                action=OrderAction.SELL,
                symbol=symbol,
                price=current_price,
                stop_loss=stop_loss,
                target=target,
                confidence=0.70,
                reason=f"Bollinger breakdown: Price {current_price:.2f} < Lower band {current_lower:.2f} with volume surge"
            )
        
        return None
