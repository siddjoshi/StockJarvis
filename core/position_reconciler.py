# core/position_reconciler.py
"""
Position Reconciler - Synchronizes database positions with broker positions.
Detects discrepancies, creates audit logs, and automatically corrects minor issues.
"""

import asyncio
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from core.logger import get_logger
from core.position_tracker import BrokerPosition
from data.models import Position, Symbol, TradingMode, Alert
from config import settings

logger = get_logger(__name__)


class DiscrepancyType(Enum):
    """Types of position discrepancies."""
    MISSING_IN_DB = "missing_in_database"
    MISSING_IN_BROKER = "missing_in_broker"
    QUANTITY_MISMATCH = "quantity_mismatch"
    PRICE_MISMATCH = "price_mismatch"
    MULTIPLE_POSITIONS = "multiple_positions_same_symbol"


class ReconciliationAction(Enum):
    """Actions to resolve discrepancies."""
    CREATE_POSITION = "create_position"
    CLOSE_POSITION = "close_position"
    UPDATE_QUANTITY = "update_quantity"
    UPDATE_PRICE = "update_price"
    MANUAL_REVIEW = "manual_review"
    IGNORE = "ignore"


@dataclass
class Discrepancy:
    """Represents a position discrepancy."""
    
    type: DiscrepancyType
    symbol: str
    db_position_id: Optional[int] = None
    db_quantity: Optional[int] = None
    db_price: Optional[float] = None
    broker_quantity: Optional[int] = None
    broker_price: Optional[float] = None
    broker_id: Optional[str] = None
    severity: str = "medium"  # low, medium, high, critical
    recommended_action: ReconciliationAction = ReconciliationAction.MANUAL_REVIEW
    details: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self) -> str:
        """Human-readable description."""
        if self.type == DiscrepancyType.MISSING_IN_DB:
            return (
                f"Position {self.symbol} exists in broker ({self.broker_quantity} shares) "
                f"but not in database"
            )
        elif self.type == DiscrepancyType.MISSING_IN_BROKER:
            return (
                f"Position {self.symbol} exists in database (ID: {self.db_position_id}, "
                f"{self.db_quantity} shares) but not in broker"
            )
        elif self.type == DiscrepancyType.QUANTITY_MISMATCH:
            return (
                f"Position {self.symbol} (ID: {self.db_position_id}): "
                f"DB quantity {self.db_quantity} != Broker quantity {self.broker_quantity}"
            )
        elif self.type == DiscrepancyType.PRICE_MISMATCH:
            return (
                f"Position {self.symbol} (ID: {self.db_position_id}): "
                f"DB price ${self.db_price:.2f} != Broker price ${self.broker_price:.2f}"
            )
        else:
            return f"Discrepancy in {self.symbol}: {self.type.value}"


@dataclass
class ReconciliationResult:
    """Result of reconciliation process."""
    
    broker_name: str
    timestamp: datetime
    db_positions_count: int
    broker_positions_count: int
    discrepancies: List[Discrepancy]
    actions_taken: List[Dict[str, Any]]
    auto_corrected: int
    manual_review_required: int
    success: bool
    error: Optional[str] = None
    
    @property
    def has_discrepancies(self) -> bool:
        """Check if any discrepancies were found."""
        return len(self.discrepancies) > 0
    
    def summary(self) -> str:
        """Generate summary report."""
        lines = [
            f"=== Reconciliation Report: {self.broker_name} ===",
            f"Timestamp: {self.timestamp}",
            f"Database Positions: {self.db_positions_count}",
            f"Broker Positions: {self.broker_positions_count}",
            f"Discrepancies Found: {len(self.discrepancies)}",
            f"  - Auto-corrected: {self.auto_corrected}",
            f"  - Manual review required: {self.manual_review_required}",
        ]
        
        if self.discrepancies:
            lines.append("\nDiscrepancies:")
            for i, disc in enumerate(self.discrepancies, 1):
                lines.append(f"  {i}. [{disc.severity.upper()}] {disc}")
                lines.append(f"     Recommended: {disc.recommended_action.value}")
        
        if self.actions_taken:
            lines.append(f"\nActions Taken: {len(self.actions_taken)}")
            for action in self.actions_taken:
                lines.append(f"  - {action['action']}: {action['details']}")
        
        lines.append(f"\nStatus: {'SUCCESS' if self.success else 'FAILED'}")
        if self.error:
            lines.append(f"Error: {self.error}")
        
        return "\n".join(lines)


