# tests/unit/test_position_reconciler.py
"""
Comprehensive unit tests for the PositionReconciler class.
Tests broker reconciliation, discrepancy detection, and auto-correction.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.position_reconciler import (
    PositionReconciler,
    Discrepancy,
    DiscrepancyType,
    ReconciliationAction,
    ReconciliationResult,
)
from core.position_tracker import BrokerPosition
from data.models import (
    Symbol,
    Position,
    TradingMode,
    Alert,
)


# ============================================================================
# Discrepancy Detection Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestDiscrepancyDetection:
    """Test detection of various discrepancy types."""
    
    async def test_detect_missing_in_database(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test detection of position missing in database."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(session_factory, auto_correct=False)
        
        # No positions in DB, but position exists in broker
        broker_positions = [
            BrokerPosition(
                symbol="RELIANCE",
                quantity=100,
                average_price=2450.00,
                last_price=2475.00,
                pnl=2500.0,
                broker_id="BRK123",
                exchange="NSE",
                product="CNC"
            )
        ]
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            broker_positions,
            TradingMode.LIVE
        )
        
        assert result.success is True
        assert len(result.discrepancies) == 1
        disc = result.discrepancies[0]
        assert disc.type == DiscrepancyType.MISSING_IN_DB
        assert disc.symbol == "RELIANCE"
        assert disc.broker_quantity == 100
        assert disc.recommended_action == ReconciliationAction.CREATE_POSITION
    
    async def test_detect_missing_in_broker(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test detection of position missing in broker."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(session_factory, auto_correct=False)
        
        # Create position in DB
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,
            entry_price=2450.00,
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        
        # No broker positions
        broker_positions = []
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            broker_positions,
            TradingMode.LIVE
        )
        
        assert result.success is True
        assert len(result.discrepancies) == 1
        disc = result.discrepancies[0]
        assert disc.type == DiscrepancyType.MISSING_IN_BROKER
        assert disc.symbol == "RELIANCE"
        assert disc.db_quantity == 100
        assert disc.recommended_action == ReconciliationAction.CLOSE_POSITION
    
    async def test_detect_quantity_mismatch(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test detection of quantity mismatches."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(session_factory, auto_correct=False)
        
        # Create position in DB
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,  # DB has 100
            entry_price=2450.00,
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        
        # Broker has different quantity
        broker_positions = [
            BrokerPosition(
                symbol="RELIANCE",
                quantity=95,  # Broker has 95
                average_price=2450.00,
                last_price=2475.00,
                pnl=2375.0,
                broker_id="BRK123",
                exchange="NSE",
                product="CNC"
            )
        ]
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            broker_positions,
            TradingMode.LIVE
        )
        
        assert result.success is True
        assert len(result.discrepancies) >= 1
        
        # Find quantity mismatch
        qty_disc = next(
            (d for d in result.discrepancies if d.type == DiscrepancyType.QUANTITY_MISMATCH),
            None
        )
        assert qty_disc is not None
        assert qty_disc.db_quantity == 100
        assert qty_disc.broker_quantity == 95
        assert qty_disc.recommended_action == ReconciliationAction.UPDATE_QUANTITY
    
    async def test_detect_price_mismatch(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test detection of price mismatches."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(
            session_factory,
            auto_correct=False
        )
        reconciler.price_tolerance_pct = 1.0  # 1% tolerance
        
        # Create position in DB
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,
            entry_price=2450.00,  # DB price
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        
        # Broker has significantly different price (>1% tolerance)
        broker_positions = [
            BrokerPosition(
                symbol="RELIANCE",
                quantity=100,
                average_price=2500.00,  # Broker price (>2% difference)
                last_price=2475.00,
                pnl=2500.0,
                broker_id="BRK123",
                exchange="NSE",
                product="CNC"
            )
        ]
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            broker_positions,
            TradingMode.LIVE
        )
        
        assert result.success is True
        
        # Find price mismatch
        price_disc = next(
            (d for d in result.discrepancies if d.type == DiscrepancyType.PRICE_MISMATCH),
            None
        )
        assert price_disc is not None
        assert price_disc.db_price == 2450.00
        assert price_disc.broker_price == 2500.00
        assert price_disc.recommended_action == ReconciliationAction.UPDATE_PRICE
    
    async def test_detect_multiple_positions_same_symbol(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test detection of multiple DB positions for same symbol."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(session_factory, auto_correct=False)
        
        # Create multiple positions for same symbol
        positions = [
            Position(
                symbol_id=sample_symbol.id,
                quantity=50,
                entry_price=2400.00,
                current_price=2475.00,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            ),
            Position(
                symbol_id=sample_symbol.id,
                quantity=50,
                entry_price=2450.00,
                current_price=2475.00,
                is_open=True,
                trading_mode=TradingMode.LIVE,
            ),
        ]
        for pos in positions:
            test_async_db_session.add(pos)
        await test_async_db_session.commit()
        
        # Broker has single position
        broker_positions = [
            BrokerPosition(
                symbol="RELIANCE",
                quantity=100,
                average_price=2425.00,
                last_price=2475.00,
                pnl=5000.0,
                broker_id="BRK123",
                exchange="NSE",
                product="CNC"
            )
        ]
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            broker_positions,
            TradingMode.LIVE
        )
        
        assert result.success is True
        
        # Find multiple positions discrepancy
        multi_disc = next(
            (d for d in result.discrepancies if d.type == DiscrepancyType.MULTIPLE_POSITIONS),
            None
        )
        assert multi_disc is not None
        assert multi_disc.symbol == "RELIANCE"
        assert multi_disc.recommended_action == ReconciliationAction.MANUAL_REVIEW


# ============================================================================
# Auto-Correction Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestAutoCorrection:
    """Test automatic correction of discrepancies."""
    
    async def test_auto_correct_price_mismatch(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test auto-correction of price mismatch."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(
            session_factory,
            auto_correct=True
        )
        reconciler.price_tolerance_pct = 1.0
        
        # Create position with different price
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,
            entry_price=2450.00,  # Old price
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Broker has different price
        broker_positions = [
            BrokerPosition(
                symbol="RELIANCE",
                quantity=100,
                average_price=2500.00,  # New price
                last_price=2475.00,
                pnl=2500.0,
                broker_id="BRK123",
                exchange="NSE",
                product="CNC"
            )
        ]
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            broker_positions,
            TradingMode.LIVE
        )
        
        assert result.success is True
        assert result.auto_corrected >= 1
        
        # Check position was updated
        await test_async_db_session.refresh(position)
        assert position.entry_price == 2500.00
    
    async def test_auto_correct_small_quantity_mismatch(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test auto-correction of small quantity mismatch."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(
            session_factory,
            auto_correct=True
        )
        
        # Create position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,  # DB has 100
            entry_price=2450.00,
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        # Broker has slightly different quantity (within auto-correct threshold)
        broker_positions = [
            BrokerPosition(
                symbol="RELIANCE",
                quantity=98,  # Small difference
                average_price=2450.00,
                last_price=2475.00,
                pnl=2450.0,
                broker_id="BRK123",
                exchange="NSE",
                product="CNC"
            )
        ]
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            broker_positions,
            TradingMode.LIVE
        )
        
        assert result.success is True
        assert result.auto_corrected >= 1
        
        # Check quantity was updated
        await test_async_db_session.refresh(position)
        assert position.quantity == 98
    
    async def test_no_auto_correct_large_quantity_mismatch(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test large quantity mismatch requires manual review."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(
            session_factory,
            auto_correct=True
        )
        
        # Create position
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,
            entry_price=2450.00,
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        await test_async_db_session.refresh(position)
        
        original_qty = position.quantity
        
        # Broker has large difference (>5 shares)
        broker_positions = [
            BrokerPosition(
                symbol="RELIANCE",
                quantity=80,  # Large difference
                average_price=2450.00,
                last_price=2475.00,
                pnl=2000.0,
                broker_id="BRK123",
                exchange="NSE",
                product="CNC"
            )
        ]
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            broker_positions,
            TradingMode.LIVE
        )
        
        assert result.success is True
        assert result.manual_review_required >= 1
        
        # Quantity should NOT be auto-corrected
        await test_async_db_session.refresh(position)
        assert position.quantity == original_qty


# ============================================================================
# Audit Log Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestAuditLogging:
    """Test audit log creation."""
    
    async def test_audit_log_created_with_discrepancies(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test audit log is created when discrepancies found."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(
            session_factory,
            auto_correct=False,
            create_audit_logs=True
        )
        
        # No DB positions, but broker has position
        broker_positions = [
            BrokerPosition(
                symbol="RELIANCE",
                quantity=100,
                average_price=2450.00,
                last_price=2475.00,
                pnl=2500.0,
                broker_id="BRK123",
                exchange="NSE",
                product="CNC"
            )
        ]
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            broker_positions,
            TradingMode.LIVE
        )
        
        assert result.success is True
        assert len(result.discrepancies) > 0
        
        # Check audit log was created (Alert with type "reconciliation")
        stmt = select(Alert).where(Alert.type == "reconciliation")
        alerts_result = await test_async_db_session.execute(stmt)
        alerts = alerts_result.scalars().all()
        
        assert len(alerts) >= 1


# ============================================================================
# Reconciliation Result Tests
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestReconciliationResult:
    """Test reconciliation result reporting."""
    
    async def test_reconciliation_summary(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test reconciliation result summary generation."""
        result = ReconciliationResult(
            broker_name="TestBroker",
            timestamp=datetime.utcnow(),
            db_positions_count=10,
            broker_positions_count=12,
            discrepancies=[
                Discrepancy(
                    type=DiscrepancyType.MISSING_IN_DB,
                    symbol="TEST1",
                    broker_quantity=100,
                    severity="high"
                ),
                Discrepancy(
                    type=DiscrepancyType.PRICE_MISMATCH,
                    symbol="TEST2",
                    db_price=100.0,
                    broker_price=102.0,
                    severity="medium"
                ),
            ],
            actions_taken=[
                {"action": "update_price", "details": "Updated TEST2"}
            ],
            auto_corrected=1,
            manual_review_required=1,
            success=True
        )
        
        summary = result.summary()
        
        assert "TestBroker" in summary
        assert "Database Positions: 10" in summary
        assert "Broker Positions: 12" in summary
        assert "Discrepancies Found: 2" in summary
        assert "Auto-corrected: 1" in summary
        assert "Manual review required: 1" in summary
        assert "SUCCESS" in summary
    
    async def test_has_discrepancies_property(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test has_discrepancies property."""
        result_with_disc = ReconciliationResult(
            broker_name="TestBroker",
            timestamp=datetime.utcnow(),
            db_positions_count=10,
            broker_positions_count=10,
            discrepancies=[
                Discrepancy(
                    type=DiscrepancyType.PRICE_MISMATCH,
                    symbol="TEST",
                    severity="medium"
                )
            ],
            actions_taken=[],
            auto_corrected=0,
            manual_review_required=1,
            success=True
        )
        
        result_no_disc = ReconciliationResult(
            broker_name="TestBroker",
            timestamp=datetime.utcnow(),
            db_positions_count=10,
            broker_positions_count=10,
            discrepancies=[],
            actions_taken=[],
            auto_corrected=0,
            manual_review_required=0,
            success=True
        )
        
        assert result_with_disc.has_discrepancies is True
        assert result_no_disc.has_discrepancies is False


# ============================================================================
# Edge Cases
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error handling."""
    
    async def test_reconcile_with_no_positions(
        self,
        test_async_db_session: AsyncSession,
    ):
        """Test reconciliation with no positions in either system."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(session_factory)
        
        result = await reconciler.reconcile_positions(
            "TestBroker",
            [],
            TradingMode.LIVE
        )
        
        assert result.success is True
        assert len(result.discrepancies) == 0
        assert result.db_positions_count == 0
        assert result.broker_positions_count == 0
    
    async def test_reconcile_paper_trading_mode(
        self,
        test_async_db_session: AsyncSession,
        sample_symbol: Symbol,
    ):
        """Test reconciliation filters by trading mode."""
        async def get_session():
            return test_async_db_session
        
        session_factory = lambda: get_session()
        reconciler = PositionReconciler(session_factory)
        
        # Create LIVE position (should not be reconciled in PAPER mode)
        position = Position(
            symbol_id=sample_symbol.id,
            quantity=100,
            entry_price=2450.00,
            current_price=2475.00,
            is_open=True,
            trading_mode=TradingMode.LIVE,  # LIVE mode
        )
        test_async_db_session.add(position)
        await test_async_db_session.commit()
        
        # Reconcile in PAPER mode (should not find LIVE position)
        result = await reconciler.reconcile_positions(
            "TestBroker",
            [],
            TradingMode.PAPER  # PAPER mode
        )
        
        assert result.success is True
        assert result.db_positions_count == 0  # No PAPER positions found
