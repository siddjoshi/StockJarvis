# core/position_monitor.py
"""
Position Monitor - Background monitoring service for active positions.
Continuously monitors stop losses, targets, time exits, and risk violations.
"""

import asyncio
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from core.logger import get_logger
from core.position_tracker import PositionTracker, PnLCalculation
from core.stop_loss_manager import StopLossManager
from core.risk_manager import RiskManager
from data.models import Position, Symbol, OrderAction, TradingMode, Alert
from config import settings

logger = get_logger(__name__)


class ExitReason(Enum):
    """Reasons for position exit."""
    STOP_LOSS_HIT = "stop_loss_hit"
    TARGET_HIT = "target_hit"
    TRAILING_STOP_HIT = "trailing_stop_hit"
    TIME_EXIT = "time_exit"
    RISK_VIOLATION = "risk_violation"
    MANUAL = "manual"
    EOD_EXIT = "eod_exit"


@dataclass
class MonitoringConfig:
    """Configuration for position monitoring."""
    
    # Monitoring intervals (seconds)
    stop_loss_interval: int = 30
    target_interval: int = 60
    time_exit_interval: int = 300  # 5 minutes
    risk_check_interval: int = 120  # 2 minutes
    
    # Exit settings
    enable_stop_losses: bool = True
    enable_targets: bool = True
    enable_time_exits: bool = True
    enable_risk_checks: bool = True
    
    # Time-based exit settings
    max_position_duration_hours: int = 24 * 5  # 5 days
    intraday_exit_time: Optional[str] = "15:15"  # Exit intraday positions
    
    # Risk settings
    max_position_loss_pct: float = 10.0  # Close if loss > 10%
    max_portfolio_loss_pct: float = 5.0  # Circuit breaker
    
    # Trailing stop settings
    enable_trailing_stops: bool = True
    trailing_activation_pct: float = 5.0  # Activate after 5% profit
    
    # Alert settings
    send_alerts: bool = True
    send_email: bool = True
    send_sms: bool = False


@dataclass
class MonitoringStats:
    """Statistics for monitoring session."""
    
    start_time: datetime
    positions_monitored: int = 0
    stop_losses_triggered: int = 0
    targets_hit: int = 0
    time_exits: int = 0
    risk_violations: int = 0
    errors: int = 0
    last_check_time: Optional[datetime] = None
    
    def runtime_seconds(self) -> float:
        """Calculate runtime in seconds."""
        return (datetime.utcnow() - self.start_time).total_seconds()
    
    def summary(self) -> str:
        """Generate summary report."""
        runtime = self.runtime_seconds()
        runtime_str = f"{runtime/3600:.1f}h" if runtime > 3600 else f"{runtime/60:.1f}m"
        
        return (
            f"Monitoring Stats (Runtime: {runtime_str}):\n"
            f"  Positions monitored: {self.positions_monitored}\n"
            f"  Stop losses triggered: {self.stop_losses_triggered}\n"
            f"  Targets hit: {self.targets_hit}\n"
            f"  Time exits: {self.time_exits}\n"
            f"  Risk violations: {self.risk_violations}\n"
            f"  Errors: {self.errors}\n"
            f"  Last check: {self.last_check_time}"
        )


