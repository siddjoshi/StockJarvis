# core/position_tracker.py
"""
Position Tracker - Real-time position monitoring and management.
Tracks all open positions, updates P&L, monitors stop losses, and integrates with brokers.
"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import selectinload

from core.logger import get_logger
from core.risk_manager import RiskManager
from core.stop_loss_manager import StopLossManager
from data.models import Position, Symbol, OrderAction, TradingMode, Order, OrderStatus
from config import settings

logger = get_logger(__name__)


@dataclass
class PnLCalculation:
    """Result of P&L calculation."""
    
    position_id: int
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    position_value: float
    total_investment: float
    stop_loss: Optional[float]
    target: Optional[float]
    distance_to_stop_pct: float
    distance_to_target_pct: float


@dataclass
class BrokerPosition:
    """Position data from broker."""
    
    symbol: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    broker_id: str  # Broker's position ID
    exchange: str
    product: str  # MIS, CNC, NRML etc.


class PositionTracker:
    """
    Main position tracking system.
    Monitors all open positions in real-time, calculates P&L, and manages position lifecycle.
    
    Example:
        >>> from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        >>> from sqlalchemy.orm import sessionmaker
        >>> 
        >>> # Create async session
        >>> engine = create_async_engine(settings.db.url.replace("mysql+mysqlconnector", "mysql+aiomysql"))
        >>> async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        >>> 
        >>> # Initialize tracker
        >>> tracker = PositionTracker(async_session)
        >>> 
        >>> # Track specific position
        >>> await tracker.track_position(position_id=123)
        >>> 
        >>> # Get all active positions
        >>> positions = await tracker.get_active_positions()
        >>> 
        >>> # Start monitoring loop
        >>> await tracker.start_monitoring()
    """
    
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        """
        Initialize position tracker.
        
        Args:
            session_factory: AsyncSession factory for database operations
        """
        self.session_factory = session_factory
        self.logger = get_logger(__name__)
        self.stop_loss_manager = StopLossManager()
        
        # Monitoring state
        self.monitoring = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.update_interval = 60  # seconds
        
        # Cache for performance
        self._position_cache: Dict[int, Position] = {}
        self._last_update: Dict[int, datetime] = {}
        
        self.logger.info("PositionTracker initialized")
    
    async def track_position(self, position_id: int) -> Optional[PnLCalculation]:
        """
        Track a specific position and calculate current P&L.
        
        Args:
            position_id: Position ID to track
        
        Returns:
            PnLCalculation with current metrics, or None if position not found
        
        Example:
            >>> pnl = await tracker.track_position(123)
            >>> if pnl:
            >>>     print(f"Position {pnl.symbol}: P&L = ${pnl.unrealized_pnl:.2f} ({pnl.unrealized_pnl_pct:.2f}%)")
        """
        async with self.session_factory() as session:
            try:
                # Fetch position with symbol relationship
                result = await session.execute(
                    select(Position)
                    .options(selectinload(Position.symbol))
                    .where(Position.id == position_id)
                )
                position = result.scalar_one_or_none()
                
                if not position:
                    self.logger.warning(f"Position {position_id} not found")
                    return None
                
                if not position.is_open:
                    self.logger.debug(f"Position {position_id} is closed, skipping tracking")
                    return None
                
                # Get current price (in production, fetch from market data service)
                current_price = await self._get_current_price(position.symbol.symbol, session)
                
                # Calculate P&L
                pnl_calc = await self.calculate_pnl(position, current_price)
                
                # Update position in database
                position.current_price = current_price
                position.unrealized_pnl = pnl_calc.unrealized_pnl
                position.updated_at = datetime.utcnow()
                
                await session.commit()
                
                # Update cache
                self._position_cache[position_id] = position
                self._last_update[position_id] = datetime.utcnow()
                
                self.logger.debug(
                    f"Tracked position {position_id} ({position.symbol.symbol}): "
                    f"P&L = ${pnl_calc.unrealized_pnl:.2f} ({pnl_calc.unrealized_pnl_pct:.2f}%)"
                )
                
                return pnl_calc
                
            except Exception as e:
                self.logger.error(f"Error tracking position {position_id}: {e}", exc_info=True)
                await session.rollback()
                return None
    
    async def calculate_pnl(
        self,
        position: Position,
        current_price: Optional[float] = None
    ) -> PnLCalculation:
        """
        Calculate P&L for a position.
        
        Args:
            position: Position model instance
            current_price: Current market price (uses position.current_price if None)
        
        Returns:
            PnLCalculation with detailed P&L metrics
        
        Example:
            >>> pnl = await tracker.calculate_pnl(position, current_price=150.50)
            >>> print(f"Unrealized P&L: ${pnl.unrealized_pnl:.2f}")
            >>> print(f"Distance to stop: {pnl.distance_to_stop_pct:.2f}%")
        """
        current_price = current_price or position.current_price
        
        # Calculate unrealized P&L
        if position.quantity > 0:  # Long position
            unrealized_pnl = (current_price - position.entry_price) * position.quantity
        else:  # Short position
            unrealized_pnl = (position.entry_price - current_price) * abs(position.quantity)
        
        # Calculate percentages
        total_investment = abs(position.entry_price * position.quantity)
        unrealized_pnl_pct = (unrealized_pnl / total_investment) * 100.0 if total_investment > 0 else 0.0
        
        # Calculate position value
        position_value = abs(current_price * position.quantity)
        
        # Calculate distances to stop and target
        distance_to_stop_pct = 0.0
        distance_to_target_pct = 0.0
        
        if position.stop_loss:
            distance_to_stop_pct = abs((current_price - position.stop_loss) / current_price) * 100.0
        
        if position.target:
            distance_to_target_pct = abs((position.target - current_price) / current_price) * 100.0
        
        return PnLCalculation(
            position_id=position.id,
            symbol=position.symbol.symbol,
            quantity=position.quantity,
            entry_price=position.entry_price,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            position_value=position_value,
            total_investment=total_investment,
            stop_loss=position.stop_loss,
            target=position.target,
            distance_to_stop_pct=distance_to_stop_pct,
            distance_to_target_pct=distance_to_target_pct
        )
    
    async def get_active_positions(
        self,
        trading_mode: TradingMode = TradingMode.LIVE
    ) -> List[Position]:
        """
        Get all active (open) positions.
        
        Args:
            trading_mode: Filter by trading mode (LIVE or PAPER)
        
        Returns:
            List of active Position objects
        
        Example:
            >>> positions = await tracker.get_active_positions(TradingMode.LIVE)
            >>> for pos in positions:
            >>>     print(f"{pos.symbol.symbol}: {pos.quantity} @ ${pos.entry_price:.2f}")
        """
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Position)
                    .options(selectinload(Position.symbol))
                    .where(
                        Position.is_open == True,
                        Position.trading_mode == trading_mode
                    )
                    .order_by(Position.entry_time.desc())
                )
                positions = result.scalars().all()
                
                self.logger.info(
                    f"Retrieved {len(positions)} active positions for {trading_mode.value} mode"
                )
                
                return list(positions)
                
            except Exception as e:
                self.logger.error(f"Error fetching active positions: {e}", exc_info=True)
                return []
    
    async def update_position_from_broker(
        self,
        position_id: int,
        broker_data: BrokerPosition
    ) -> bool:
        """
        Update position with data from broker.
        Used for reconciliation and real-time updates.
        
        Args:
            position_id: Position ID in database
            broker_data: Position data from broker
        
        Returns:
            True if update successful, False otherwise
        
        Example:
            >>> broker_pos = BrokerPosition(
            >>>     symbol="RELIANCE",
            >>>     quantity=100,
            >>>     average_price=2450.50,
            >>>     last_price=2475.00,
            >>>     pnl=2450.0,
            >>>     broker_id="12345",
            >>>     exchange="NSE",
            >>>     product="CNC"
            >>> )
            >>> success = await tracker.update_position_from_broker(123, broker_pos)
        """
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Position)
                    .options(selectinload(Position.symbol))
                    .where(Position.id == position_id)
                )
                position = result.scalar_one_or_none()
                
                if not position:
                    self.logger.error(f"Position {position_id} not found for broker update")
                    return False
                
                # Validate symbol match
                if position.symbol.symbol != broker_data.symbol:
                    self.logger.error(
                        f"Symbol mismatch: DB={position.symbol.symbol}, Broker={broker_data.symbol}"
                    )
                    return False
                
                # Update fields
                old_price = position.current_price
                position.current_price = broker_data.last_price
                position.updated_at = datetime.utcnow()
                
                # Recalculate P&L
                pnl_calc = await self.calculate_pnl(position, broker_data.last_price)
                position.unrealized_pnl = pnl_calc.unrealized_pnl
                
                await session.commit()
                
                self.logger.info(
                    f"Updated position {position_id} from broker: "
                    f"Price ${old_price:.2f} -> ${broker_data.last_price:.2f}, "
                    f"P&L ${pnl_calc.unrealized_pnl:.2f}"
                )
                
                return True
                
            except Exception as e:
                self.logger.error(
                    f"Error updating position {position_id} from broker: {e}",
                    exc_info=True
                )
                await session.rollback()
                return False
    
    async def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_reason: str = "manual"
    ) -> bool:
        """
        Close a position and calculate realized P&L.
        
        Args:
            position_id: Position ID to close
            exit_price: Exit price
            exit_reason: Reason for exit (manual, stop_loss, target, etc.)
        
        Returns:
            True if closed successfully
        
        Example:
            >>> success = await tracker.close_position(
            >>>     position_id=123,
            >>>     exit_price=2500.00,
            >>>     exit_reason="target_hit"
            >>> )
        """
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Position)
                    .options(selectinload(Position.symbol))
                    .where(Position.id == position_id)
                )
                position = result.scalar_one_or_none()
                
                if not position:
                    self.logger.error(f"Position {position_id} not found")
                    return False
                
                if not position.is_open:
                    self.logger.warning(f"Position {position_id} is already closed")
                    return False
                
                # Calculate realized P&L
                if position.quantity > 0:  # Long position
                    realized_pnl = (exit_price - position.entry_price) * position.quantity
                else:  # Short position
                    realized_pnl = (position.entry_price - exit_price) * abs(position.quantity)
                
                # Update position
                position.is_open = False
                position.current_price = exit_price
                position.realized_pnl = realized_pnl
                position.unrealized_pnl = 0.0
                position.exit_time = datetime.utcnow()
                position.updated_at = datetime.utcnow()
                
                await session.commit()
                
                # Remove from cache
                self._position_cache.pop(position_id, None)
                self._last_update.pop(position_id, None)
                
                # Remove trailing stop if exists
                self.stop_loss_manager.remove_trailing_stop(position_id)
                
                self.logger.info(
                    f"Closed position {position_id} ({position.symbol.symbol}): "
                    f"Entry ${position.entry_price:.2f}, Exit ${exit_price:.2f}, "
                    f"Realized P&L: ${realized_pnl:.2f}, Reason: {exit_reason}"
                )
                
                return True
                
            except Exception as e:
                self.logger.error(f"Error closing position {position_id}: {e}", exc_info=True)
                await session.rollback()
                return False
    
    async def start_monitoring(self):
        """
        Start background monitoring loop.
        Updates all active positions every 60 seconds.
        
        Example:
            >>> await tracker.start_monitoring()
            >>> # Monitoring runs in background
            >>> await asyncio.sleep(300)  # Let it run
            >>> await tracker.stop_monitoring()
        """
        if self.monitoring:
            self.logger.warning("Position monitoring already active")
            return
        
        self.monitoring = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.logger.info("Position monitoring started")
    
    async def stop_monitoring(self):
        """
        Stop background monitoring loop.
        
        Example:
            >>> await tracker.stop_monitoring()
        """
        if not self.monitoring:
            self.logger.warning("Position monitoring not active")
            return
        
        self.monitoring = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Position monitoring stopped")
    
    async def _monitoring_loop(self):
        """Background monitoring loop."""
        self.logger.info(f"Starting position monitoring loop (interval: {self.update_interval}s)")
        
        while self.monitoring:
            try:
                # Get all active positions
                positions = await self.get_active_positions()
                
                if positions:
                    self.logger.info(f"Monitoring {len(positions)} active positions")
                    
                    # Track each position
                    for position in positions:
                        try:
                            await self.track_position(position.id)
                        except Exception as e:
                            self.logger.error(
                                f"Error tracking position {position.id}: {e}",
                                exc_info=True
                            )
                    
                    self.logger.debug("Position tracking cycle complete")
                
                # Wait for next interval
                await asyncio.sleep(self.update_interval)
                
            except asyncio.CancelledError:
                self.logger.info("Monitoring loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}", exc_info=True)
                await asyncio.sleep(self.update_interval)
    
    async def _get_current_price(self, symbol: str, session: AsyncSession) -> float:
        """
        Get current market price for a symbol.
        
        In production, this should:
        1. Connect to live market data feed (Zerodha WebSocket, etc.)
        2. Query real-time price APIs
        3. Fall back to latest database price if live data unavailable
        
        Args:
            symbol: Stock symbol
            session: Database session
        
        Returns:
            Current price
        """
        # TODO: Implement live price fetching from broker/market data
        # For now, simulate by getting latest price from database
        
        try:
            from data.models import Price, Timeframe
            
            result = await session.execute(
                select(Symbol).where(Symbol.symbol == symbol)
            )
            symbol_obj = result.scalar_one_or_none()
            
            if not symbol_obj:
                self.logger.warning(f"Symbol {symbol} not found")
                return 0.0
            
            # Get latest price
            result = await session.execute(
                select(Price)
                .where(
                    Price.symbol_id == symbol_obj.id,
                    Price.timeframe == Timeframe.DAILY
                )
                .order_by(Price.timestamp.desc())
                .limit(1)
            )
            latest_price = result.scalar_one_or_none()
            
            if latest_price:
                return float(latest_price.close)
            else:
                self.logger.warning(f"No price data found for {symbol}")
                return 0.0
                
        except Exception as e:
            self.logger.error(f"Error fetching price for {symbol}: {e}", exc_info=True)
            return 0.0
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get summary of entire portfolio.
        
        Returns:
            Dictionary with portfolio metrics
        
        Example:
            >>> summary = await tracker.get_portfolio_summary()
            >>> print(f"Total P&L: ${summary['total_pnl']:.2f}")
            >>> print(f"Open Positions: {summary['num_positions']}")
        """
        async with self.session_factory() as session:
            try:
                # Get all open positions
                positions = await self.get_active_positions()
                
                if not positions:
                    return {
                        "num_positions": 0,
                        "total_investment": 0.0,
                        "total_value": 0.0,
                        "total_unrealized_pnl": 0.0,
                        "total_realized_pnl": 0.0,
                        "total_pnl": 0.0,
                        "positions": []
                    }
                
                # Calculate aggregates
                total_investment = sum(
                    abs(p.entry_price * p.quantity) for p in positions
                )
                total_value = sum(
                    abs(p.current_price * p.quantity) for p in positions
                )
                total_unrealized_pnl = sum(p.unrealized_pnl for p in positions)
                
                # Get total realized P&L from closed positions
                result = await session.execute(
                    select(Position)
                    .where(
                        Position.is_open == False,
                        Position.trading_mode == TradingMode.LIVE
                    )
                )
                closed_positions = result.scalars().all()
                total_realized_pnl = sum(p.realized_pnl for p in closed_positions)
                
                # Position details
                position_details = []
                for p in positions:
                    pnl_calc = await self.calculate_pnl(p)
                    position_details.append({
                        "id": p.id,
                        "symbol": p.symbol.symbol,
                        "quantity": p.quantity,
                        "entry_price": p.entry_price,
                        "current_price": p.current_price,
                        "unrealized_pnl": pnl_calc.unrealized_pnl,
                        "unrealized_pnl_pct": pnl_calc.unrealized_pnl_pct,
                        "position_value": pnl_calc.position_value,
                    })
                
                return {
                    "num_positions": len(positions),
                    "total_investment": total_investment,
                    "total_value": total_value,
                    "total_unrealized_pnl": total_unrealized_pnl,
                    "total_realized_pnl": total_realized_pnl,
                    "total_pnl": total_unrealized_pnl + total_realized_pnl,
                    "positions": position_details
                }
                
            except Exception as e:
                self.logger.error(f"Error getting portfolio summary: {e}", exc_info=True)
                return {}
