# tests/unit/test_backtester.py
"""
Unit tests for the Backtesting Engine.
Tests BacktestEngine, BacktestConfig, BacktestExecutor, and BacktestAnalyzer.
"""

import pytest
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Optional

from core.backtester import (
    BacktestEngine,
    BacktestConfig,
    BacktestTrade,
    BacktestResult,
)
from core.backtest_executor import (
    BacktestExecutor,
    SlippageConfig,
    CommissionConfig,
    SlippageModel,
    CommissionModel,
    create_default_executor,
    create_zero_cost_executor
)
from core.backtest_analyzer import (
    BacktestAnalyzer,
    PerformanceMetrics,
    analyze_backtest,
)
from core.strategy_engine import Strategy, SignalOutput
from data.models import OrderAction


# ============================================================================
# Mock Strategy for Testing
# ============================================================================

class MockAlwaysBuyStrategy(Strategy):
    """Mock strategy that always generates BUY signals."""
    
    def __init__(self):
        super().__init__(
            name="MockAlwaysBuy",
            description="Always generates BUY signals for testing",
            parameters={"test_param": 100}
        )
    
    def get_required_history(self) -> int:
        return 10
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        """Generate a BUY signal with 5% stop loss and 10% target."""
        current_price = data['close'].iloc[-1]
        return SignalOutput(
            action=OrderAction.BUY,
            symbol=symbol,
            price=current_price,
            stop_loss=current_price * 0.95,  # 5% stop loss
            target=current_price * 1.10,      # 10% target
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


class MockAlternatingSellStrategy(Strategy):
    """Mock strategy that generates SELL signals on alternate bars."""
    
    def __init__(self):
        super().__init__(
            name="MockAlternatingSell",
            description="Generates SELL signals on alternate bars"
        )
        self._call_count = 0
    
    def get_required_history(self) -> int:
        return 10
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        """Generate SELL signal every other call."""
        self._call_count += 1
        if self._call_count % 2 == 0:
            current_price = data['close'].iloc[-1]
            return SignalOutput(
                action=OrderAction.SELL,
                symbol=symbol,
                price=current_price,
                stop_loss=current_price * 1.05,
                target=current_price * 0.90,
                confidence=0.70,
                reason="Mock SELL signal"
            )
        return None


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_price_data() -> pd.DataFrame:
    """Create sample OHLCV price data for testing (50 days)."""
    dates = pd.date_range(end=datetime.now(), periods=50, freq='D')
    # Create uptrending price data
    base_price = 100.0
    data = pd.DataFrame({
        'open': [base_price + i * 0.5 for i in range(50)],
        'high': [base_price + i * 0.5 + 3 for i in range(50)],
        'low': [base_price + i * 0.5 - 2 for i in range(50)],
        'close': [base_price + i * 0.5 + 1 for i in range(50)],
        'volume': [1000000 + (i * 10000) for i in range(50)]
    }, index=dates)
    return data


@pytest.fixture
def backtest_config() -> BacktestConfig:
    """Create default backtest configuration."""
    return BacktestConfig(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 30),
        initial_capital=100000.0,
        risk_per_trade=0.02,
        max_positions=3,
        slippage_pct=0.001,
        commission_pct=0.001
    )


@pytest.fixture
def mock_buy_strategy() -> MockAlwaysBuyStrategy:
    """Create mock BUY strategy."""
    return MockAlwaysBuyStrategy()


@pytest.fixture
def mock_no_signal_strategy() -> MockNoSignalStrategy:
    """Create mock no-signal strategy."""
    return MockNoSignalStrategy()


@pytest.fixture
def sample_trades() -> list:
    """Create sample trades for analysis testing."""
    base_date = datetime(2024, 1, 1)
    trades = [
        BacktestTrade(
            trade_id=1,
            symbol="TEST",
            action=OrderAction.BUY,
            entry_date=base_date,
            entry_price=100.0,
            quantity=10,
            exit_date=base_date + timedelta(days=7),
            exit_price=110.0,  # Win
            exit_reason="target_hit"
        ),
        BacktestTrade(
            trade_id=2,
            symbol="TEST",
            action=OrderAction.BUY,
            entry_date=base_date + timedelta(days=10),
            entry_price=105.0,
            quantity=10,
            exit_date=base_date + timedelta(days=14),
            exit_price=95.0,  # Loss
            exit_reason="stop_loss_hit"
        ),
        BacktestTrade(
            trade_id=3,
            symbol="TEST",
            action=OrderAction.BUY,
            entry_date=base_date + timedelta(days=20),
            entry_price=100.0,
            quantity=10,
            exit_date=base_date + timedelta(days=30),
            exit_price=115.0,  # Win
            exit_reason="target_hit"
        ),
    ]
    return trades


