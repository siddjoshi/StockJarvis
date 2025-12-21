# tests/unit/test_strategy_engine.py
"""
Unit tests for Strategy Engine and Strategy Registry.
Tests strategy registration, execution, signal generation, and validation.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional

from core.strategy_engine import (
    Strategy,
    StrategyRegistry,
    SignalOutput,
    registry as global_registry
)
from data.models import OrderAction
from config.settings import settings


# ============================================================================
# Mock Strategy Implementations
# ============================================================================

class MockSuccessStrategy(Strategy):
    """Mock strategy that always generates a BUY signal."""
    
    def __init__(self):
        super().__init__(
            name="MockSuccess",
            description="Always generates BUY signals",
            parameters={"test_param": 100}
        )
        self.is_validated = True
        self.backtest_accuracy = 0.75
    
    def get_required_history(self) -> int:
        return 10
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        """Generate a BUY signal."""
        current_price = data['close'].iloc[-1]
        return SignalOutput(
            action=OrderAction.BUY,
            symbol=symbol,
            price=current_price,
            stop_loss=current_price * 0.95,
            target=current_price * 1.10,
            confidence=0.85,
            reason="Mock BUY signal for testing"
        )


class MockNoSignalStrategy(Strategy):
    """Mock strategy that never generates signals."""
    
    def __init__(self):
        super().__init__(
            name="MockNoSignal",
            description="Never generates signals"
        )
    
    def get_required_history(self) -> int:
        return 5
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        """Return None (no signal)."""
        return None


class MockInvalidStrategy(Strategy):
    """Mock strategy that generates invalid signals."""
    
    def __init__(self):
        super().__init__(name="MockInvalid")
    
    def get_required_history(self) -> int:
        return 10
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        """Generate an invalid signal (bad R:R ratio)."""
        current_price = data['close'].iloc[-1]
        return SignalOutput(
            action=OrderAction.BUY,
            symbol=symbol,
            price=current_price,
            stop_loss=current_price * 0.99,  # Only 1% stop loss
            target=current_price * 1.005,    # Only 0.5% target - bad R:R
            confidence=0.6,
            reason="Invalid signal with poor R:R ratio"
        )


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_price_data() -> pd.DataFrame:
    """
    Create sample OHLCV price data for testing.
    
    Returns:
        DataFrame: 30 days of price data
    """
    dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
    data = pd.DataFrame({
        'open': [100 + i for i in range(30)],
        'high': [105 + i for i in range(30)],
        'low': [95 + i for i in range(30)],
        'close': [102 + i for i in range(30)],
        'volume': [1000000 + (i * 10000) for i in range(30)]
    }, index=dates)
    return data


@pytest.fixture
def insufficient_price_data() -> pd.DataFrame:
    """
    Create insufficient price data (only 5 bars).
    
    Returns:
        DataFrame: 5 days of price data
    """
    dates = pd.date_range(end=datetime.now(), periods=5, freq='D')
    data = pd.DataFrame({
        'open': [100, 101, 102, 103, 104],
        'high': [105, 106, 107, 108, 109],
        'low': [95, 96, 97, 98, 99],
        'close': [102, 103, 104, 105, 106],
        'volume': [1000000, 1100000, 1200000, 1300000, 1400000]
    }, index=dates)
    return data


@pytest.fixture
def strategy_registry() -> StrategyRegistry:
    """
    Create a fresh strategy registry for each test.
    
    Returns:
        StrategyRegistry: Empty registry
    """
    return StrategyRegistry()


@pytest.fixture
def mock_strategy() -> MockSuccessStrategy:
    """
    Create a mock strategy instance.
    
    Returns:
        MockSuccessStrategy: Mock strategy
    """
    return MockSuccessStrategy()


# ============================================================================
# Test SignalOutput Class
# ============================================================================

class TestSignalOutput:
    """Test SignalOutput dataclass and its methods."""
    
    def test_signal_creation(self):
        """Test creating a valid signal."""
        signal = SignalOutput(
            action=OrderAction.BUY,
            symbol="RELIANCE",
            price=2500.0,
            stop_loss=2400.0,
            target=2700.0,
            confidence=0.8,
            reason="Test signal"
        )
        
        assert signal.action == OrderAction.BUY
        assert signal.symbol == "RELIANCE"
        assert signal.price == 2500.0
        assert signal.stop_loss == 2400.0
        assert signal.target == 2700.0
        assert signal.confidence == 0.8
        assert signal.reason == "Test signal"
        assert signal.timestamp is not None
    
    def test_risk_reward_ratio_buy(self):
        """Test R:R ratio calculation for BUY signal."""
        signal = SignalOutput(
            action=OrderAction.BUY,
            symbol="TEST",
            price=100.0,
            stop_loss=95.0,   # Risk: 5
            target=110.0,     # Reward: 10
            confidence=0.8,
            reason="Test"
        )
        
        # R:R = 10/5 = 2.0
        assert signal.risk_reward_ratio == 2.0
    
    def test_risk_reward_ratio_sell(self):
        """Test R:R ratio calculation for SELL signal."""
        signal = SignalOutput(
            action=OrderAction.SELL,
            symbol="TEST",
            price=100.0,
            stop_loss=105.0,  # Risk: 5
            target=90.0,      # Reward: 10
            confidence=0.8,
            reason="Test"
        )
        
        # R:R = 10/5 = 2.0
        assert signal.risk_reward_ratio == 2.0
    
    def test_signal_validation_valid(self):
        """Test validation of a valid signal."""
        signal = SignalOutput(
            action=OrderAction.BUY,
            symbol="TEST",
            price=100.0,
            stop_loss=95.0,
            target=110.0,
            confidence=0.75,
            reason="Valid signal"
        )
        
        assert signal.is_valid() is True
    
    def test_signal_validation_bad_risk_reward(self):
        """Test validation fails for bad R:R ratio."""
        signal = SignalOutput(
            action=OrderAction.BUY,
            symbol="TEST",
            price=100.0,
            stop_loss=98.0,   # Risk: 2
            target=101.0,     # Reward: 1, R:R = 0.5
            confidence=0.8,
            reason="Bad R:R"
        )
        
        assert signal.is_valid() is False
    
    def test_signal_validation_low_confidence(self):
        """Test validation fails for low confidence."""
        signal = SignalOutput(
            action=OrderAction.BUY,
            symbol="TEST",
            price=100.0,
            stop_loss=90.0,
            target=120.0,
            confidence=0.3,  # Too low
            reason="Low confidence"
        )
        
        assert signal.is_valid() is False
    
    def test_signal_validation_invalid_price_levels_buy(self):
        """Test validation fails for invalid BUY price levels."""
        # Stop loss above entry price
        signal = SignalOutput(
            action=OrderAction.BUY,
            symbol="TEST",
            price=100.0,
            stop_loss=105.0,  # Invalid: stop loss > price
            target=110.0,
            confidence=0.8,
            reason="Invalid levels"
        )
        
        assert signal.is_valid() is False
    
    def test_signal_validation_invalid_price_levels_sell(self):
        """Test validation fails for invalid SELL price levels."""
        # Target above entry price
        signal = SignalOutput(
            action=OrderAction.SELL,
            symbol="TEST",
            price=100.0,
            stop_loss=95.0,
            target=105.0,  # Invalid: target > price for SELL
            confidence=0.8,
            reason="Invalid levels"
        )
        
        assert signal.is_valid() is False


# ============================================================================
# Test Strategy Base Class
# ============================================================================

class TestStrategy:
    """Test Strategy abstract base class."""
    
    def test_strategy_initialization(self, mock_strategy):
        """Test strategy initialization."""
        assert mock_strategy.name == "MockSuccess"
        assert mock_strategy.description == "Always generates BUY signals"
        assert mock_strategy.parameters == {"test_param": 100}
        assert mock_strategy.is_validated is True
        assert mock_strategy.backtest_accuracy == 0.75
    
    def test_strategy_validate_data_success(self, mock_strategy, sample_price_data):
        """Test data validation with valid data."""
        assert mock_strategy.validate_data(sample_price_data) is True
    
    def test_strategy_validate_data_missing_columns(self, mock_strategy):
        """Test data validation fails with missing columns."""
        invalid_data = pd.DataFrame({
            'open': [100, 101, 102],
            'close': [102, 103, 104]
            # Missing: high, low, volume
        })
        
        assert mock_strategy.validate_data(invalid_data) is False
    
    def test_strategy_validate_data_insufficient_history(self, mock_strategy, insufficient_price_data):
        """Test data validation fails with insufficient history."""
        # MockSuccessStrategy requires 10 bars, but only 5 provided
        assert mock_strategy.validate_data(insufficient_price_data) is False
    
    def test_strategy_validate_data_with_nan(self, mock_strategy):
        """Test data validation fails with NaN values."""
        data_with_nan = pd.DataFrame({
            'open': [100, 101, None, 103],
            'high': [105, 106, 107, 108],
            'low': [95, 96, 97, 98],
            'close': [102, 103, 104, 105],
            'volume': [1000000, 1100000, 1200000, 1300000]
        })
        
        assert mock_strategy.validate_data(data_with_nan) is False
    
    def test_strategy_is_tradeable_success(self, mock_strategy):
        """Test tradeable check with validated strategy."""
        mock_strategy.is_validated = True
        mock_strategy.backtest_accuracy = 0.70  # Above minimum
        
        assert mock_strategy.is_tradeable() is True
    
    def test_strategy_is_tradeable_not_validated(self, mock_strategy):
        """Test tradeable check fails if not validated."""
        mock_strategy.is_validated = False
        mock_strategy.backtest_accuracy = 0.70
        
        assert mock_strategy.is_tradeable() is False
    
    def test_strategy_is_tradeable_low_accuracy(self, mock_strategy):
        """Test tradeable check fails with low accuracy."""
        mock_strategy.is_validated = True
        mock_strategy.backtest_accuracy = 0.40  # Below minimum
        
        assert mock_strategy.is_tradeable() is False
    
    def test_strategy_is_tradeable_no_backtest(self, mock_strategy):
        """Test tradeable check fails without backtest results."""
        mock_strategy.is_validated = True
        mock_strategy.backtest_accuracy = None
        
        assert mock_strategy.is_tradeable() is False
    
    def test_strategy_str_representation(self, mock_strategy):
        """Test string representation."""
        assert str(mock_strategy) == "Strategy(MockSuccess)"
    
    def test_strategy_repr_representation(self, mock_strategy):
        """Test detailed representation."""
        repr_str = repr(mock_strategy)
        assert "MockSuccess" in repr_str
        assert "validated=True" in repr_str
        assert "accuracy=0.75" in repr_str


# ============================================================================
# Test Strategy Registry
# ============================================================================

class TestStrategyRegistry:
    """Test StrategyRegistry class."""
    
    def test_registry_initialization(self, strategy_registry):
        """Test registry initializes empty."""
        assert len(strategy_registry.list_names()) == 0
        assert strategy_registry.get_all() == []
    
    def test_register_strategy(self, strategy_registry, mock_strategy):
        """Test registering a strategy."""
        strategy_registry.register(mock_strategy)
        
        assert "MockSuccess" in strategy_registry.list_names()
        assert strategy_registry.get("MockSuccess") == mock_strategy
    
    def test_register_duplicate_strategy(self, strategy_registry, mock_strategy):
        """Test registering duplicate strategy (should overwrite)."""
        strategy_registry.register(mock_strategy)
        
        # Register another strategy with same name
        new_strategy = MockSuccessStrategy()
        strategy_registry.register(new_strategy)
        
        # Should have only one strategy
        assert len(strategy_registry.list_names()) == 1
        assert strategy_registry.get("MockSuccess") == new_strategy
    
    def test_unregister_strategy(self, strategy_registry, mock_strategy):
        """Test unregistering a strategy."""
        strategy_registry.register(mock_strategy)
        assert "MockSuccess" in strategy_registry.list_names()
        
        strategy_registry.unregister("MockSuccess")
        assert "MockSuccess" not in strategy_registry.list_names()
        assert strategy_registry.get("MockSuccess") is None
    
    def test_get_strategy_exists(self, strategy_registry, mock_strategy):
        """Test getting an existing strategy."""
        strategy_registry.register(mock_strategy)
        
        retrieved = strategy_registry.get("MockSuccess")
        assert retrieved == mock_strategy
    
    def test_get_strategy_not_exists(self, strategy_registry):
        """Test getting a non-existent strategy."""
        assert strategy_registry.get("NonExistent") is None
    
    def test_get_all_strategies(self, strategy_registry):
        """Test getting all registered strategies."""
        strategy1 = MockSuccessStrategy()
        strategy2 = MockNoSignalStrategy()
        
        strategy_registry.register(strategy1)
        strategy_registry.register(strategy2)
        
        all_strategies = strategy_registry.get_all()
        assert len(all_strategies) == 2
        assert strategy1 in all_strategies
        assert strategy2 in all_strategies
    
    def test_get_tradeable_strategies(self, strategy_registry):
        """Test getting only tradeable strategies."""
        # Tradeable strategy
        strategy1 = MockSuccessStrategy()
        strategy1.is_validated = True
        strategy1.backtest_accuracy = 0.70
        
        # Non-tradeable strategy (not validated)
        strategy2 = MockNoSignalStrategy()
        strategy2.is_validated = False
        
        strategy_registry.register(strategy1)
        strategy_registry.register(strategy2)
        
        tradeable = strategy_registry.get_tradeable()
        assert len(tradeable) == 1
        assert strategy1 in tradeable
        assert strategy2 not in tradeable
    
    def test_list_strategy_names(self, strategy_registry):
        """Test listing strategy names."""
        strategy1 = MockSuccessStrategy()
        strategy2 = MockNoSignalStrategy()
        
        strategy_registry.register(strategy1)
        strategy_registry.register(strategy2)
        
        names = strategy_registry.list_names()
        assert len(names) == 2
        assert "MockSuccess" in names
        assert "MockNoSignal" in names


# ============================================================================
# Test Strategy Execution
# ============================================================================

class TestStrategyExecution:
    """Test strategy signal generation."""
    
    def test_generate_signal_success(self, mock_strategy, sample_price_data):
        """Test successful signal generation."""
        signal = mock_strategy.generate_signal("RELIANCE", sample_price_data)
        
        assert signal is not None
        assert signal.action == OrderAction.BUY
        assert signal.symbol == "RELIANCE"
        assert signal.confidence == 0.85
        assert signal.reason == "Mock BUY signal for testing"
    
    def test_generate_signal_no_signal(self, sample_price_data):
        """Test strategy that generates no signal."""
        strategy = MockNoSignalStrategy()
        signal = strategy.generate_signal("RELIANCE", sample_price_data)
        
        assert signal is None
    
    def test_generate_signal_invalid(self, sample_price_data):
        """Test strategy that generates invalid signal."""
        strategy = MockInvalidStrategy()
        signal = strategy.generate_signal("RELIANCE", sample_price_data)
        
        assert signal is not None
        assert signal.is_valid() is False  # Signal validation should fail
    
    def test_signal_generation_with_insufficient_data(self, mock_strategy, insufficient_price_data):
        """Test signal generation fails gracefully with insufficient data."""
        # Validate data should fail first
        assert mock_strategy.validate_data(insufficient_price_data) is False
        
        # Even if we call generate_signal, it should handle gracefully
        # (In production, you'd validate before calling generate_signal)
        signal = mock_strategy.generate_signal("RELIANCE", insufficient_price_data)
        # Signal might be None or invalid depending on implementation
        assert signal is None or not signal.is_valid()


# ============================================================================
# Test Invalid Strategy
# ============================================================================

class TestInvalidStrategy:
    """Test handling of invalid strategies."""
    
    def test_invalid_strategy_signal(self, sample_price_data):
        """Test invalid strategy generates invalid signal."""
        strategy = MockInvalidStrategy()
        signal = strategy.generate_signal("TEST", sample_price_data)
        
        assert signal is not None
        assert signal.is_valid() is False  # Poor R:R ratio
    
    def test_strategy_without_validation(self):
        """Test strategy that hasn't been validated."""
        strategy = MockNoSignalStrategy()
        strategy.is_validated = False
        strategy.backtest_accuracy = None
        
        assert strategy.is_tradeable() is False


