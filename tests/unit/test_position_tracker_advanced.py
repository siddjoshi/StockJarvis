# tests/unit/test_position_tracker_advanced.py
"""
Advanced unit tests for PositionTracker.
Tests concurrent updates, race conditions, error handling, and edge cases.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.position_tracker import (
    PositionTracker,
    PnLCalculation,
    BrokerPosition,
)
from data.models import (
    Symbol,
    Position,
    TradingMode,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_price_fetch(request):
    """
    Helper fixture to mock _get_current_price consistently across tests.
    Usage: Just pass the price you want to return.
    """
    def _mock(tracker, price=2475.00):
        return patch.object(tracker, '_get_current_price', return_value=price)
    return _mock


# ============================================================================
# Concurrent Operations Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestConcurrentOperations:
    """Test concurrent position updates."""
    
    async def test_concurrent_position_tracking(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
        mock_price_fetch,
    ):
        """Test tracking multiple positions concurrently."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create multiple positions
        positions = []
        for i in range(5):
            pos = Position(
                symbol_id=sample_symbol.id,
                quantity=10 + i,
                entry_price=2400.00 + (i * 10),
                current_price=2450.00,
                is_open=True,
                trading_mode=TradingMode.PAPER,
            )
            test_async_db_session.add(pos)
        
        await test_async_db_session.commit()
        
        # Get position IDs
        from sqlalchemy import select
        result = await test_async_db_session.execute(
            select(Position).where(Position.is_open == True)
        )
        positions = result.scalars().all()
        position_ids = [p.id for p in positions]
        
        # Mock price fetching using helper
        with mock_price_fetch(tracker, 2475.00):
            # Track all positions concurrently
            tasks = [tracker.track_position(pid) for pid in position_ids]
            results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(r is not None for r in results)
        assert len(results) == 5
    
    async def test_race_condition_pnl_calculation(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test P&L calculation under race conditions."""
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
            trading_mode=TradingMode.PAPER,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock different prices for concurrent calculations
        prices = [2460.00, 2470.00, 2480.00]
        
        async def track_with_price(price):
            with patch.object(tracker, '_get_current_price', return_value=price):
                return await tracker.track_position(position.id)
        
        # Calculate P&L concurrently with different prices
        tasks = [track_with_price(p) for p in prices]
        results = await asyncio.gather(*tasks)
        
        # All calculations should succeed
        assert all(r is not None for r in results)
        
        # P&L should reflect different prices
        pnls = [r.unrealized_pnl for r in results]
        assert len(set(pnls)) == len(prices)  # All different
    
    async def test_concurrent_broker_updates(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test concurrent broker updates to same position."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,
            entry_price=2450.00,
            current_price=2450.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Create multiple broker updates
        broker_data_list = [
            BrokerPosition(
                symbol="RELIANCE",
                quantity=100,
                average_price=2450.00,
                last_price=2460.00 + i,
                pnl=1000.0,
                broker_id="BRK123",
                exchange="NSE",
                product="CNC"
            )
            for i in range(3)
        ]
        
        # Update concurrently
        tasks = [
            tracker.update_position_from_broker(position.id, bd)
            for bd in broker_data_list
        ]
        results = await asyncio.gather(*tasks)
        
        # All updates should succeed
        assert all(r is True for r in results)
        
        # Final price should be from one of the updates
        await test_async_db_session.refresh(position)
        assert position.current_price in [2460.00, 2461.00, 2462.00]


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in various scenarios."""
    
    async def test_handle_database_error_gracefully(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test handling of database errors."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Try to track non-existent position
        result = await tracker.track_position(999999)
        
        # Should return None, not raise exception
        assert result is None
    
    async def test_handle_price_fetch_error(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test handling of price fetching errors."""
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
            trading_mode=TradingMode.PAPER,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock price fetch to fail
        with patch.object(
            tracker,
            '_get_current_price',
            side_effect=Exception("API Error")
        ):
            result = await tracker.track_position(position.id)
        
        # Should handle error gracefully
        assert result is None
    
    async def test_handle_invalid_broker_data(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test handling of invalid broker data."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,
            entry_price=2450.00,
            current_price=2450.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Create broker data with wrong symbol
        broker_data = BrokerPosition(
            symbol="WRONG_SYMBOL",
            quantity=100,
            average_price=2450.00,
            last_price=2475.00,
            pnl=2500.0,
            broker_id="BRK123",
            exchange="NSE",
            product="CNC"
        )
        
        # Should fail but not crash
        result = await tracker.update_position_from_broker(position.id, broker_data)
        assert result is False


# ============================================================================
# Stale Data Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestStaleDataHandling:
    """Test handling of stale price data."""
    
    async def test_detect_stale_price_data(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test detection of stale price data."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create position with old update timestamp
        old_time = datetime.utcnow() - timedelta(hours=2)
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=10,
            entry_price=2450.00,
            current_price=2475.00,
            updated_at=old_time,
            is_open=True,
            trading_mode=TradingMode.PAPER,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Check last update time - should not be in cache yet
        assert position.id not in tracker._last_update
        
        # Track position (should update timestamp)
        with patch.object(tracker, '_get_current_price', return_value=2480.00):
            await tracker.track_position(position.id)
        
        # Check timestamp was updated
        await test_async_db_session.refresh(position)
        assert position.updated_at > old_time
    
    async def test_handle_missing_price_data(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test handling when price data is missing."""
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
            trading_mode=TradingMode.PAPER,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Mock price fetch returning 0.0 (no data)
        with patch.object(tracker, '_get_current_price', return_value=0.0):
            result = await tracker.track_position(position.id)
        
        # Should still return result with 0 price
        assert result is not None
        assert result.current_price == 0.0


# ============================================================================
# Monitoring Loop Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestMonitoringLoop:
    """Test position monitoring loop."""
    
    async def test_start_stop_monitoring_loop(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test starting and stopping monitoring loop."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Start monitoring
        await tracker.start_monitoring()
        assert tracker.monitoring is True
        assert tracker.monitoring_task is not None
        
        # Stop monitoring
        await tracker.stop_monitoring()
        assert tracker.monitoring is False
    
    async def test_monitoring_loop_handles_errors(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test monitoring loop handles errors without crashing."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        tracker.update_interval = 1  # Fast interval for testing
        
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
        
        # Mock track_position to fail occasionally
        call_count = [0]
        
        async def mock_track(pid):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Simulated error")
            return None
        
        with patch.object(tracker, 'track_position', side_effect=mock_track):
            # Start monitoring
            await tracker.start_monitoring()
            
            # Let it run and hit the error
            await asyncio.sleep(3)
            
            # Stop monitoring
            await tracker.stop_monitoring()
        
        # Should have survived the error
        assert call_count[0] >= 2
    
    async def test_monitoring_updates_cache(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test monitoring updates position cache."""
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
        
        # Track position
        with patch.object(tracker, '_get_current_price', return_value=2475.00):
            await tracker.track_position(position.id)
        
        # Check cache
        assert position.id in tracker._position_cache
        assert position.id in tracker._last_update


# ============================================================================
# Portfolio Summary Edge Cases
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestPortfolioSummaryEdgeCases:
    """Test portfolio summary edge cases."""
    
    async def test_portfolio_summary_with_mixed_positions(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test portfolio summary with long and short positions."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create mixed positions
        positions = [
            Position(
                symbol_id=sample_symbol.id,
                quantity=10,  # Long
                entry_price=2450.00,
                current_price=2475.00,
                unrealized_pnl=250.0,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            ),
            Position(
                symbol_id=sample_symbol.id,
                quantity=-5,  # Short
                entry_price=2500.00,
                current_price=2475.00,
                unrealized_pnl=125.0,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            ),
        ]
        for pos in positions:
            test_async_db_session.add(pos)
        await test_async_db_session.commit()
        
        summary = await tracker.get_portfolio_summary()
        
        assert summary["num_positions"] == 2
        assert summary["total_unrealized_pnl"] == pytest.approx(375.0, rel=0.1)
    
    async def test_portfolio_summary_calculation_accuracy(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test accuracy of portfolio summary calculations."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create position with known values
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,
            entry_price=2450.00,
            current_price=2475.00,
            unrealized_pnl=2500.0,  # (2475-2450) * 100
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        
        summary = await tracker.get_portfolio_summary()
        
        # Verify calculations
        expected_investment = 2450.00 * 100
        expected_value = 2475.00 * 100
        
        assert summary["total_investment"] == pytest.approx(expected_investment, rel=0.01)
        assert summary["total_value"] == pytest.approx(expected_value, rel=0.01)
        assert summary["total_unrealized_pnl"] == pytest.approx(2500.0, rel=0.01)


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestPerformance:
    """Test performance with many positions."""
    
    async def test_track_many_positions_efficiently(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test tracking many positions completes in reasonable time."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create many positions
        num_positions = 50
        positions = []
        for i in range(num_positions):
            pos = Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2400.00 + i,
                current_price=2450.00,
                is_open=True,
                trading_mode=TradingMode.PAPER,
            )
            test_async_db_session.add(pos)
        
        await test_async_db_session.commit()
        
        # Get position IDs
        from sqlalchemy import select
        result = await test_async_db_session.execute(
            select(Position).where(Position.is_open == True)
        )
        all_positions = result.scalars().all()
        
        # Track all positions
        start_time = datetime.utcnow()
        
        with patch.object(tracker, '_get_current_price', return_value=2475.00):
            for pos in all_positions:
                await tracker.track_position(pos.id)
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        # Should complete reasonably fast (< 10 seconds for 50 positions)
        assert elapsed < 10.0
    
    async def test_portfolio_summary_with_many_positions(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test portfolio summary with many positions."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        tracker = PositionTracker(session_factory)
        
        # Create many positions
        for i in range(20):
            pos = Position(
                symbol_id=sample_symbol.id,
                quantity=10,
                entry_price=2400.00 + (i * 5),
                current_price=2450.00,
                unrealized_pnl=100.0 + (i * 10),
                is_open=True,
                trading_mode=TradingMode.LIVE,
            )
            test_async_db_session.add(pos)
        
        await test_async_db_session.commit()
        
        # Get summary
        start_time = datetime.utcnow()
        summary = await tracker.get_portfolio_summary()
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        
        # Should complete fast
        assert elapsed < 5.0
        assert summary["num_positions"] == 20