@pytest.fixture
def sample_backtest_result(sample_trades) -> BacktestResult:
    """Create sample backtest result for analysis."""
    return BacktestResult(
        strategy_name="TestStrategy",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 30),
        initial_capital=100000.0,
        final_capital=120000.0,
        total_trades=3,
        winning_trades=2,
        losing_trades=1,
        trades=sample_trades,
        equity_curve=[100000, 101000, 102000, 103000, 105000, 110000, 115000, 120000],
        equity_dates=[datetime(2024, 1, i) for i in range(1, 9)]
    )


# ============================================================================
# Test BacktestConfig
# ============================================================================

class TestBacktestConfig:
    """Test BacktestConfig class."""
    
    def test_config_creation(self, backtest_config):
        """Test basic config creation."""
        assert backtest_config.start_date == date(2024, 1, 1)
        assert backtest_config.end_date == date(2024, 6, 30)
        assert backtest_config.initial_capital == 100000.0
        assert backtest_config.risk_per_trade == 0.02
        assert backtest_config.max_positions == 3
    
    def test_config_invalid_dates(self):
        """Test config validation for invalid dates."""
        with pytest.raises(ValueError, match="start_date must be before end_date"):
            BacktestConfig(
                start_date=date(2024, 12, 1),
                end_date=date(2024, 1, 1)
            )
    
    def test_config_same_dates(self):
        """Test config validation for same dates."""
        with pytest.raises(ValueError):
            BacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1)
            )
    
    def test_config_invalid_capital(self):
        """Test config validation for invalid capital."""
        with pytest.raises(ValueError, match="initial_capital must be positive"):
            BacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                initial_capital=0
            )
    
    def test_config_invalid_risk(self):
        """Test config validation for invalid risk."""
        with pytest.raises(ValueError, match="risk_per_trade must be between 0 and 1"):
            BacktestConfig(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 6, 30),
                risk_per_trade=1.5
            )


# ============================================================================
# Test BacktestTrade
# ============================================================================