# ============================================================================
# Integration Tests
# ============================================================================

class TestStrategyIntegration:
    """Integration tests for complete strategy workflow."""
    
    def test_complete_strategy_workflow(self, strategy_registry, mock_strategy, sample_price_data):
        """Test complete workflow: register -> validate -> generate signal."""
        # 1. Register strategy
        strategy_registry.register(mock_strategy)
        assert "MockSuccess" in strategy_registry.list_names()
        
        # 2. Validate data
        assert mock_strategy.validate_data(sample_price_data) is True
        
        # 3. Generate signal
        signal = mock_strategy.generate_signal("RELIANCE", sample_price_data)
        assert signal is not None
        
        # 4. Validate signal
        assert signal.is_valid() is True
        
        # 5. Check if strategy is tradeable
        assert mock_strategy.is_tradeable() is True
    
    def test_multiple_strategies_execution(self, strategy_registry, sample_price_data):
        """Test executing multiple strategies."""
        # Register multiple strategies
        strategy1 = MockSuccessStrategy()
        strategy2 = MockNoSignalStrategy()
        
        strategy_registry.register(strategy1)
        strategy_registry.register(strategy2)
        
        # Execute all strategies
        signals = []
        for strategy in strategy_registry.get_all():
            if strategy.validate_data(sample_price_data):
                signal = strategy.generate_signal("RELIANCE", sample_price_data)
                if signal:
                    signals.append(signal)
        
        # Should have one signal from MockSuccessStrategy
        assert len(signals) == 1
        assert signals[0].action == OrderAction.BUY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
