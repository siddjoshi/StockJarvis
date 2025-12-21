# tests/unit/test_position_tracker.py - Unit tests for PositionTracker
"""
Comprehensive unit tests for the PositionTracker class.
Tests position tracking, P&L calculation, broker updates, and position lifecycle.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.position_tracker import (
    PositionTracker,
    PnLCalculation,
    BrokerPosition,
)
from data.models import (
    Symbol,
    Position,
    Price,
    OrderAction,
    TradingMode,
    Exchange,
    Timeframe,
)


# ============================================================================
# Position Tracking Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestPositionTracking:
    """Test position tracking functionality."""
    
    async def test_track_position_basic(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test basic position tracking."""
        # Create async session factory
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create a position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock price fetching
        with patch.object(tracker, '_get_current_price', return_value=2475.00):
            pnl_calc = await tracker.track_position(position.id)
        
        assert pnl_calc is not None
        assert pnl_calc.symbol == "RELIANCE"
        assert pnl_calc.quantity == 10
        assert pnl_calc.entry_price == 2450.00
        assert pnl_calc.current_price == 2475.00
        assert pnl_calc.unrealized_pnl == pytest.approx(250.0, rel=0.01)
    
    async def test_track_position_not_found(self, test_async_db_session: AsyncSession):
        """Test tracking non-existent position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        pnl_calc = await tracker.track_position(99999)
        
        assert pnl_calc is None
    
    async def test_track_position_updates_database(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test that tracking updates position in database."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2450.00,  # Initial price
            unrealized_pnl=0.0,
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        initial_updated_at = position.updated_at
        
        # Track with new price
        with patch.object(tracker, '_get_current_price', return_value=2500.00):
            await tracker.track_position(position.id)
        
        # Refresh from database
        await test_async_db_session.refresh(position)
        
        # Check updates
        assert position.current_price == 2500.00
        assert position.unrealized_pnl == pytest.approx(500.0, rel=0.01)
        assert position.updated_at > initial_updated_at
    
    async def test_track_closed_position_skipped(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test that closed positions are skipped during tracking."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create closed position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2500.00,
            is_open=False,  # Closed
            realized_pnl=500.0,
            trading_mode=TradingMode.PAPER,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        pnl_calc = await tracker.track_position(position.id)
        
        assert pnl_calc is None


# ============================================================================
# P&L Calculation Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestPnLCalculation:
    """Test P&L calculation logic."""
    
    async def test_calculate_pnl_long_position_profit(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test P&L calculation for profitable long position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,  # Long (positive quantity)
            entry_price=2450.00,
            current_price=2500.00,
            stop_loss=2400.00,
            target=2550.00,
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        position.symbol = sample_symbol
        
        pnl_calc = await tracker.calculate_pnl(position, current_price=2500.00)
        
        # Long position: (current - entry) * quantity
        expected_pnl = (2500.00 - 2450.00) * 10
        assert pnl_calc.unrealized_pnl == pytest.approx(expected_pnl, rel=0.01)
        assert pnl_calc.unrealized_pnl_pct == pytest.approx(2.04, rel=0.1)  # ~2.04%
        assert pnl_calc.position_value == pytest.approx(25000.0, rel=0.01)
        assert pnl_calc.distance_to_stop_pct > 0
        assert pnl_calc.distance_to_target_pct > 0
    
    async def test_calculate_pnl_long_position_loss(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test P&L calculation for losing long position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2400.00,  # Below entry
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        position.symbol = sample_symbol
        
        pnl_calc = await tracker.calculate_pnl(position, current_price=2400.00)
        
        expected_pnl = (2400.00 - 2450.00) * 10  # -500
        assert pnl_calc.unrealized_pnl == pytest.approx(expected_pnl, rel=0.01)
        assert pnl_calc.unrealized_pnl < 0
        assert pnl_calc.unrealized_pnl_pct < 0
    
    async def test_calculate_pnl_short_position(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test P&L calculation for short position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=-10,  # Short (negative quantity)
            entry_price=2450.00,
            current_price=2400.00,  # Price dropped - profit for short
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        position.symbol = sample_symbol
        
        pnl_calc = await tracker.calculate_pnl(position, current_price=2400.00)
        
        # Short position: (entry - current) * abs(quantity)
        expected_pnl = (2450.00 - 2400.00) * 10  # +500
        assert pnl_calc.unrealized_pnl == pytest.approx(expected_pnl, rel=0.01)
        assert pnl_calc.unrealized_pnl > 0
    
    async def test_calculate_pnl_zero_price(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test P&L calculation with zero price edge case."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2450.00,
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        position.symbol = sample_symbol
        
        # Calculate with same price (zero P&L)
        pnl_calc = await tracker.calculate_pnl(position, current_price=2450.00)
        
        assert pnl_calc.unrealized_pnl == pytest.approx(0.0, abs=0.01)
        assert pnl_calc.unrealized_pnl_pct == pytest.approx(0.0, abs=0.01)
    
    async def test_calculate_pnl_with_stop_and_target(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test P&L calculation includes stop loss and target distances."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2475.00,
            stop_loss=2400.00,
            target=2550.00,
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        position.symbol = sample_symbol
        
        pnl_calc = await tracker.calculate_pnl(position, current_price=2475.00)
        
        # Distance to stop: (2475 - 2400) / 2475 * 100 = ~3.03%
        assert pnl_calc.distance_to_stop_pct == pytest.approx(3.03, rel=0.1)
        
        # Distance to target: (2550 - 2475) / 2475 * 100 = ~3.03%
        assert pnl_calc.distance_to_target_pct == pytest.approx(3.03, rel=0.1)


# ============================================================================
# Broker Update Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestBrokerUpdate:
    """Test updating positions from broker data."""
    
    async def test_update_from_broker_success(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test successful position update from broker."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2450.00,
            unrealized_pnl=0.0,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Broker data with updated price
        broker_data = BrokerPosition(
            symbol="RELIANCE",
            quantity=10,
            average_price=2450.00,
            last_price=2500.00,
            pnl=500.0,
            broker_id="BRK123",
            exchange="NSE",
            product="CNC"
        )
        
        success = await tracker.update_position_from_broker(position.id, broker_data)
        
        assert success is True
        
        # Verify update
        await test_async_db_session.refresh(position)
        assert position.current_price == 2500.00
        assert position.unrealized_pnl == pytest.approx(500.0, rel=0.01)
    
    async def test_update_from_broker_symbol_mismatch(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test broker update fails with symbol mismatch."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2450.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Broker data with different symbol
        broker_data = BrokerPosition(
            symbol="TCS",  # Different symbol
            quantity=10,
            average_price=3500.00,
            last_price=3550.00,
            pnl=500.0,
            broker_id="BRK123",
            exchange="NSE",
            product="CNC"
        )
        
        success = await tracker.update_position_from_broker(position.id, broker_data)
        
        assert success is False
    
    async def test_update_from_broker_position_not_found(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test broker update with non-existent position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        broker_data = BrokerPosition(
            symbol="RELIANCE",
            quantity=10,
            average_price=2450.00,
            last_price=2500.00,
            pnl=500.0,
            broker_id="BRK123",
            exchange="NSE",
            product="CNC"
        )
        
        success = await tracker.update_position_from_broker(99999, broker_data)
        
        assert success is False


# ============================================================================
# Position Lifecycle Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestPositionLifecycle:
    """Test position lifecycle management."""
    
    async def test_close_position_success(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test successfully closing a position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create open position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2475.00,
            unrealized_pnl=250.0,
            is_open=True,
            trading_mode=TradingMode.PAPER,
            entry_time=datetime.utcnow() - timedelta(hours=2),
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Close position
        success = await tracker.close_position(
            position_id=position.id,
            exit_price=2500.00,
            exit_reason="target_hit"
        )
        
        assert success is True
        
        # Verify position is closed
        await test_async_db_session.refresh(position)
        assert position.is_open is False
        assert position.realized_pnl == pytest.approx(500.0, rel=0.01)
        assert position.unrealized_pnl == 0.0
        assert position.exit_time is not None
    
    async def test_close_position_short(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test closing a short position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create short position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=-10,  # Short
            entry_price=2450.00,
            current_price=2450.00,
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Close at profit (price dropped)
        success = await tracker.close_position(
            position_id=position.id,
            exit_price=2400.00,
            exit_reason="target_hit"
        )
        
        assert success is True
        await test_async_db_session.refresh(position)
        
        # Short profit: (2450 - 2400) * 10 = 500
        assert position.realized_pnl == pytest.approx(500.0, rel=0.01)
    
    async def test_close_already_closed_position(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test closing an already closed position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create closed position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2500.00,
            realized_pnl=500.0,
            is_open=False,  # Already closed
            trading_mode=TradingMode.PAPER,
            exit_time=datetime.utcnow(),
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        success = await tracker.close_position(
            position_id=position.id,
            exit_price=2550.00,
            exit_reason="manual"
        )
        
        # Should fail or warn
        assert success is False
    
    async def test_close_position_not_found(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test closing non-existent position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        success = await tracker.close_position(
            position_id=99999,
            exit_price=2500.00,
            exit_reason="manual"
        )
        
        assert success is False


# ============================================================================
# Active Positions Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestActivePositions:
    """Test getting active positions."""
    
    async def test_get_active_positions_live_mode(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test getting active positions in LIVE mode."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create mixed positions
        positions = [
            Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2450.00,
                current_price=2475.00,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            ),
            Position(
                symbol_id=sample_symbol.id,
                quantity=5,
                entry_price=2400.00,
                current_price=2450.00,
                is_open=True,
                trading_mode=TradingMode.PAPER,  # Different mode
            ),
            Position(
                symbol_id=sample_symbol.id,
                quantity=8,
                entry_price=2500.00,
                current_price=2450.00,
                is_open=False,  # Closed
                trading_mode=TradingMode.LIVE,
            ),
        ]
        for pos in positions:
            test_async_db_session.add(pos)
        await test_async_db_session.commit()
        
        active_positions = await tracker.get_active_positions(TradingMode.LIVE)
        
        # Should only get open LIVE positions
        assert len(active_positions) == 1
        assert all(p.is_open for p in active_positions)
        assert all(p.trading_mode == TradingMode.LIVE for p in active_positions)
    
    async def test_get_active_positions_empty(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test getting active positions when none exist."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        active_positions = await tracker.get_active_positions()
        
        assert len(active_positions) == 0


# ============================================================================
# Portfolio Summary Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestPortfolioSummary:
    """Test portfolio summary calculations."""
    
    async def test_get_portfolio_summary_with_positions(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test portfolio summary with open positions."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create positions
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
            test_async_db_session.add(pos)
        await test_async_db_session.commit()
        
        summary = await tracker.get_portfolio_summary()
        
        assert summary["num_positions"] == 2
        assert summary["total_investment"] > 0
        assert summary["total_value"] > 0
        assert summary["total_unrealized_pnl"] == pytest.approx(500.0, rel=0.1)
        assert len(summary["positions"]) == 2
    
    async def test_get_portfolio_summary_empty(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test portfolio summary with no positions."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        summary = await tracker.get_portfolio_summary()
        
        assert summary["num_positions"] == 0
        assert summary["total_investment"] == 0.0
        assert summary["total_unrealized_pnl"] == 0.0
        assert len(summary["positions"]) == 0
    
    async def test_get_portfolio_summary_includes_realized_pnl(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test portfolio summary includes realized P&L from closed positions."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create closed positions
        closed_positions = [
            Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2400.00,
                current_price=2500.00,
                realized_pnl=1000.0,
                is_open=False,
                trading_mode=TradingMode.LIVE,
            ),
            Position(
                symbol_id=sample_symbol.id,
                quantity=5,
                entry_price=2450.00,
                current_price=2400.00,
                realized_pnl=-250.0,
                is_open=False,
                trading_mode=TradingMode.LIVE,
            ),
        ]
        for pos in closed_positions:
            test_async_db_session.add(pos)
        await test_async_db_session.commit()
        
        summary = await tracker.get_portfolio_summary()
        
        assert summary["total_realized_pnl"] == pytest.approx(750.0, rel=0.1)
        assert summary["total_pnl"] == pytest.approx(750.0, rel=0.1)


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""
    
    async def test_track_position_with_error(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test tracking handles database errors gracefully."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock an error during price fetch
        with patch.object(tracker, '_get_current_price', side_effect=Exception("API Error")):
            pnl_calc = await tracker.track_position(position.id)
        
        # Should handle error gracefully
        assert pnl_calc is None
    
    async def test_calculate_pnl_with_none_price(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test P&L calculation uses position price if current_price is None."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        position.symbol = sample_symbol
        
        # Calculate without providing current_price
        pnl_calc = await tracker.calculate_pnl(position, current_price=None)
        
        # Should use position.current_price
        assert pnl_calc.current_price == 2475.00
        assert pnl_calc.unrealized_pnl == pytest.approx(250.0, rel=0.01)