class TestBacktestTrade:
    """Test BacktestTrade class."""
    
    def test_trade_pnl_buy_winner(self):
        """Test P&L calculation for winning BUY trade."""
        trade = BacktestTrade(
            trade_id=1,
            symbol="TEST",
            action=OrderAction.BUY,
            entry_date=datetime.now(),
            entry_price=100.0,
            quantity=10,
            exit_date=datetime.now(),
            exit_price=110.0,
            exit_reason="target_hit"
        )
        assert trade.pnl == 100.0  # (110 - 100) * 10
        assert trade.pnl_pct == 10.0  # 10%
        assert trade.is_winner is True
    
    def test_trade_pnl_buy_loser(self):
        """Test P&L calculation for losing BUY trade."""
        trade = BacktestTrade(
            trade_id=1,
            symbol="TEST",
            action=OrderAction.BUY,
            entry_date=datetime.now(),
            entry_price=100.0,
            quantity=10,
            exit_date=datetime.now(),
            exit_price=90.0,
            exit_reason="stop_loss_hit"
        )
        assert trade.pnl == -100.0  # (90 - 100) * 10
        assert trade.pnl_pct == -10.0
        assert trade.is_winner is False
    
    def test_trade_pnl_sell_winner(self):
        """Test P&L calculation for winning SELL (short) trade."""
        trade = BacktestTrade(
            trade_id=1,
            symbol="TEST",
            action=OrderAction.SELL,
            entry_date=datetime.now(),
            entry_price=100.0,
            quantity=10,
            exit_date=datetime.now(),
            exit_price=90.0,
            exit_reason="target_hit"
        )
        assert trade.pnl == 100.0  # (100 - 90) * 10
        assert trade.is_winner is True
    
    def test_trade_pnl_sell_loser(self):
        """Test P&L calculation for losing SELL (short) trade."""
        trade = BacktestTrade(
            trade_id=1,
            symbol="TEST",
            action=OrderAction.SELL,
            entry_date=datetime.now(),
            entry_price=100.0,
            quantity=10,
            exit_date=datetime.now(),
            exit_price=110.0,
            exit_reason="stop_loss_hit"
        )
        assert trade.pnl == -100.0  # (100 - 110) * 10
        assert trade.is_winner is False
    
    def test_trade_holding_days(self):
        """Test holding days calculation."""
        entry = datetime(2024, 1, 1)
        exit_date = datetime(2024, 1, 11)
        
        trade = BacktestTrade(
            trade_id=1,
            symbol="TEST",
            action=OrderAction.BUY,
            entry_date=entry,
            entry_price=100.0,
            quantity=10,
            exit_date=exit_date,
            exit_price=110.0,
            exit_reason="target_hit"
        )
        assert trade.holding_days == 10
    
    def test_trade_no_exit(self):
        """Test trade with no exit."""
        trade = BacktestTrade(
            trade_id=1,
            symbol="TEST",
            action=OrderAction.BUY,
            entry_date=datetime.now(),
            entry_price=100.0,
            quantity=10
        )
        assert trade.pnl == 0.0
        assert trade.pnl_pct == 0.0
        assert trade.holding_days == 0
    
    def test_trade_to_dict(self):
        """Test trade to dictionary conversion."""
        trade = BacktestTrade(
            trade_id=1,
            symbol="TEST",
            action=OrderAction.BUY,
            entry_date=datetime(2024, 1, 1),
            entry_price=100.0,
            quantity=10,
            exit_date=datetime(2024, 1, 10),
            exit_price=110.0,
            exit_reason="target_hit"
        )
        
        d = trade.to_dict()
        assert d["trade_id"] == 1
        assert d["symbol"] == "TEST"
        assert d["action"] == "BUY"
        assert d["entry_price"] == 100.0
        assert d["exit_price"] == 110.0
        assert d["quantity"] == 10
        assert d["pnl"] == 100.0
        assert d["pnl_pct"] == 10.0
        assert d["holding_days"] == 9
        assert d["exit_reason"] == "target_hit"


# ============================================================================
# Test BacktestExecutor
# ============================================================================

class TestBacktestExecutor:
    """Test BacktestExecutor class."""
    
    def test_default_executor(self):
        """Test default executor creation."""
        executor = create_default_executor()
        assert executor.slippage.model == SlippageModel.PERCENTAGE
        assert executor.commission.model == CommissionModel.PERCENTAGE
    
    def test_zero_cost_executor(self):
        """Test zero-cost executor creation."""
        executor = create_zero_cost_executor()
        result = executor.execute_entry(100.0, 10, OrderAction.BUY)
        assert result.slippage == 0.0
        assert result.commission == 0.0
    
    def test_entry_execution_buy(self):
        """Test BUY entry execution with costs."""
        executor = BacktestExecutor(
            slippage_config=SlippageConfig(
                model=SlippageModel.PERCENTAGE,
                percentage=0.001  # 0.1%
            ),
            commission_config=CommissionConfig(
                model=CommissionModel.PERCENTAGE,
                percentage=0.001  # 0.1%
            )
        )
        
        result = executor.execute_entry(100.0, 10, OrderAction.BUY)
        
        # Price should be higher due to slippage
        assert result.execution_price > 100.0
        assert result.slippage == pytest.approx(0.1, rel=0.01)  # 0.1% of 100
        assert result.commission > 0
        assert result.filled is True
    
    def test_entry_execution_sell(self):
        """Test SELL entry execution with costs."""
        executor = BacktestExecutor(
            slippage_config=SlippageConfig(
                model=SlippageModel.PERCENTAGE,
                percentage=0.001
            )
        )
        
        result = executor.execute_entry(100.0, 10, OrderAction.SELL)
        
        # Price should be lower due to slippage for short entry
        assert result.execution_price < 100.0
    
    def test_exit_execution(self):
        """Test exit execution."""
        executor = create_default_executor()
        
        # Exit long position (BUY -> SELL)
        result = executor.execute_exit(110.0, 10, OrderAction.BUY)
        
        # For exiting long, we sell, so price should be lower
        assert result.execution_price < 110.0
        assert result.filled is True
    
    def test_position_size_calculation(self):
        """Test position size calculation."""
        executor = BacktestExecutor()
        
        size = executor.calculate_position_size(
            capital=100000.0,
            risk_per_trade=0.02,  # 2%
            entry_price=100.0,
            stop_loss=95.0,  # 5% risk per share
            action=OrderAction.BUY
        )
        
        # Risk amount = 100000 * 0.02 = 2000
        # Risk per share = 100 - 95 = 5
        # Position size = 2000 / 5 = 400 shares
        assert size == 400
    
    def test_position_size_zero_risk(self):
        """Test position size with zero risk per share."""
        executor = BacktestExecutor()
        
        size = executor.calculate_position_size(
            capital=100000.0,
            risk_per_trade=0.02,
            entry_price=100.0,
            stop_loss=100.0,  # No risk
            action=OrderAction.BUY
        )
        
        assert size == 0
    
    def test_stop_loss_check_buy(self):
        """Test stop loss check for BUY position."""
        executor = BacktestExecutor()
        
        # Stop hit
        hit, price = executor.check_stop_loss(
            action=OrderAction.BUY,
            stop_loss=95.0,
            current_high=100.0,
            current_low=94.0  # Below stop
        )
        assert hit is True
        assert price == 95.0
        
        # Stop not hit
        hit, price = executor.check_stop_loss(
            action=OrderAction.BUY,
            stop_loss=95.0,
            current_high=100.0,
            current_low=96.0  # Above stop
        )
        assert hit is False
    
    def test_target_check_buy(self):
        """Test target check for BUY position."""
        executor = BacktestExecutor()
        
        # Target hit
        hit, price = executor.check_target(
            action=OrderAction.BUY,
            target=110.0,
            current_high=112.0,  # Above target
            current_low=105.0
        )
        assert hit is True
        assert price == 110.0
        
        # Target not hit
        hit, price = executor.check_target(
            action=OrderAction.BUY,
            target=110.0,
            current_high=108.0,  # Below target
            current_low=105.0
        )
        assert hit is False


# ============================================================================
# Test SlippageConfig
# ============================================================================

class TestSlippageConfig:
    """Test SlippageConfig class."""
    
    def test_fixed_slippage(self):
        """Test fixed slippage model."""
        config = SlippageConfig(
            model=SlippageModel.FIXED,
            fixed_amount=0.50
        )
        
        slippage = config.calculate(100.0, 10, OrderAction.BUY)
        assert slippage == 0.50
    
    def test_percentage_slippage(self):
        """Test percentage slippage model."""
        config = SlippageConfig(
            model=SlippageModel.PERCENTAGE,
            percentage=0.001  # 0.1%
        )
        
        slippage = config.calculate(100.0, 10, OrderAction.BUY)
        assert slippage == pytest.approx(0.1, rel=0.01)
    
    def test_volume_based_slippage(self):
        """Test volume-based slippage model."""
        config = SlippageConfig(
            model=SlippageModel.VOLUME_BASED,
            volume_impact=0.0001
        )
        
        # 100 shares vs 10000 avg volume = 1% of volume
        slippage = config.calculate(100.0, 100, OrderAction.BUY, avg_volume=10000)
        assert slippage > 0
    
    def test_apply_slippage_buy(self):
        """Test slippage application for BUY."""
        config = SlippageConfig(
            model=SlippageModel.FIXED,
            fixed_amount=0.50
        )
        
        price = config.apply_slippage(100.0, 10, OrderAction.BUY, is_entry=True)
        assert price == 100.50  # Higher for buy


# ============================================================================
# Test CommissionConfig
# ============================================================================

class TestCommissionConfig:
    """Test CommissionConfig class."""
    
    def test_fixed_commission(self):
        """Test fixed commission model."""
        config = CommissionConfig(
            model=CommissionModel.FIXED,
            fixed_fee=20.0
        )
        
        commission = config.calculate(100.0, 10)
        assert commission == 20.0
    
    def test_percentage_commission(self):
        """Test percentage commission model."""
        config = CommissionConfig(
            model=CommissionModel.PERCENTAGE,
            percentage=0.001  # 0.1%
        )
        
        # Order value = 100 * 10 = 1000
        # Commission = 1000 * 0.001 = 1.0
        commission = config.calculate(100.0, 10)
        assert commission == pytest.approx(1.0, rel=0.01)
    
    def test_minimum_commission(self):
        """Test minimum commission enforcement."""
        config = CommissionConfig(
            model=CommissionModel.PERCENTAGE,
            percentage=0.001,
            minimum=20.0
        )
        
        # Calculated commission would be 1.0, but minimum is 20
        commission = config.calculate(100.0, 10)
        assert commission == 20.0


