# workers/tasks/position_monitoring.py
"""
Celery tasks for position monitoring.
Monitors stop losses, targets, reconciles with broker, and updates P&L.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio

from workers.celery_app import celery_app
from core.logger import get_logger
from core.position_tracker import PositionTracker, BrokerPosition
from core.position_monitor import PositionMonitor, MonitoringConfig
from core.position_reconciler import PositionReconciler
from data.repository import repository
from data.models import Position, TradingMode
from config import settings

# Import async SQLAlchemy components
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

logger = get_logger(__name__)


# Helper function to create async session factory
def get_async_session_factory():
    """
    Create async session factory for database operations.
    Converts MySQL connector URL to aiomysql for async support.
    """
    # Convert connection string to async
    async_url = settings.db.url.replace(
        "mysql+mysqlconnector://",
        "mysql+aiomysql://"
    )
    
    # Create async engine
    engine = create_async_engine(
        async_url,
        pool_size=settings.db.pool_size,
        pool_recycle=settings.db.pool_recycle,
        echo=settings.app.debug
    )
    
    # Create session factory
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    return async_session_factory


@celery_app.task(bind=True, name="workers.tasks.position_monitoring.monitor_positions")
def monitor_positions(self) -> Dict[str, Any]:
    """
    Monitor all active positions for stop loss and target hits.
    Runs position monitoring cycle once.
    
    Returns:
        Dictionary with task results and statistics
    
    Example:
        >>> from workers.tasks.position_monitoring import monitor_positions
        >>> result = monitor_positions.delay()
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting position monitoring task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'positions_monitored': 0,
        'stop_losses_triggered': 0,
        'targets_hit': 0,
        'positions_updated': 0,
        'errors': [],
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 0,
                'status': 'Initializing position monitoring...'
            }
        )
        
        # Run async monitoring
        async def run_monitoring():
            """Async function to run position monitoring."""
            # Create async session factory
            session_factory = get_async_session_factory()
            
            # Create position monitor with configuration
            config = MonitoringConfig(
                stop_loss_interval=30,
                target_interval=60,
                enable_stop_losses=True,
                enable_targets=True,
                enable_trailing_stops=True,
                trailing_activation_pct=5.0,
                send_alerts=True
            )
            
            monitor = PositionMonitor(session_factory, config)
            
            # Create position tracker
            tracker = PositionTracker(session_factory)
            
            try:
                # Get all active positions
                positions = await tracker.get_active_positions(TradingMode.LIVE)
                stats['positions_monitored'] = len(positions)
                
                logger.info(f"Monitoring {len(positions)} active positions")
                
                if not positions:
                    logger.info("No active positions to monitor")
                    return
                
                # Monitor each position
                for idx, position in enumerate(positions, 1):
                    try:
                        # Update progress
                        self.update_state(
                            state='PROGRESS',
                            meta={
                                'current': idx,
                                'total': len(positions),
                                'status': f'Monitoring position {position.symbol.symbol}...',
                                'symbol': position.symbol.symbol,
                                'progress_pct': (idx / len(positions)) * 100
                            }
                        )
                        
                        # Track position and update P&L
                        pnl = await tracker.track_position(position.id)
                        
                        if pnl:
                            stats['positions_updated'] += 1
                            
                            # Check stop loss
                            if position.stop_loss:
                                is_long = position.quantity > 0
                                
                                stop_hit = False
                                if is_long:
                                    stop_hit = pnl.current_price <= position.stop_loss
                                else:
                                    stop_hit = pnl.current_price >= position.stop_loss
                                
                                if stop_hit:
                                    logger.warning(
                                        f"Stop loss hit for {position.symbol.symbol}: "
                                        f"Price ${pnl.current_price:.2f} {'<=' if is_long else '>='} "
                                        f"SL ${position.stop_loss:.2f}"
                                    )
                                    
                                    # Close position
                                    await tracker.close_position(
                                        position.id,
                                        position.stop_loss,
                                        "stop_loss_hit"
                                    )
                                    stats['stop_losses_triggered'] += 1
                                    continue
                            
                            # Check target
                            if position.target:
                                is_long = position.quantity > 0
                                
                                target_hit = False
                                if is_long:
                                    target_hit = pnl.current_price >= position.target
                                else:
                                    target_hit = pnl.current_price <= position.target
                                
                                if target_hit:
                                    logger.info(
                                        f"Target hit for {position.symbol.symbol}: "
                                        f"Price ${pnl.current_price:.2f} {'>=' if is_long else '<='} "
                                        f"Target ${position.target:.2f}"
                                    )
                                    
                                    # Close position
                                    await tracker.close_position(
                                        position.id,
                                        position.target,
                                        "target_hit"
                                    )
                                    stats['targets_hit'] += 1
                                    continue
                            
                            logger.debug(
                                f"Position {position.symbol.symbol}: "
                                f"P&L ${pnl.unrealized_pnl:.2f} ({pnl.unrealized_pnl_pct:.2f}%)"
                            )
                        
                    except Exception as e:
                        logger.error(
                            f"Error monitoring position {position.id}: {e}",
                            exc_info=True
                        )
                        stats['errors'].append(f"Position {position.id}: {str(e)}")
                
                logger.info(
                    f"Monitoring cycle complete: "
                    f"{stats['positions_updated']} updated, "
                    f"{stats['stop_losses_triggered']} SL hit, "
                    f"{stats['targets_hit']} targets hit"
                )
                
            except Exception as e:
                logger.error(f"Error in monitoring: {e}", exc_info=True)
                raise
        
        # Run async function
        asyncio.run(run_monitoring())
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Position monitoring completed: "
            f"{stats['positions_monitored']} positions monitored"
        )
        
        # Create alert if stop losses or targets hit
        if stats['stop_losses_triggered'] > 0 or stats['targets_hit'] > 0:
            repository.add_alert(
                alert_type='position_monitoring',
                title='Position Monitoring Alert',
                message=f"Stop losses: {stats['stop_losses_triggered']}, "
                        f"Targets hit: {stats['targets_hit']}",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in monitor_positions task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='position_monitoring',
            title='Position Monitoring Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.position_monitoring.reconcile_broker_positions")
def reconcile_broker_positions(self, broker: str = "zerodha") -> Dict[str, Any]:
    """
    Reconcile database positions with broker positions.
    Detects and corrects discrepancies.
    
    Args:
        broker: Broker name (zerodha, upstox, etc.)
    
    Returns:
        Dictionary with task results and statistics
    
    Example:
        >>> from workers.tasks.position_monitoring import reconcile_broker_positions
        >>> result = reconcile_broker_positions.delay(broker="zerodha")
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting broker position reconciliation task for {broker}")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'broker': broker,
        'start_time': datetime.utcnow().isoformat(),
        'db_positions': 0,
        'broker_positions': 0,
        'discrepancies_found': 0,
        'auto_corrected': 0,
        'manual_review_required': 0,
        'errors': [],
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 0,
                'status': f'Fetching positions from {broker}...'
            }
        )
        
        # TODO: Fetch positions from broker
        # This needs to be implemented based on your broker integration
        broker_positions = []
        
        # Placeholder for broker integration:
        """
        # Example with Zerodha:
        from BrokerModules.Zerodha import ZerodhaAPI
        
        zerodha = ZerodhaAPI()
        raw_positions = zerodha.get_positions()
        
        broker_positions = []
        for pos in raw_positions:
            broker_pos = BrokerPosition(
                symbol=pos['tradingsymbol'],
                quantity=pos['quantity'],
                average_price=pos['average_price'],
                last_price=pos['last_price'],
                pnl=pos['pnl'],
                broker_id=pos['order_id'],
                exchange=pos['exchange'],
                product=pos['product']
            )
            broker_positions.append(broker_pos)
        """
        
        logger.warning(
            f"Broker reconciliation requires integration with {broker} API"
        )
        stats['errors'].append(
            f"Broker reconciliation not implemented - needs {broker} integration"
        )
        
        # For demonstration, log the process
        logger.info(f"Fetched {len(broker_positions)} positions from {broker}")
        stats['broker_positions'] = len(broker_positions)
        
        # Run async reconciliation
        async def run_reconciliation():
            """Async function to run reconciliation."""
            # Create async session factory
            session_factory = get_async_session_factory()
            
            # Create reconciler
            reconciler = PositionReconciler(
                session_factory,
                auto_correct=True,
                create_audit_logs=True
            )
            
            try:
                # Run reconciliation
                result = await reconciler.reconcile_positions(
                    broker_name=broker.capitalize(),
                    broker_positions=broker_positions,
                    trading_mode=TradingMode.LIVE
                )
                
                # Update stats
                stats['db_positions'] = result.db_positions_count
                stats['broker_positions'] = result.broker_positions_count
                stats['discrepancies_found'] = len(result.discrepancies)
                stats['auto_corrected'] = result.auto_corrected
                stats['manual_review_required'] = result.manual_review_required
                
                # Log summary
                logger.info(result.summary())
                
                # If discrepancies found, create alert
                if result.has_discrepancies:
                    repository.add_alert(
                        alert_type='reconciliation',
                        title=f'Position Reconciliation - {broker.capitalize()}',
                        message=f"Found {len(result.discrepancies)} discrepancies. "
                                f"Auto-corrected: {result.auto_corrected}, "
                                f"Manual review: {result.manual_review_required}",
                        metadata={
                            'broker': broker,
                            'discrepancies': [str(d) for d in result.discrepancies],
                            'actions': result.actions_taken
                        }
                    )
                
            except Exception as e:
                logger.error(f"Error in reconciliation: {e}", exc_info=True)
                raise
        
        # Run async function
        if broker_positions:  # Only run if we have broker positions
            asyncio.run(run_reconciliation())
        else:
            logger.warning("No broker positions to reconcile")
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Broker reconciliation completed: "
            f"{stats['discrepancies_found']} discrepancies found"
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in reconcile_broker_positions task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='reconciliation',
            title='Broker Reconciliation Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.position_monitoring.update_position_pnl")
def update_position_pnl(self) -> Dict[str, Any]:
    """
    Calculate and update P&L for all active positions.
    
    Returns:
        Dictionary with task results and statistics
    
    Example:
        >>> from workers.tasks.position_monitoring import update_position_pnl
        >>> result = update_position_pnl.delay()
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting position P&L update task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'positions_processed': 0,
        'positions_updated': 0,
        'total_unrealized_pnl': 0.0,
        'total_investment': 0.0,
        'portfolio_pnl_pct': 0.0,
        'errors': [],
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 0,
                'status': 'Updating position P&L...'
            }
        )
        
        # Run async P&L update
        async def run_pnl_update():
            """Async function to update P&L."""
            # Create async session factory
            session_factory = get_async_session_factory()
            
            # Create position tracker
            tracker = PositionTracker(session_factory)
            
            try:
                # Get all active positions
                positions = await tracker.get_active_positions(TradingMode.LIVE)
                
                logger.info(f"Updating P&L for {len(positions)} active positions")
                
                if not positions:
                    logger.info("No active positions to update")
                    return
                
                total_pnl = 0.0
                total_investment = 0.0
                
                # Update each position
                for idx, position in enumerate(positions, 1):
                    try:
                        # Update progress
                        self.update_state(
                            state='PROGRESS',
                            meta={
                                'current': idx,
                                'total': len(positions),
                                'status': f'Updating {position.symbol.symbol}...',
                                'symbol': position.symbol.symbol,
                                'progress_pct': (idx / len(positions)) * 100
                            }
                        )
                        
                        # Calculate P&L
                        pnl = await tracker.calculate_pnl(position)
                        
                        if pnl:
                            total_pnl += pnl.unrealized_pnl
                            total_investment += pnl.total_investment
                            stats['positions_updated'] += 1
                            
                            logger.debug(
                                f"{position.symbol.symbol}: "
                                f"P&L ${pnl.unrealized_pnl:.2f} ({pnl.unrealized_pnl_pct:.2f}%)"
                            )
                        
                        stats['positions_processed'] += 1
                        
                    except Exception as e:
                        logger.error(
                            f"Error updating P&L for position {position.id}: {e}",
                            exc_info=True
                        )
                        stats['errors'].append(f"Position {position.id}: {str(e)}")
                
                # Calculate portfolio metrics
                stats['total_unrealized_pnl'] = total_pnl
                stats['total_investment'] = total_investment
                
                if total_investment > 0:
                    stats['portfolio_pnl_pct'] = (total_pnl / total_investment) * 100.0
                
                logger.info(
                    f"P&L update complete: Total P&L ${total_pnl:.2f} "
                    f"({stats['portfolio_pnl_pct']:.2f}%)"
                )
                
            except Exception as e:
                logger.error(f"Error in P&L update: {e}", exc_info=True)
                raise
        
        # Run async function
        asyncio.run(run_pnl_update())
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Position P&L update completed: {stats['positions_updated']} positions updated"
        )
        
        # Create alert if significant P&L change
        if abs(stats['portfolio_pnl_pct']) > 5.0:
            alert_type = 'info' if stats['portfolio_pnl_pct'] > 0 else 'warning'
            repository.add_alert(
                alert_type='pnl_update',
                title='Portfolio P&L Update',
                message=f"Portfolio P&L: ${stats['total_unrealized_pnl']:.2f} "
                        f"({stats['portfolio_pnl_pct']:.2f}%)",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in update_position_pnl task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='pnl_update',
            title='Position P&L Update Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats
