# tests/unit/test_position_monitor.py
"""
Comprehensive unit tests for the PositionMonitor class.
Tests all 4 async monitoring loops, exit conditions, and statistics tracking.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.position_monitor import (
    PositionMonitor,
    MonitoringConfig,
    MonitoringStats,
    ExitReason,
)
from core.position_tracker import PositionTracker
from data.models import (
    Symbol,
    Position,
    OrderAction,
    TradingMode,
    Alert,
)


# ============================================================================
# Monitoring Configuration Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestMonitoringConfiguration:
    """Test monitoring configuration and initialization."""
    
    async def test_default_config_initialization(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test monitor initializes with default configuration."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        monitor = PositionMonitor(session_factory)
        
        assert monitor.config is not None
        assert monitor.config.stop_loss_interval == 30
        assert monitor.config.target_interval == 60
        assert monitor.config.enable_stop_losses is True
        assert monitor.config.enable_targets is True
        assert monitor.monitoring is False
    
    async def test_custom_config_initialization(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test monitor with custom configuration."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        config = MonitoringConfig(
            stop_loss_interval=15,
            target_interval=30,
            enable_trailing_stops=False,
        )
        monitor = PositionMonitor(session_factory, config)
        
        assert monitor.config.stop_loss_interval == 15
        assert monitor.config.target_interval == 30
        assert monitor.config.enable_trailing_stops is False


# ============================================================================
# Stop Loss Monitoring Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestStopLossMonitoring:
    """Test stop loss monitoring loop."""
    
    async def test_stop_loss_triggered_long_position(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test stop loss triggers for long position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        config = MonitoringConfig(
            stop_loss_interval=1,  # Fast for testing
            enable_targets=False,
            enable_time_exits=False,
            enable_risk_checks=False,
        )
        monitor = PositionMonitor(session_factory, config)
        
        # Create long position with stop loss
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,  # Long
            entry_price=2450.00,
            current_price=2400.00,  # Below stop
            stop_loss=2420.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock P&L calculation to return current price
        with patch.object(
            monitor.position_tracker,
            'calculate_pnl',
            return_value=MagicMock(current_price=2400.00)
        ):
            # Start monitoring briefly
            await monitor.start_monitoring()
            await asyncio.sleep(2)  # Let it check once
            await monitor.stop_monitoring()
        
        # Position should be closed
        await test_async_db_session.refresh(position)
        assert position.is_open is False
        assert monitor.stats.stop_losses_triggered >= 1
    
    async def test_stop_loss_triggered_short_position(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test stop loss triggers for short position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        config = MonitoringConfig(
            stop_loss_interval=1,
            enable_targets=False,
            enable_time_exits=False,
            enable_risk_checks=False,
        )
        monitor = PositionMonitor(session_factory, config)
        
        # Create short position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=-10,  # Short
            entry_price=2450.00,
            current_price=2480.00,  # Above stop (bad for short)
            stop_loss=2470.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock P&L calculation
        with patch.object(
            monitor.position_tracker,
            'calculate_pnl',
            return_value=MagicMock(current_price=2480.00)
        ):
            await monitor.start_monitoring()
            await asyncio.sleep(2)
            await monitor.stop_monitoring()
        
        # Position should be closed
        await test_async_db_session.refresh(position)
        assert position.is_open is False


# ============================================================================
# Target Monitoring Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestTargetMonitoring:
    """Test profit target monitoring loop."""
    
    async def test_target_hit_long_position(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test target hit for long position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        config = MonitoringConfig(
            target_interval=1,
            enable_stop_losses=False,
            enable_time_exits=False,
            enable_risk_checks=False,
        )
        monitor = PositionMonitor(session_factory, config)
        
        # Create long position that hit target
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2550.00,  # Above target
            target=2500.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock P&L calculation
        with patch.object(
            monitor.position_tracker,
            'calculate_pnl',
            return_value=MagicMock(current_price=2550.00)
        ):
            await monitor.start_monitoring()
            await asyncio.sleep(2)
            await monitor.stop_monitoring()
        
        # Position should be closed
        await test_async_db_session.refresh(position)
        assert position.is_open is False
        assert monitor.stats.targets_hit >= 1


# ============================================================================
# Time Exit Monitoring Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestTimeExitMonitoring:
    """Test time-based exit monitoring."""
    
    async def test_max_duration_exit(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test position closed after exceeding max duration."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        config = MonitoringConfig(
            time_exit_interval=1,
            max_position_duration_hours=1,  # 1 hour
            enable_stop_losses=False,
            enable_targets=False,
            enable_risk_checks=False,
        )
        monitor = PositionMonitor(session_factory, config)
        
        # Create old position (2 hours old)
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2475.00,
            entry_time=datetime.utcnow() - timedelta(hours=2),
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock P&L calculation
        with patch.object(
            monitor.position_tracker,
            'calculate_pnl',
            return_value=MagicMock(current_price=2475.00)
        ):
            await monitor.start_monitoring()
            await asyncio.sleep(2)
            await monitor.stop_monitoring()
        
        # Position should be closed
        await test_async_db_session.refresh(position)
        assert position.is_open is False
        assert monitor.stats.time_exits >= 1


# ============================================================================
# Risk Violation Monitoring Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestRiskViolationMonitoring:
    """Test risk violation monitoring."""
    
    async def test_position_loss_limit_exceeded(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test position closed when loss limit exceeded."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        config = MonitoringConfig(
            risk_check_interval=1,
            max_position_loss_pct=5.0,  # 5% max loss
            enable_stop_losses=False,
            enable_targets=False,
            enable_time_exits=False,
        )
        monitor = PositionMonitor(session_factory, config)
        
        # Create position with >5% loss
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2300.00,  # ~6% loss
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock P&L calculation with loss
        mock_pnl = MagicMock()
        mock_pnl.current_price = 2300.00
        mock_pnl.unrealized_pnl = -1500.0  # Loss
        mock_pnl.unrealized_pnl_pct = -6.12  # ~6% loss
        mock_pnl.total_investment = 24500.0
        
        with patch.object(
            monitor.position_tracker,
            'calculate_pnl',
            return_value=mock_pnl
        ):
            await monitor.start_monitoring()
            await asyncio.sleep(2)
            await monitor.stop_monitoring()
        
        # Position should be closed due to risk violation
        await test_async_db_session.refresh(position)
        assert position.is_open is False
        assert monitor.stats.risk_violations >= 1


# ============================================================================
# Monitoring Lifecycle Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestMonitoringLifecycle:
    """Test monitoring start/stop lifecycle."""
    
    async def test_start_monitoring(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test starting monitoring creates tasks."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        monitor = PositionMonitor(session_factory)
        
        await monitor.start_monitoring()
        
        assert monitor.monitoring is True
        assert len(monitor._tasks) == 4  # 4 monitoring loops
        
        await monitor.stop_monitoring()
    
    async def test_stop_monitoring(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test stopping monitoring cancels all tasks."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        monitor = PositionMonitor(session_factory)
        
        await monitor.start_monitoring()
        assert monitor.monitoring is True
        
        await monitor.stop_monitoring()
        
        assert monitor.monitoring is False
        assert len(monitor._tasks) == 0
    
    async def test_double_start_ignored(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test that starting monitoring twice is handled gracefully."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        monitor = PositionMonitor(session_factory)
        
        await monitor.start_monitoring()
        task_count = len(monitor._tasks)
        
        await monitor.start_monitoring()  # Second start
        
        assert len(monitor._tasks) == task_count  # No new tasks
        
        await monitor.stop_monitoring()


# ============================================================================
# Statistics Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestMonitoringStatistics:
    """Test monitoring statistics tracking."""
    
    async def test_get_stats(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test getting monitoring statistics."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        monitor = PositionMonitor(session_factory)
        
        stats = monitor.get_stats()
        
        assert isinstance(stats, MonitoringStats)
        assert stats.positions_monitored == 0
        assert stats.stop_losses_triggered == 0
        assert stats.targets_hit == 0
    
    async def test_reset_stats(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test resetting monitoring statistics."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        monitor = PositionMonitor(session_factory)
        
        # Modify stats
        monitor.stats.stop_losses_triggered = 5
        monitor.stats.targets_hit = 3
        
        # Reset
        monitor.reset_stats()
        
        assert monitor.stats.stop_losses_triggered == 0
        assert monitor.stats.targets_hit == 0
    
    async def test_stats_summary(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test statistics summary generation."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        monitor = PositionMonitor(session_factory)
        
        monitor.stats.stop_losses_triggered = 5
        monitor.stats.targets_hit = 3
        monitor.stats.time_exits = 2
        
        summary = monitor.stats.summary()
        
        assert "Stop losses triggered: 5" in summary
        assert "Targets hit: 3" in summary
        assert "Time exits: 2" in summary