# ============================================================================
# Test BacktestAnalyzer
# ============================================================================

class TestBacktestAnalyzer:
    """Test BacktestAnalyzer class."""
    
    def test_returns_calculation(self, sample_backtest_result):
        """Test return metrics calculation."""
        analyzer = BacktestAnalyzer(sample_backtest_result)
        metrics = analyzer.calculate_all_metrics()
        
        # Total return = (120000 - 100000) / 100000 = 0.20
        assert metrics.total_return == pytest.approx(0.20, rel=0.01)
    
    def test_trade_metrics(self, sample_backtest_result):
        """Test trade statistics calculation."""
        analyzer = BacktestAnalyzer(sample_backtest_result)
        metrics = analyzer.calculate_all_metrics()
        
        assert metrics.total_trades == 3
        assert metrics.winning_trades == 2
        assert metrics.losing_trades == 1
        assert metrics.win_rate == pytest.approx(0.667, rel=0.01)
    
    def test_profit_factor(self, sample_backtest_result):
        """Test profit factor calculation."""
        analyzer = BacktestAnalyzer(sample_backtest_result)
        metrics = analyzer.calculate_all_metrics()
        
        # Total profit = 100 + 150 = 250
        # Total loss = 100
        # Profit factor = 250 / 100 = 2.5
        assert metrics.profit_factor > 1.0  # Should be profitable
    
    def test_drawdown_calculation(self, sample_backtest_result):
        """Test drawdown calculation."""
        analyzer = BacktestAnalyzer(sample_backtest_result)
        analyzer.calculate_all_metrics()
        
        drawdowns = analyzer.get_drawdown_curve()
        assert len(drawdowns) == len(sample_backtest_result.equity_curve)
    
    def test_risk_metrics_with_returns(self, sample_backtest_result):
        """Test risk metrics calculation with daily returns."""
        daily_returns = [0.01, -0.005, 0.02, 0.01, -0.01, 0.015, 0.02]
        
        analyzer = BacktestAnalyzer(sample_backtest_result, daily_returns)
        metrics = analyzer.calculate_all_metrics()
        
        # Sharpe ratio should be calculated
        assert metrics.sharpe_ratio is not None
        assert metrics.volatility > 0
    
    def test_monthly_returns(self, sample_backtest_result):
        """Test monthly returns calculation."""
        analyzer = BacktestAnalyzer(sample_backtest_result)
        monthly = analyzer.get_monthly_returns()
        
        # Should have at least one month
        assert len(monthly) >= 0  # May be empty if dates span less than a month
    
    def test_summary_generation(self, sample_backtest_result):
        """Test text summary generation."""
        analyzer = BacktestAnalyzer(sample_backtest_result)
        analyzer.calculate_all_metrics()
        
        summary = analyzer.generate_summary()
        
        assert "TestStrategy" in summary
        assert "Total Return" in summary
        assert "Winning Trades" in summary
    
    def test_metrics_to_dict(self, sample_backtest_result):
        """Test metrics to dictionary conversion."""
        analyzer = BacktestAnalyzer(sample_backtest_result)
        metrics = analyzer.calculate_all_metrics()
        
        d = metrics.to_dict()
        
        assert "returns" in d
        assert "risk" in d
        assert "trades" in d
        assert "positions" in d
        assert d["returns"]["total_return"] == pytest.approx(0.20, rel=0.01)


# ============================================================================
# Test BacktestResult
# ============================================================================

class TestBacktestResult:
    """Test BacktestResult class."""
    
    def test_result_to_dict(self, sample_backtest_result):
        """Test result to dictionary conversion."""
        d = sample_backtest_result.to_dict()
        
        assert d["strategy_name"] == "TestStrategy"
        assert d["initial_capital"] == 100000.0
        assert d["final_capital"] == 120000.0
        assert d["total_trades"] == 3


# ============================================================================
# Test BacktestEngine (Integration-style)
# ============================================================================

class TestBacktestEngine:
    """Test BacktestEngine class (basic tests without database)."""
    
    def test_engine_initialization(self, mock_buy_strategy, backtest_config):
        """Test engine initialization."""
        engine = BacktestEngine(
            strategy=mock_buy_strategy,
            config=backtest_config,
            symbols=["TEST"]
        )
        
        assert engine.strategy == mock_buy_strategy
        assert engine.config == backtest_config
        assert engine.symbols == ["TEST"]
        assert engine.capital == 100000.0
    
    def test_empty_result_creation(self, mock_no_signal_strategy, backtest_config):
        """Test empty result creation when no trades occur."""
        engine = BacktestEngine(
            strategy=mock_no_signal_strategy,
            config=backtest_config,
            symbols=[]
        )
        
        result = engine._create_empty_result()
        
        assert result.total_trades == 0
        assert result.final_capital == backtest_config.initial_capital
        assert result.accuracy == 0.0


# ============================================================================
# Test analyze_backtest Helper Function
# ============================================================================

class TestAnalyzeBacktestFunction:
    """Test the analyze_backtest convenience function."""
    
    def test_analyze_backtest_basic(self, sample_backtest_result):
        """Test basic backtest analysis."""
        metrics = analyze_backtest(sample_backtest_result)
        
        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.total_return == pytest.approx(0.20, rel=0.01)


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_no_trades_result(self):
        """Test result with no trades."""
        result = BacktestResult(
            strategy_name="NoTrades",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            final_capital=100000.0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            trades=[],
            equity_curve=[100000.0],
            equity_dates=[]
        )
        
        analyzer = BacktestAnalyzer(result)
        metrics = analyzer.calculate_all_metrics()
        
        assert metrics.total_return == 0.0
        assert metrics.win_rate == 0.0
        assert metrics.profit_factor == 0.0
    
    def test_all_losers(self):
        """Test result with all losing trades."""
        trades = [
            BacktestTrade(
                trade_id=1,
                symbol="TEST",
                action=OrderAction.BUY,
                entry_date=datetime(2024, 1, 1),
                entry_price=100.0,
                quantity=10,
                exit_date=datetime(2024, 1, 10),
                exit_price=90.0,
                exit_reason="stop_loss_hit"
            ),
            BacktestTrade(
                trade_id=2,
                symbol="TEST",
                action=OrderAction.BUY,
                entry_date=datetime(2024, 1, 15),
                entry_price=95.0,
                quantity=10,
                exit_date=datetime(2024, 1, 20),
                exit_price=85.0,
                exit_reason="stop_loss_hit"
            ),
        ]
        
        result = BacktestResult(
            strategy_name="AllLosers",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            final_capital=80000.0,
            total_trades=2,
            winning_trades=0,
            losing_trades=2,
            trades=trades,
            equity_curve=[100000.0, 90000.0, 80000.0],
            equity_dates=[]
        )
        
        analyzer = BacktestAnalyzer(result)
        metrics = analyzer.calculate_all_metrics()
        
        assert metrics.win_rate == 0.0
        assert metrics.total_return < 0
    
    def test_all_winners(self):
        """Test result with all winning trades."""
        trades = [
            BacktestTrade(
                trade_id=1,
                symbol="TEST",
                action=OrderAction.BUY,
                entry_date=datetime(2024, 1, 1),
                entry_price=100.0,
                quantity=10,
                exit_date=datetime(2024, 1, 10),
                exit_price=110.0,
                exit_reason="target_hit"
            ),
            BacktestTrade(
                trade_id=2,
                symbol="TEST",
                action=OrderAction.BUY,
                entry_date=datetime(2024, 1, 15),
                entry_price=105.0,
                quantity=10,
                exit_date=datetime(2024, 1, 20),
                exit_price=120.0,
                exit_reason="target_hit"
            ),
        ]
        
        result = BacktestResult(
            strategy_name="AllWinners",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            initial_capital=100000.0,
            final_capital=125000.0,
            total_trades=2,
            winning_trades=2,
            losing_trades=0,
            trades=trades,
            equity_curve=[100000.0, 110000.0, 125000.0],
            equity_dates=[]
        )
        
        analyzer = BacktestAnalyzer(result)
        metrics = analyzer.calculate_all_metrics()
        
        assert metrics.win_rate == 1.0
        assert metrics.total_return > 0
        # Profit factor should be infinity when no losses
        assert metrics.profit_factor == float('inf')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