class PositionReconciler:
    """
    Position reconciliation system.
    Compares database positions with broker positions and resolves discrepancies.
    
    Example:
        >>> from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        >>> from sqlalchemy.orm import sessionmaker
        >>> 
        >>> # Create async session
        >>> engine = create_async_engine(settings.db.url.replace("mysql+mysqlconnector", "mysql+aiomysql"))
        >>> async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        >>> 
        >>> # Initialize reconciler
        >>> reconciler = PositionReconciler(async_session)
        >>> 
        >>> # Fetch broker positions (implement based on your broker)
        >>> broker_positions = await get_zerodha_positions()
        >>> 
        >>> # Reconcile
        >>> result = await reconciler.reconcile_positions("Zerodha", broker_positions)
        >>> print(result.summary())
    """
    
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        auto_correct: bool = True,
        create_audit_logs: bool = True
    ):
        """
        Initialize position reconciler.
        
        Args:
            session_factory: AsyncSession factory for database operations
            auto_correct: Automatically correct minor discrepancies
            create_audit_logs: Create audit logs for all discrepancies
        """
        self.session_factory = session_factory
        self.auto_correct = auto_correct
        self.create_audit_logs = create_audit_logs
        self.logger = get_logger(__name__)
        
        # Configuration
        self.quantity_tolerance = 0  # No tolerance for quantity mismatches
        self.price_tolerance_pct = 2.0  # 2% tolerance for price mismatches
        
        self.logger.info(
            f"PositionReconciler initialized (auto_correct={auto_correct}, "
            f"audit_logs={create_audit_logs})"
        )
    
    async def reconcile_positions(
        self,
        broker_name: str,
        broker_positions: List[BrokerPosition],
        trading_mode: TradingMode = TradingMode.LIVE
    ) -> ReconciliationResult:
        """
        Reconcile database positions with broker positions.
        
        Args:
            broker_name: Name of the broker (e.g., "Zerodha")
            broker_positions: List of positions from broker
            trading_mode: Trading mode to reconcile (LIVE or PAPER)
        
        Returns:
            ReconciliationResult with detailed report
        
        Example:
            >>> broker_positions = [
            >>>     BrokerPosition(
            >>>         symbol="RELIANCE",
            >>>         quantity=100,
            >>>         average_price=2450.50,
            >>>         last_price=2475.00,
            >>>         pnl=2450.0,
            >>>         broker_id="12345",
            >>>         exchange="NSE",
            >>>         product="CNC"
            >>>     ),
            >>>     # ... more positions
            >>> ]
            >>> result = await reconciler.reconcile_positions("Zerodha", broker_positions)
            >>> 
            >>> if result.has_discrepancies:
            >>>     print(result.summary())
            >>>     # Send alert
        """
        self.logger.info(
            f"Starting reconciliation with {broker_name} "
            f"({len(broker_positions)} broker positions)"
        )
        
        timestamp = datetime.utcnow()
        discrepancies: List[Discrepancy] = []
        actions_taken: List[Dict[str, Any]] = []
        auto_corrected = 0
        manual_review_required = 0
        
        async with self.session_factory() as session:
            try:
                # Fetch all open positions from database
                result = await session.execute(
                    select(Position)
                    .options(selectinload(Position.symbol))
                    .where(
                        Position.is_open == True,
                        Position.trading_mode == trading_mode
                    )
                )
                db_positions = result.scalars().all()
                
                self.logger.info(f"Found {len(db_positions)} open positions in database")
                
                # Create lookup dictionaries
                db_by_symbol: Dict[str, List[Position]] = {}
                for pos in db_positions:
                    symbol = pos.symbol.symbol
                    if symbol not in db_by_symbol:
                        db_by_symbol[symbol] = []
                    db_by_symbol[symbol].append(pos)
                
                broker_by_symbol: Dict[str, BrokerPosition] = {
                    bp.symbol: bp for bp in broker_positions
                }
                
                # Get all symbols from both sources
                all_symbols = set(db_by_symbol.keys()) | set(broker_by_symbol.keys())
                
                self.logger.debug(f"Comparing {len(all_symbols)} unique symbols")
                
                # Compare positions
                for symbol in sorted(all_symbols):
                    db_pos_list = db_by_symbol.get(symbol, [])
                    broker_pos = broker_by_symbol.get(symbol)
                    
                    # Detect discrepancies
                    symbol_discrepancies = await self._compare_symbol_positions(
                        symbol, db_pos_list, broker_pos, session
                    )
                    
                    discrepancies.extend(symbol_discrepancies)
                    
                    # Auto-correct if enabled
                    if self.auto_correct:
                        for disc in symbol_discrepancies:
                            action = await self._resolve_discrepancy(
                                disc, session, broker_name
                            )
                            if action:
                                actions_taken.append(action)
                                if action.get("auto_corrected", False):
                                    auto_corrected += 1
                                else:
                                    manual_review_required += 1
                
                # Commit changes
                if self.auto_correct:
                    await session.commit()
                    self.logger.info(f"Auto-corrected {auto_corrected} discrepancies")
                
                # Create audit log
                if self.create_audit_logs and discrepancies:
                    await self._create_audit_log(
                        session, broker_name, discrepancies, actions_taken
                    )
                    await session.commit()
                
                # Count manual reviews needed
                manual_review_required = sum(
                    1 for d in discrepancies
                    if d.recommended_action == ReconciliationAction.MANUAL_REVIEW
                    and not any(a.get("discrepancy_id") == id(d) for a in actions_taken)
                )
                
                result = ReconciliationResult(
                    broker_name=broker_name,
                    timestamp=timestamp,
                    db_positions_count=len(db_positions),
                    broker_positions_count=len(broker_positions),
                    discrepancies=discrepancies,
                    actions_taken=actions_taken,
                    auto_corrected=auto_corrected,
                    manual_review_required=manual_review_required,
                    success=True
                )
                
                self.logger.info(
                    f"Reconciliation complete: {len(discrepancies)} discrepancies, "
                    f"{auto_corrected} auto-corrected, {manual_review_required} need review"
                )
                
                return result
                
            except Exception as e:
                self.logger.error(f"Error during reconciliation: {e}", exc_info=True)
                await session.rollback()
                
                return ReconciliationResult(
                    broker_name=broker_name,
                    timestamp=timestamp,
                    db_positions_count=len(db_positions) if 'db_positions' in locals() else 0,
                    broker_positions_count=len(broker_positions),
                    discrepancies=[],
                    actions_taken=[],
                    auto_corrected=0,
                    manual_review_required=0,
                    success=False,
                    error=str(e)
                )
    
    async def _compare_symbol_positions(
        self,
        symbol: str,
        db_positions: List[Position],
        broker_position: Optional[BrokerPosition],
        session: AsyncSession
    ) -> List[Discrepancy]:
        """
        Compare positions for a single symbol.
        
        Args:
            symbol: Stock symbol
            db_positions: List of database positions for this symbol
            broker_position: Broker position for this symbol (if any)
            session: Database session
        
        Returns:
            List of discrepancies found
        """
        discrepancies: List[Discrepancy] = []
        
        # Case 1: Position exists in broker but not in database
        if broker_position and not db_positions:
            disc = Discrepancy(
                type=DiscrepancyType.MISSING_IN_DB,
                symbol=symbol,
                broker_quantity=broker_position.quantity,
                broker_price=broker_position.average_price,
                broker_id=broker_position.broker_id,
                severity="high",
                recommended_action=ReconciliationAction.CREATE_POSITION,
                details={
                    "broker_exchange": broker_position.exchange,
                    "broker_product": broker_position.product,
                    "broker_pnl": broker_position.pnl
                }
            )
            discrepancies.append(disc)
            self.logger.warning(f"Position missing in DB: {disc}")
        
        # Case 2: Position exists in database but not in broker
        elif db_positions and not broker_position:
            for db_pos in db_positions:
                disc = Discrepancy(
                    type=DiscrepancyType.MISSING_IN_BROKER,
                    symbol=symbol,
                    db_position_id=db_pos.id,
                    db_quantity=db_pos.quantity,
                    db_price=db_pos.entry_price,
                    severity="high",
                    recommended_action=ReconciliationAction.CLOSE_POSITION,
                    details={
                        "db_entry_time": db_pos.entry_time.isoformat(),
                        "db_unrealized_pnl": db_pos.unrealized_pnl
                    }
                )
                discrepancies.append(disc)
                self.logger.warning(f"Position missing in broker: {disc}")
        
        # Case 3: Position exists in both - check for mismatches
        elif db_positions and broker_position:
            # Check for multiple DB positions for same symbol
            if len(db_positions) > 1:
                disc = Discrepancy(
                    type=DiscrepancyType.MULTIPLE_POSITIONS,
                    symbol=symbol,
                    severity="medium",
                    recommended_action=ReconciliationAction.MANUAL_REVIEW,
                    details={
                        "db_position_ids": [p.id for p in db_positions],
                        "db_quantities": [p.quantity for p in db_positions],
                        "total_db_quantity": sum(p.quantity for p in db_positions),
                        "broker_quantity": broker_position.quantity
                    }
                )
                discrepancies.append(disc)
                self.logger.warning(f"Multiple DB positions for same symbol: {disc}")
            
            # Compare single position (or first if multiple)
            db_pos = db_positions[0]
            
            # Check quantity mismatch
            if db_pos.quantity != broker_position.quantity:
                disc = Discrepancy(
                    type=DiscrepancyType.QUANTITY_MISMATCH,
                    symbol=symbol,
                    db_position_id=db_pos.id,
                    db_quantity=db_pos.quantity,
                    db_price=db_pos.entry_price,
                    broker_quantity=broker_position.quantity,
                    broker_price=broker_position.average_price,
                    broker_id=broker_position.broker_id,
                    severity="high",
                    recommended_action=ReconciliationAction.UPDATE_QUANTITY,
                    details={
                        "quantity_diff": broker_position.quantity - db_pos.quantity
                    }
                )
                discrepancies.append(disc)
                self.logger.warning(f"Quantity mismatch: {disc}")
            
            # Check price mismatch (with tolerance)
            price_diff_pct = abs(
                (db_pos.entry_price - broker_position.average_price) / broker_position.average_price
            ) * 100.0
            
            if price_diff_pct > self.price_tolerance_pct:
                disc = Discrepancy(
                    type=DiscrepancyType.PRICE_MISMATCH,
                    symbol=symbol,
                    db_position_id=db_pos.id,
                    db_quantity=db_pos.quantity,
                    db_price=db_pos.entry_price,
                    broker_quantity=broker_position.quantity,
                    broker_price=broker_position.average_price,
                    broker_id=broker_position.broker_id,
                    severity="medium",
                    recommended_action=ReconciliationAction.UPDATE_PRICE,
                    details={
                        "price_diff_pct": price_diff_pct,
                        "tolerance_pct": self.price_tolerance_pct
                    }
                )
                discrepancies.append(disc)
                self.logger.warning(f"Price mismatch: {disc}")
        
        return discrepancies
    
    async def _resolve_discrepancy(
        self,
        discrepancy: Discrepancy,
        session: AsyncSession,
        broker_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Attempt to automatically resolve a discrepancy.
        
        Args:
            discrepancy: Discrepancy to resolve
            session: Database session
            broker_name: Broker name
        
        Returns:
            Action details if action was taken, None otherwise
        """
        action = None
        
        try:
            # Only auto-correct certain types
            if discrepancy.recommended_action == ReconciliationAction.UPDATE_PRICE:
                # Update price
                result = await session.execute(
                    select(Position).where(Position.id == discrepancy.db_position_id)
                )
                position = result.scalar_one_or_none()
                
                if position:
                    old_price = position.entry_price
                    position.entry_price = discrepancy.broker_price
                    position.updated_at = datetime.utcnow()
                    
                    action = {
                        "action": "update_price",
                        "discrepancy_id": id(discrepancy),
                        "position_id": position.id,
                        "symbol": discrepancy.symbol,
                        "old_price": old_price,
                        "new_price": discrepancy.broker_price,
                        "auto_corrected": True,
                        "details": f"Updated price from ${old_price:.2f} to ${discrepancy.broker_price:.2f}"
                    }
                    
                    self.logger.info(f"Auto-corrected price: {action['details']}")
            
            elif discrepancy.recommended_action == ReconciliationAction.UPDATE_QUANTITY:
                # Update quantity (only if difference is small)
                qty_diff = abs(discrepancy.broker_quantity - discrepancy.db_quantity)
                
                if qty_diff <= 5:  # Allow auto-correction for small differences
                    result = await session.execute(
                        select(Position).where(Position.id == discrepancy.db_position_id)
                    )
                    position = result.scalar_one_or_none()
                    
                    if position:
                        old_qty = position.quantity
                        position.quantity = discrepancy.broker_quantity
                        position.updated_at = datetime.utcnow()
                        
                        action = {
                            "action": "update_quantity",
                            "discrepancy_id": id(discrepancy),
                            "position_id": position.id,
                            "symbol": discrepancy.symbol,
                            "old_quantity": old_qty,
                            "new_quantity": discrepancy.broker_quantity,
                            "auto_corrected": True,
                            "details": f"Updated quantity from {old_qty} to {discrepancy.broker_quantity}"
                        }
                        
                        self.logger.info(f"Auto-corrected quantity: {action['details']}")
                else:
                    action = {
                        "action": "manual_review",
                        "discrepancy_id": id(discrepancy),
                        "symbol": discrepancy.symbol,
                        "auto_corrected": False,
                        "details": f"Quantity difference {qty_diff} too large for auto-correction"
                    }
            
            else:
                # Requires manual review
                action = {
                    "action": "manual_review",
                    "discrepancy_id": id(discrepancy),
                    "discrepancy_type": discrepancy.type.value,
                    "symbol": discrepancy.symbol,
                    "auto_corrected": False,
                    "details": str(discrepancy)
                }
        
        except Exception as e:
            self.logger.error(
                f"Error resolving discrepancy for {discrepancy.symbol}: {e}",
                exc_info=True
            )
            action = {
                "action": "error",
                "discrepancy_id": id(discrepancy),
                "symbol": discrepancy.symbol,
                "auto_corrected": False,
                "details": f"Error: {str(e)}"
            }
        
        return action
    
    async def _create_audit_log(
        self,
        session: AsyncSession,
        broker_name: str,
        discrepancies: List[Discrepancy],
        actions: List[Dict[str, Any]]
    ):
        """
        Create audit log for reconciliation.
        
        Args:
            session: Database session
            broker_name: Broker name
            discrepancies: List of discrepancies
            actions: List of actions taken
        """
        try:
            # Create alert/audit log
            summary = f"Position reconciliation with {broker_name} found {len(discrepancies)} discrepancies"
            
            details = {
                "broker": broker_name,
                "timestamp": datetime.utcnow().isoformat(),
                "discrepancies_count": len(discrepancies),
                "actions_count": len(actions),
                "auto_corrected": sum(1 for a in actions if a.get("auto_corrected", False)),
                "discrepancies": [
                    {
                        "type": d.type.value,
                        "symbol": d.symbol,
                        "severity": d.severity,
                        "details": str(d)
                    }
                    for d in discrepancies
                ],
                "actions": actions
            }
            
            import json
            
            alert = Alert(
                type="reconciliation",
                title=f"Position Reconciliation - {broker_name}",
                message=summary,
                metadata=json.dumps(details),
                email_sent=False,
                sms_sent=False
            )
            
            session.add(alert)
            
            self.logger.info(f"Created audit log for reconciliation")
            
        except Exception as e:
            self.logger.error(f"Error creating audit log: {e}", exc_info=True)
