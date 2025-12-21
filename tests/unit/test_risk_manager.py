# tests/unit/test_risk_manager.py - Unit tests for RiskManager
"""
Comprehensive unit tests for the RiskManager class.
Tests position sizing, risk checks, circuit breakers, and portfolio limits.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

from sqlalchemy.orm import Session

from core.risk_manager import (
    RiskManager,
    RiskCheckResult,
    PositionSizeRecommendation,
)
from data.models import (
    Symbol,
    Position,
    Order,
    OrderAction,
    OrderStatus,
    TradingMode,
)
from config.risk_config import PositionSizingMethod
from config.settings import Settings


# ============================================================================
# Position Sizing Tests
# ============================================================================

@pytest.mark.unit
class TestPositionSizing:
    """Test position sizing methods."""
    
    def test_fixed_fractional_sizing(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test fixed fractional position sizing method."""
        risk_manager = RiskManager(test_db_session)
        
        # Setup test data
        signal_data = {
            "action": OrderAction.BUY,
            "price": 2450.00,
            "stop_loss": 2400.00,  # 50 points risk = 2.04%
            "target": 2550.00,
        }
        account_info = {"balance": 100000.00}
        
        # Calculate position size
        recommendation = risk_manager.calculate_position_size(
            symbol="RELIANCE",
            signal_data=signal_data,
            account_info=account_info,
            method=PositionSizingMethod.FIXED_FRACTIONAL
        )
        
        # Assertions
        assert recommendation is not None
        assert recommendation.symbol == "RELIANCE"
        assert recommendation.quantity > 0
        assert recommendation.entry_price == 2450.00
        assert recommendation.stop_loss == 2400.00
        assert recommendation.target == 2550.00
        assert recommendation.sizing_method == PositionSizingMethod.FIXED_FRACTIONAL
        
        # Check risk amount is ~2% of capital (default risk_per_trade)
        # Risk per share = 2450 - 2400 = 50
        # Max risk = 100000 * 0.02 = 2000
        # Quantity should be around 2000 / 50 = 40 shares
        assert recommendation.risk_amount <= 2000.0
        assert recommendation.risk_amount > 0
        
        # Position value should be reasonable
        assert recommendation.position_value > 0
        assert recommendation.position_value <= account_info["balance"]
    
    def test_kelly_criterion_sizing(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test Kelly Criterion position sizing method."""
        risk_manager = RiskManager(test_db_session)
        
        signal_data = {
            "action": OrderAction.BUY,
            "price": 2450.00,
            "stop_loss": 2400.00,
            "target": 2550.00,
        }
        account_info = {"balance": 100000.00}
        
        # Provide win rate and risk:reward for Kelly
        symbol_data = {
            "win_rate": 0.65,  # 65% win rate
            "risk_reward_ratio": 2.0,  # 2:1 reward:risk
        }
        
        recommendation = risk_manager.calculate_position_size(
            symbol="RELIANCE",
            signal_data=signal_data,
            account_info=account_info,
            method=PositionSizingMethod.KELLY_CRITERION,
            symbol_data=symbol_data
        )
        
        assert recommendation is not None
        assert recommendation.quantity > 0
        assert recommendation.sizing_method == PositionSizingMethod.KELLY_CRITERION
        # Kelly sizing typically more aggressive than fixed fractional
        assert recommendation.position_pct > 0
    
    def test_risk_parity_sizing(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test risk parity position sizing method."""
        risk_manager = RiskManager(test_db_session)
        
        signal_data = {
            "action": OrderAction.BUY,
            "price": 2450.00,
            "stop_loss": 2400.00,
            "target": 2550.00,
        }
        account_info = {"balance": 100000.00}
        
        # Provide volatility for risk parity
        symbol_data = {
            "volatility": 0.025,  # 2.5% daily volatility
        }
        
        recommendation = risk_manager.calculate_position_size(
            symbol="RELIANCE",
            signal_data=signal_data,
            account_info=account_info,
            method=PositionSizingMethod.RISK_PARITY,
            symbol_data=symbol_data
        )
        
        assert recommendation is not None
        assert recommendation.quantity > 0
        assert recommendation.sizing_method == PositionSizingMethod.RISK_PARITY
    
    def test_atr_based_sizing(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test ATR-based position sizing method."""
        risk_manager = RiskManager(test_db_session)
        
        signal_data = {
            "action": OrderAction.BUY,
            "price": 2450.00,
            "target": 2550.00,
            # No stop_loss provided - should use ATR
        }
        account_info = {"balance": 100000.00}
        
        # Provide ATR
        symbol_data = {
            "atr": 45.0,  # Average True Range
        }
        
        recommendation = risk_manager.calculate_position_size(
            symbol="RELIANCE",
            signal_data=signal_data,
            account_info=account_info,
            method=PositionSizingMethod.ATR_BASED,
            symbol_data=symbol_data
        )
        
        assert recommendation is not None
        assert recommendation.quantity > 0
        assert recommendation.sizing_method == PositionSizingMethod.ATR_BASED
        # Stop loss should be calculated based on ATR
        assert recommendation.stop_loss > 0
        assert recommendation.stop_loss < recommendation.entry_price
    
    @pytest.mark.parametrize("method", [
        PositionSizingMethod.FIXED_FRACTIONAL,
        PositionSizingMethod.KELLY_CRITERION,
        PositionSizingMethod.RISK_PARITY,
        PositionSizingMethod.ATR_BASED,
    ])
    def test_all_sizing_methods_return_valid_recommendation(
        self,
        test_db_session: Session,
        sample_symbol: Symbol,
        method: str
    ):
        """Test that all sizing methods return valid recommendations."""
        risk_manager = RiskManager(test_db_session)
        
        signal_data = {
            "action": OrderAction.BUY,
            "price": 2450.00,
            "stop_loss": 2400.00,
            "target": 2550.00,
        }
        account_info = {"balance": 100000.00}
        symbol_data = {
            "atr": 45.0,
            "volatility": 0.025,
            "win_rate": 0.65,
            "risk_reward_ratio": 2.0,
        }
        
        recommendation = risk_manager.calculate_position_size(
            symbol="RELIANCE",
            signal_data=signal_data,
            account_info=account_info,
            method=method,
            symbol_data=symbol_data
        )
        
        # All methods should return valid recommendations
        assert recommendation is not None
        assert recommendation.quantity >= 0
        assert recommendation.entry_price > 0
        assert recommendation.stop_loss > 0
        assert recommendation.sizing_method == method


# ============================================================================
# Portfolio Exposure Tests
# ============================================================================

@pytest.mark.unit
class TestPortfolioExposure:
    """Test portfolio exposure checks."""
    
    def test_portfolio_exposure_within_limits(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test that portfolio exposure check passes when within limits."""
        risk_manager = RiskManager(test_db_session)
        
        # Create one existing position (20% exposure)
        existing_position = Position(
            symbol_id=sample_symbol.id,
            quantity=8,
            entry_price=2450.00,
            current_price=2450.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_db_session.add(existing_position)
        test_db_session.commit()
        
        # Try to add another position (10% exposure)
        # Total would be 30%, which is under typical 80% limit
        result = risk_manager._check_portfolio_exposure(
            new_position_value=10000.0,  # 10% of 100k
            account_balance=100000.0
        )
        
        assert result.passed is True
        assert len(result.violations) == 0
        assert result.metadata["exposure_pct"] == pytest.approx(30.0, rel=0.1)
    
    def test_portfolio_exposure_exceeds_limit(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test that portfolio exposure check fails when exceeding limits."""
        risk_manager = RiskManager(test_db_session)
        
        # Create multiple existing positions totaling 75% exposure
        for i in range(3):
            position = Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2500.00,
                current_price=2500.00,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            )
            test_db_session.add(position)
        test_db_session.commit()
        
        # Try to add another large position (30% exposure)
        # Total would be 105%, which exceeds typical 80% limit
        result = risk_manager._check_portfolio_exposure(
            new_position_value=30000.0,  # 30% of 100k
            account_balance=100000.0
        )
        
        assert result.passed is False
        assert len(result.violations) > 0
        assert any("exposure" in v.lower() for v in result.violations)
    
    def test_portfolio_exposure_warning_threshold(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test that warnings are issued when approaching exposure limits."""
        risk_manager = RiskManager(test_db_session)
        
        # Create positions totaling ~72% exposure (90% of 80% limit)
        for i in range(7):
            position = Position(
                symbol_id=sample_symbol.id,
                quantity=4,
                entry_price=2500.00,
                current_price=2500.00,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            )
            test_db_session.add(position)
        test_db_session.commit()
        
        # Add small position that brings us close to limit
        result = risk_manager._check_portfolio_exposure(
            new_position_value=2000.0,
            account_balance=100000.0
        )
        
        # Should pass but with warnings
        assert result.passed is True
        assert len(result.warnings) > 0
        assert any("approaching" in w.lower() for w in result.warnings)


# ============================================================================
# Position Limits Tests
# ============================================================================

@pytest.mark.unit
class TestPositionLimits:
    """Test position count and per-symbol limits."""
    
    def test_position_limits_within_max(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test position limits check passes when within maximum."""
        risk_manager = RiskManager(test_db_session)
        
        # Create 3 open positions (under typical limit of 5-10)
        for i in range(3):
            position = Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2450.00,
                current_price=2450.00,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            )
            test_db_session.add(position)
        test_db_session.commit()
        
        result = risk_manager._check_position_limits("RELIANCE")
        
        assert result.passed is True
        assert len(result.violations) == 0
    
    def test_position_limits_at_maximum(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test position limits check fails when at maximum."""
        risk_manager = RiskManager(test_db_session)
        
        # Create maximum number of positions (typically 5-10)
        # Using 10 to ensure we hit the limit
        for i in range(10):
            position = Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2450.00,
                current_price=2450.00,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            )
            test_db_session.add(position)
        test_db_session.commit()
        
        result = risk_manager._check_position_limits("RELIANCE")
        
        # Should fail or warn depending on exact limit configuration
        assert result.passed is False or len(result.warnings) > 0
    
    def test_per_symbol_position_limit(
        self,
        test_db_session: Session
    ):
        """Test per-symbol position limits."""
        from conftest import create_test_symbol
        
        risk_manager = RiskManager(test_db_session)
        
        # Create two symbols
        symbol1 = create_test_symbol(test_db_session, "SYM1", "Symbol 1")
        symbol2 = create_test_symbol(test_db_session, "SYM2", "Symbol 2")
        
        # Create multiple positions in SYM1 (at limit)
        for i in range(3):  # Typical per-symbol limit is 2-3
            position = Position(
                symbol_id=symbol1.id,
                quantity=10,
                entry_price=100.00,
                current_price=100.00,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            )
            test_db_session.add(position)
        test_db_session.commit()
        
        # Check SYM1 - should fail
        result1 = risk_manager._check_position_limits("SYM1")
        
        # Check SYM2 - should pass (no positions yet)
        result2 = risk_manager._check_position_limits("SYM2")
        
        assert result2.passed is True


# ============================================================================
# Circuit Breaker Tests
# ============================================================================

@pytest.mark.unit
class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def test_circuit_breaker_trigger_on_max_drawdown(
        self,
        test_db_session: Session
    ):
        """Test circuit breaker triggers on maximum drawdown."""
        risk_manager = RiskManager(test_db_session)
        
        # Simulate large drawdown (current balance much lower than initial)
        current_balance = 60000.0  # 40% drawdown from 100k
        
        result = risk_manager._check_drawdown_limits(current_balance)
        
        # Should trigger circuit breaker for large drawdown
        assert risk_manager.circuit_breaker_active is True
        assert risk_manager.circuit_breaker_reason is not None
        assert "drawdown" in risk_manager.circuit_breaker_reason.lower()
    
    def test_circuit_breaker_trigger_on_consecutive_losses(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test circuit breaker triggers on consecutive losses."""
        risk_manager = RiskManager(test_db_session)
        
        # Create multiple losing positions
        for i in range(6):  # Typical limit is 5 consecutive losses
            position = Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2450.00,
                current_price=2300.00,  # Loss
                realized_pnl=-150.0 * 10,  # -1500 per position
                is_open=False,
                trading_mode=TradingMode.LIVE,
                entry_time=datetime.utcnow() - timedelta(days=i+1),
                exit_time=datetime.utcnow() - timedelta(days=i),
            )
            test_db_session.add(position)
        test_db_session.commit()
        
        result = risk_manager._check_drawdown_limits(90000.0)
        
        # Should trigger circuit breaker
        assert risk_manager.circuit_breaker_active is True
        assert "consecutive" in risk_manager.circuit_breaker_reason.lower()
    
    def test_circuit_breaker_blocks_new_positions(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test that circuit breaker blocks new position recommendations."""
        risk_manager = RiskManager(test_db_session)
        
        # Manually trigger circuit breaker
        risk_manager._trigger_circuit_breaker("Test trigger")
        
        # Try to get position recommendation
        signal_data = {
            "action": OrderAction.BUY,
            "price": 2450.00,
            "stop_loss": 2400.00,
            "target": 2550.00,
        }
        account_info = {"balance": 100000.00}
        
        recommendation = risk_manager.calculate_position_size(
            symbol="RELIANCE",
            signal_data=signal_data,
            account_info=account_info
        )
        
        # Should not pass risk checks
        assert recommendation.passed_checks is False
        assert any("circuit breaker" in w.lower() for w in recommendation.warnings)
    
    def test_circuit_breaker_reset_manual(
        self,
        test_db_session: Session
    ):
        """Test manual circuit breaker reset."""
        risk_manager = RiskManager(test_db_session)
        
        # Trigger circuit breaker
        risk_manager._trigger_circuit_breaker("Test trigger")
        assert risk_manager.circuit_breaker_active is True
        
        # Wait for cooldown (simulate)
        risk_manager.circuit_breaker_triggered_at = datetime.utcnow() - timedelta(hours=25)
        
        # Reset manually
        success = risk_manager.reset_circuit_breaker(manual=True)
        
        assert success is True
        assert risk_manager.circuit_breaker_active is False
        assert risk_manager.circuit_breaker_reason is None
    
    def test_circuit_breaker_reset_before_cooldown(
        self,
        test_db_session: Session
    ):
        """Test circuit breaker reset fails before cooldown period."""
        risk_manager = RiskManager(test_db_session)
        
        # Trigger circuit breaker
        risk_manager._trigger_circuit_breaker("Test trigger")
        
        # Try to reset immediately (cooldown not elapsed)
        success = risk_manager.reset_circuit_breaker(manual=True)
        
        assert success is False
        assert risk_manager.circuit_breaker_active is True


# ============================================================================
# Risk:Reward Ratio Tests
# ============================================================================

@pytest.mark.unit
class TestRiskRewardValidation:
    """Test risk:reward ratio validation."""
    
    def test_valid_risk_reward_ratio(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test that valid risk:reward ratio passes validation."""
        risk_manager = RiskManager(test_db_session)
        
        signal_data = {
            "action": OrderAction.BUY,
            "price": 2450.00,
            "stop_loss": 2400.00,  # 50 points risk
            "target": 2550.00,     # 100 points reward = 2:1 ratio
        }
        account_info = {"balance": 100000.00}
        
        recommendation = risk_manager.calculate_position_size(
            symbol="RELIANCE",
            signal_data=signal_data,
            account_info=account_info
        )
        
        assert recommendation.risk_reward_ratio >= 2.0
        assert recommendation.passed_checks is True
    
    def test_invalid_risk_reward_ratio(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test that invalid risk:reward ratio fails validation."""
        risk_manager = RiskManager(test_db_session)
        
        signal_data = {
            "action": OrderAction.BUY,
            "price": 2450.00,
            "stop_loss": 2400.00,  # 50 points risk
            "target": 2475.00,     # 25 points reward = 0.5:1 ratio (poor)
        }
        account_info = {"balance": 100000.00}
        
        recommendation = risk_manager.calculate_position_size(
            symbol="RELIANCE",
            signal_data=signal_data,
            account_info=account_info
        )
        
        # Should have violations for poor risk:reward
        assert recommendation.risk_reward_ratio < 2.0
        assert recommendation.passed_checks is False
        assert any("risk:reward" in v.lower() or "risk reward" in v.lower() 
                  for v in recommendation.warnings)


# ============================================================================
# Portfolio Metrics Tests
# ============================================================================

@pytest.mark.unit
class TestPortfolioMetrics:
    """Test portfolio metrics calculation."""
    
    def test_get_portfolio_metrics_with_open_positions(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test portfolio metrics calculation with open positions."""
        risk_manager = RiskManager(test_db_session)
        
        # Create open positions
        positions = [
            Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2450.00,
                current_price=2475.00,
                unrealized_pnl=250.0,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            ),
            Position(
                symbol_id=sample_symbol.id,
                quantity=5,
                entry_price=2400.00,
                current_price=2450.00,
                unrealized_pnl=250.0,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            ),
        ]
        for pos in positions:
            test_db_session.add(pos)
        test_db_session.commit()
        
        metrics = risk_manager.get_portfolio_metrics()
        
        assert metrics["num_open_positions"] == 2
        assert metrics["total_position_value"] > 0
        assert metrics["unrealized_pnl"] == pytest.approx(500.0, rel=0.1)
        assert metrics["exposure_pct"] > 0
    
    def test_get_portfolio_metrics_empty_portfolio(
        self,
        test_db_session: Session
    ):
        """Test portfolio metrics with no positions."""
        risk_manager = RiskManager(test_db_session)
        
        metrics = risk_manager.get_portfolio_metrics()
        
        assert metrics["num_open_positions"] == 0
        assert metrics["total_position_value"] == 0.0
        assert metrics["unrealized_pnl"] == 0.0
        assert metrics["exposure_pct"] == 0.0
    
    def test_get_portfolio_metrics_includes_performance(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test that portfolio metrics include performance statistics."""
        risk_manager = RiskManager(test_db_session)
        
        # Create closed positions for performance
        winning_positions = [
            Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2400.00,
                current_price=2500.00,
                realized_pnl=1000.0,
                is_open=False,
                trading_mode=TradingMode.LIVE,
                entry_time=datetime.utcnow() - timedelta(days=2),
                exit_time=datetime.utcnow() - timedelta(days=1),
            ),
            Position(
                symbol_id=sample_symbol.id,
                quantity=5,
                entry_price=2450.00,
                current_price=2400.00,
                realized_pnl=-250.0,
                is_open=False,
                trading_mode=TradingMode.LIVE,
                entry_time=datetime.utcnow() - timedelta(days=1),
                exit_time=datetime.utcnow(),
            ),
        ]
        for pos in winning_positions:
            test_db_session.add(pos)
        test_db_session.commit()
        
        metrics = risk_manager.get_portfolio_metrics()
        
        assert metrics["total_trades"] == 2
        assert metrics["winning_trades"] == 1
        assert metrics["win_rate"] == pytest.approx(0.5, rel=0.01)
        assert metrics["realized_pnl"] == pytest.approx(750.0, rel=0.1)


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_zero_quantity_position_rejected(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test that zero quantity positions are rejected."""
        risk_manager = RiskManager(test_db_session)
        
        result = risk_manager._validate_position_risk(
            symbol="RELIANCE",
            quantity=0,
            entry_price=2450.00,
            stop_loss=2400.00,
            target=2550.00,
            action=OrderAction.BUY,
            account_balance=100000.0
        )
        
        assert result.passed is False
        assert any("quantity" in v.lower() for v in result.violations)
    
    def test_negative_quantity_position_rejected(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test that negative quantity positions are rejected."""
        risk_manager = RiskManager(test_db_session)
        
        result = risk_manager._validate_position_risk(
            symbol="RELIANCE",
            quantity=-10,
            entry_price=2450.00,
            stop_loss=2400.00,
            target=2550.00,
            action=OrderAction.BUY,
            account_balance=100000.0
        )
        
        assert result.passed is False
    
    def test_unknown_symbol_handled(
        self,
        test_db_session: Session
    ):
        """Test handling of unknown symbols."""
        risk_manager = RiskManager(test_db_session)
        
        result = risk_manager._check_position_limits("NONEXISTENT")
        
        assert result.passed is False
        assert any("not found" in v.lower() for v in result.violations)
    
    def test_invalid_sizing_method_fallback(
        self,
        test_db_session: Session,
        sample_symbol: Symbol
    ):
        """Test fallback to default method for invalid sizing method."""
        risk_manager = RiskManager(test_db_session)
        
        signal_data = {
            "action": OrderAction.BUY,
            "price": 2450.00,
            "stop_loss": 2400.00,
            "target": 2550.00,
        }
        account_info = {"balance": 100000.00}
        
        # Use invalid method name
        recommendation = risk_manager.calculate_position_size(
            symbol="RELIANCE",
            signal_data=signal_data,
            account_info=account_info,
            method="INVALID_METHOD"
        )
        
        # Should fall back to fixed_fractional
        assert recommendation is not None
        assert recommendation.sizing_method == PositionSizingMethod.FIXED_FRACTIONAL