class PositionMonitor:
    """
    Background monitoring service for positions.
    Runs multiple async loops to monitor stop losses, targets, time exits, and risk violations.
    
    Example:
        >>> from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        >>> from sqlalchemy.orm import sessionmaker
        >>> 
        >>> # Create async session
        >>> engine = create_async_engine(settings.db.url.replace("mysql+mysqlconnector", "mysql+aiomysql"))
        >>> async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        >>> 
        >>> # Initialize monitor with custom config
        >>> config = MonitoringConfig(
        >>>     stop_loss_interval=30,
        >>>     enable_trailing_stops=True,
        >>>     send_alerts=True
        >>> )
        >>> monitor = PositionMonitor(async_session, config)
        >>> 
        >>> # Start monitoring (runs in background)
        >>> await monitor.start_monitoring()
        >>> 
        >>> # Check stats
        >>> print(monitor.get_stats().summary())
        >>> 
        >>> # Stop gracefully
        >>> await monitor.stop_monitoring()
    """
    
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        config: Optional[MonitoringConfig] = None
    ):
        """
        Initialize position monitor.
        
        Args:
            session_factory: AsyncSession factory for database operations
            config: Monitoring configuration (uses defaults if None)
        """
        self.session_factory = session_factory
        self.config = config or MonitoringConfig()
        self.logger = get_logger(__name__)
        
        # Initialize components
        self.position_tracker = PositionTracker(session_factory)
        self.stop_loss_manager = StopLossManager()
        
        # Monitoring state
        self.monitoring = False
        self._tasks: List[asyncio.Task] = []
        self._stop_event = asyncio.Event()
        
        # Statistics
        self.stats = MonitoringStats(start_time=datetime.utcnow())
        
        # Cache to avoid repeated actions
        self._processed_exits: Set[int] = set()  # position_ids already processed
        
        self.logger.info("PositionMonitor initialized")
    
    async def start_monitoring(self):
        """
        Start all monitoring loops.
        Launches 4 concurrent monitoring tasks:
        - monitor_stop_losses
        - monitor_targets
        - monitor_time_exits
        - monitor_risk_violations
        
        Example:
            >>> await monitor.start_monitoring()
            >>> # Runs in background until stop_monitoring() is called
        """
        if self.monitoring:
            self.logger.warning("Position monitoring already active")
            return
        
        self.monitoring = True
        self._stop_event.clear()
        self.stats = MonitoringStats(start_time=datetime.utcnow())
        
        # Start monitoring tasks
        if self.config.enable_stop_losses:
            task = asyncio.create_task(self.monitor_stop_losses())
            self._tasks.append(task)
            self.logger.info("Started stop loss monitoring")
        
        if self.config.enable_targets:
            task = asyncio.create_task(self.monitor_targets())
            self._tasks.append(task)
            self.logger.info("Started target monitoring")
        
        if self.config.enable_time_exits:
            task = asyncio.create_task(self.monitor_time_exits())
            self._tasks.append(task)
            self.logger.info("Started time exit monitoring")
        
        if self.config.enable_risk_checks:
            task = asyncio.create_task(self.monitor_risk_violations())
            self._tasks.append(task)
            self.logger.info("Started risk violation monitoring")
        
        self.logger.info(
            f"Position monitoring started with {len(self._tasks)} active monitors"
        )
    
    async def stop_monitoring(self):
        """
        Stop all monitoring loops gracefully.
        
        Example:
            >>> await monitor.stop_monitoring()
            >>> print(monitor.get_stats().summary())
        """
        if not self.monitoring:
            self.logger.warning("Position monitoring not active")
            return
        
        self.logger.info("Stopping position monitoring...")
        
        self.monitoring = False
        self._stop_event.set()
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for cancellation
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        
        self._tasks.clear()
        
        self.logger.info(
            f"Position monitoring stopped. {self.stats.summary()}"
        )
    
    async def monitor_stop_losses(self):
        """
        Monitor and trigger stop losses.
        Checks all open positions every 30 seconds for stop loss hits.
        Supports both fixed and trailing stop losses.
        """
        self.logger.info(
            f"Stop loss monitor started (interval: {self.config.stop_loss_interval}s)"
        )
        
        while self.monitoring and not self._stop_event.is_set():
            try:
                async with self.session_factory() as session:
                    # Get all open positions
                    result = await session.execute(
                        select(Position)
                        .options(selectinload(Position.symbol))
                        .where(
                            Position.is_open == True,
                            Position.trading_mode == TradingMode.LIVE
                        )
                    )
                    positions = result.scalars().all()
                    
                    self.logger.debug(f"Checking stop losses for {len(positions)} positions")
                    
                    for position in positions:
                        if position.id in self._processed_exits:
                            continue
                        
                        try:
                            # Get current P&L
                            pnl = await self.position_tracker.calculate_pnl(position)
                            
                            # Determine if long or short
                            is_long = position.quantity > 0
                            
                            # Check trailing stop
                            if self.config.enable_trailing_stops:
                                # Initialize trailing stop if not exists
                                trailing_state = self.stop_loss_manager.get_trailing_stop(
                                    position.id
                                )
                                
                                if not trailing_state and position.stop_loss:
                                    # Initialize
                                    self.stop_loss_manager.initialize_trailing_stop(
                                        position_id=position.id,
                                        symbol=position.symbol.symbol,
                                        entry_price=position.entry_price,
                                        current_price=pnl.current_price,
                                        action=OrderAction.BUY if is_long else OrderAction.SELL,
                                        activation_profit_pct=self.config.trailing_activation_pct,
                                        distance_pct=None  # Use default
                                    )
                                
                                # Update trailing stop
                                if trailing_state:
                                    updated, state = self.stop_loss_manager.update_trailing_stop(
                                        position.id,
                                        pnl.current_price,
                                        is_long
                                    )
                                    
                                    if updated and state:
                                        # Update position stop loss in DB
                                        position.stop_loss = state.stop_price
                                        await session.commit()
                                    
                                    # Check if trailing stop triggered
                                    if self.stop_loss_manager.check_trailing_stop_trigger(
                                        position.id,
                                        pnl.current_price,
                                        is_long
                                    ):
                                        await self._exit_position(
                                            position,
                                            pnl.current_price,
                                            ExitReason.TRAILING_STOP_HIT,
                                            session
                                        )
                                        self.stats.stop_losses_triggered += 1
                                        continue
                            
                            # Check regular stop loss
                            if position.stop_loss:
                                stop_triggered = False
                                
                                if is_long:
                                    stop_triggered = pnl.current_price <= position.stop_loss
                                else:
                                    stop_triggered = pnl.current_price >= position.stop_loss
                                
                                if stop_triggered:
                                    self.logger.warning(
                                        f"Stop loss triggered for {position.symbol.symbol} "
                                        f"(ID: {position.id}): Current ${pnl.current_price:.2f} "
                                        f"{'<=' if is_long else '>='} SL ${position.stop_loss:.2f}"
                                    )
                                    
                                    await self._exit_position(
                                        position,
                                        position.stop_loss,
                                        ExitReason.STOP_LOSS_HIT,
                                        session
                                    )
                                    self.stats.stop_losses_triggered += 1
                        
                        except Exception as e:
                            self.logger.error(
                                f"Error checking stop loss for position {position.id}: {e}",
                                exc_info=True
                            )
                            self.stats.errors += 1
                    
                    self.stats.last_check_time = datetime.utcnow()
                
                # Wait for next interval
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.config.stop_loss_interval
                    )
                except asyncio.TimeoutError:
                    pass
                
            except asyncio.CancelledError:
                self.logger.info("Stop loss monitor cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in stop loss monitor: {e}", exc_info=True)
                self.stats.errors += 1
                await asyncio.sleep(self.config.stop_loss_interval)
    
    async def monitor_targets(self):
        """
        Monitor and trigger profit targets.
        Checks all open positions every 60 seconds for target hits.
        """
        self.logger.info(
            f"Target monitor started (interval: {self.config.target_interval}s)"
        )
        
        while self.monitoring and not self._stop_event.is_set():
            try:
                async with self.session_factory() as session:
                    # Get all open positions with targets
                    result = await session.execute(
                        select(Position)
                        .options(selectinload(Position.symbol))
                        .where(
                            Position.is_open == True,
                            Position.trading_mode == TradingMode.LIVE,
                            Position.target.isnot(None)
                        )
                    )
                    positions = result.scalars().all()
                    
                    self.logger.debug(f"Checking targets for {len(positions)} positions")
                    
                    for position in positions:
                        if position.id in self._processed_exits:
                            continue
                        
                        try:
                            # Get current P&L
                            pnl = await self.position_tracker.calculate_pnl(position)
                            
                            # Determine if long or short
                            is_long = position.quantity > 0
                            
                            # Check target
                            target_hit = False
                            
                            if is_long:
                                target_hit = pnl.current_price >= position.target
                            else:
                                target_hit = pnl.current_price <= position.target
                            
                            if target_hit:
                                self.logger.info(
                                    f"Target hit for {position.symbol.symbol} "
                                    f"(ID: {position.id}): Current ${pnl.current_price:.2f} "
                                    f"{'>=' if is_long else '<='} Target ${position.target:.2f}"
                                )
                                
                                await self._exit_position(
                                    position,
                                    position.target,
                                    ExitReason.TARGET_HIT,
                                    session
                                )
                                self.stats.targets_hit += 1
                        
                        except Exception as e:
                            self.logger.error(
                                f"Error checking target for position {position.id}: {e}",
                                exc_info=True
                            )
                            self.stats.errors += 1
                    
                    self.stats.last_check_time = datetime.utcnow()
                
                # Wait for next interval
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.config.target_interval
                    )
                except asyncio.TimeoutError:
                    pass
                
            except asyncio.CancelledError:
                self.logger.info("Target monitor cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in target monitor: {e}", exc_info=True)
                self.stats.errors += 1
                await asyncio.sleep(self.config.target_interval)
    
    async def monitor_time_exits(self):
        """
        Monitor time-based exits.
        Checks for:
        - Positions held too long (max_position_duration_hours)
        - Intraday positions to close at EOD
        """
        self.logger.info(
            f"Time exit monitor started (interval: {self.config.time_exit_interval}s)"
        )
        
        while self.monitoring and not self._stop_event.is_set():
            try:
                async with self.session_factory() as session:
                    now = datetime.utcnow()
                    
                    # Get all open positions
                    result = await session.execute(
                        select(Position)
                        .options(selectinload(Position.symbol))
                        .where(
                            Position.is_open == True,
                            Position.trading_mode == TradingMode.LIVE
                        )
                    )
                    positions = result.scalars().all()
                    
                    self.logger.debug(f"Checking time exits for {len(positions)} positions")
                    
                    for position in positions:
                        if position.id in self._processed_exits:
                            continue
                        
                        try:
                            # Check max duration
                            position_age = now - position.entry_time
                            max_duration = timedelta(hours=self.config.max_position_duration_hours)
                            
                            if position_age > max_duration:
                                self.logger.warning(
                                    f"Position {position.symbol.symbol} (ID: {position.id}) "
                                    f"held for {position_age.days} days, exceeds max duration"
                                )
                                
                                pnl = await self.position_tracker.calculate_pnl(position)
                                await self._exit_position(
                                    position,
                                    pnl.current_price,
                                    ExitReason.TIME_EXIT,
                                    session
                                )
                                self.stats.time_exits += 1
                                continue
                            
                            # Check intraday EOD exit
                            if self.config.intraday_exit_time:
                                # Parse time (HH:MM format)
                                try:
                                    exit_hour, exit_min = map(
                                        int,
                                        self.config.intraday_exit_time.split(":")
                                    )
                                    exit_time = now.replace(
                                        hour=exit_hour,
                                        minute=exit_min,
                                        second=0,
                                        microsecond=0
                                    )
                                    
                                    # Check if it's time to exit
                                    if now >= exit_time:
                                        # Check if position was opened today
                                        if position.entry_time.date() == now.date():
                                            self.logger.info(
                                                f"EOD exit for intraday position "
                                                f"{position.symbol.symbol} (ID: {position.id})"
                                            )
                                            
                                            pnl = await self.position_tracker.calculate_pnl(position)
                                            await self._exit_position(
                                                position,
                                                pnl.current_price,
                                                ExitReason.EOD_EXIT,
                                                session
                                            )
                                            self.stats.time_exits += 1
                                
                                except ValueError:
                                    self.logger.error(
                                        f"Invalid intraday_exit_time format: "
                                        f"{self.config.intraday_exit_time}"
                                    )
                        
                        except Exception as e:
                            self.logger.error(
                                f"Error checking time exit for position {position.id}: {e}",
                                exc_info=True
                            )
                            self.stats.errors += 1
                    
                    self.stats.last_check_time = datetime.utcnow()
                
                # Wait for next interval
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.config.time_exit_interval
                    )
                except asyncio.TimeoutError:
                    pass
                
            except asyncio.CancelledError:
                self.logger.info("Time exit monitor cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in time exit monitor: {e}", exc_info=True)
                self.stats.errors += 1
                await asyncio.sleep(self.config.time_exit_interval)
    
    async def monitor_risk_violations(self):
        """
        Monitor risk violations and circuit breakers.
        Checks for:
        - Individual position losses exceeding limits
        - Portfolio-level risk violations
        - Circuit breaker conditions
        """
        self.logger.info(
            f"Risk monitor started (interval: {self.config.risk_check_interval}s)"
        )
        
        while self.monitoring and not self._stop_event.is_set():
            try:
                async with self.session_factory() as session:
                    # Get all open positions
                    result = await session.execute(
                        select(Position)
                        .options(selectinload(Position.symbol))
                        .where(
                            Position.is_open == True,
                            Position.trading_mode == TradingMode.LIVE
                        )
                    )
                    positions = result.scalars().all()
                    
                    if not positions:
                        await asyncio.sleep(self.config.risk_check_interval)
                        continue
                    
                    self.logger.debug(f"Checking risk for {len(positions)} positions")
                    
                    # Calculate portfolio metrics
                    total_unrealized_pnl = 0.0
                    total_investment = 0.0
                    
                    for position in positions:
                        if position.id in self._processed_exits:
                            continue
                        
                        try:
                            pnl = await self.position_tracker.calculate_pnl(position)
                            total_unrealized_pnl += pnl.unrealized_pnl
                            total_investment += pnl.total_investment
                            
                            # Check individual position loss
                            if pnl.unrealized_pnl_pct < -self.config.max_position_loss_pct:
                                self.logger.critical(
                                    f"Position {position.symbol.symbol} (ID: {position.id}) "
                                    f"loss {pnl.unrealized_pnl_pct:.2f}% exceeds limit "
                                    f"{self.config.max_position_loss_pct}%"
                                )
                                
                                await self._exit_position(
                                    position,
                                    pnl.current_price,
                                    ExitReason.RISK_VIOLATION,
                                    session
                                )
                                self.stats.risk_violations += 1
                                
                                # Send critical alert
                                await self._send_alert(
                                    session,
                                    "CRITICAL: Position Loss Limit Exceeded",
                                    f"Position {position.symbol.symbol} loss {pnl.unrealized_pnl_pct:.2f}% "
                                    f"exceeded {self.config.max_position_loss_pct}%. Position closed.",
                                    severity="critical"
                                )
                        
                        except Exception as e:
                            self.logger.error(
                                f"Error checking risk for position {position.id}: {e}",
                                exc_info=True
                            )
                            self.stats.errors += 1
                    
                    # Check portfolio loss
                    if total_investment > 0:
                        portfolio_loss_pct = (total_unrealized_pnl / total_investment) * 100.0
                        
                        if portfolio_loss_pct < -self.config.max_portfolio_loss_pct:
                            self.logger.critical(
                                f"PORTFOLIO LOSS {portfolio_loss_pct:.2f}% exceeds limit "
                                f"{self.config.max_portfolio_loss_pct}%"
                            )
                            
                            # Send critical alert
                            await self._send_alert(
                                session,
                                "CRITICAL: Portfolio Loss Limit Exceeded",
                                f"Portfolio loss {portfolio_loss_pct:.2f}% exceeded "
                                f"{self.config.max_portfolio_loss_pct}%. Circuit breaker triggered.",
                                severity="critical"
                            )
                            
                            # TODO: Trigger circuit breaker / close all positions
                            # This should integrate with RiskManager
                            self.stats.risk_violations += 1
                    
                    self.stats.last_check_time = datetime.utcnow()
                
                # Wait for next interval
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.config.risk_check_interval
                    )
                except asyncio.TimeoutError:
                    pass
                
            except asyncio.CancelledError:
                self.logger.info("Risk monitor cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in risk monitor: {e}", exc_info=True)
                self.stats.errors += 1
                await asyncio.sleep(self.config.risk_check_interval)
    
    async def _exit_position(
        self,
        position: Position,
        exit_price: float,
        reason: ExitReason,
        session: AsyncSession
    ):
        """
        Exit a position and create alert.
        
        Args:
            position: Position to exit
            exit_price: Exit price
            reason: Reason for exit
            session: Database session
        """
        try:
            # Mark as processed
            self._processed_exits.add(position.id)
            
            # Close position
            success = await self.position_tracker.close_position(
                position.id,
                exit_price,
                reason.value
            )
            
            if success:
                self.logger.info(
                    f"Position {position.symbol.symbol} (ID: {position.id}) "
                    f"exited at ${exit_price:.2f}, reason: {reason.value}"
                )
                
                # Send alert
                if self.config.send_alerts:
                    await self._send_alert(
                        session,
                        f"Position Exited: {position.symbol.symbol}",
                        f"Position exited at ${exit_price:.2f}. Reason: {reason.value}. "
                        f"P&L: ${position.realized_pnl:.2f}",
                        severity="info"
                    )
            else:
                self.logger.error(f"Failed to exit position {position.id}")
        
        except Exception as e:
            self.logger.error(f"Error exiting position {position.id}: {e}", exc_info=True)
            self.stats.errors += 1
    
    async def _send_alert(
        self,
        session: AsyncSession,
        title: str,
        message: str,
        severity: str = "info"
    ):
        """
        Send alert notification.
        
        Args:
            session: Database session
            title: Alert title
            message: Alert message
            severity: Severity level (info, warning, error, critical)
        """
        try:
            alert = Alert(
                type=severity,
                title=title,
                message=message,
                email_sent=False,
                sms_sent=False
            )
            
            session.add(alert)
            await session.commit()
            
            # TODO: Implement actual email/SMS sending
            # This would integrate with notification service
            
            self.logger.info(f"Alert created: {title}")
        
        except Exception as e:
            self.logger.error(f"Error sending alert: {e}", exc_info=True)
    
    def get_stats(self) -> MonitoringStats:
        """
        Get current monitoring statistics.
        
        Returns:
            MonitoringStats object
        
        Example:
            >>> stats = monitor.get_stats()
            >>> print(stats.summary())
        """
        return self.stats
    
    def reset_stats(self):
        """
        Reset monitoring statistics.
        
        Example:
            >>> monitor.reset_stats()
        """
        self.stats = MonitoringStats(start_time=datetime.utcnow())
        self._processed_exits.clear()
        self.logger.info("Monitoring statistics reset")
