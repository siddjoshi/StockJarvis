# workers/tasks/signal_generation.py
"""
Celery tasks for signal generation.
Runs strategies to generate trading signals for EOD and intraday.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from workers.celery_app import celery_app
from core.logger import get_logger
from core.scanner import Scanner, create_eod_scanner, create_intraday_scanner
from core.strategy_engine import registry
from data.repository import repository
from data.models import Timeframe, Signal
from config import settings

logger = get_logger(__name__)


@celery_app.task(bind=True, name="workers.tasks.signal_generation.generate_eod_signals")
def generate_eod_signals(self, strategy_names: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run end-of-day strategies and generate signals.
    
    Args:
        strategy_names: List of strategy names to run (runs all tradeable strategies if None)
    
    Returns:
        Dictionary with task results and statistics
    
    Example:
        >>> from workers.tasks.signal_generation import generate_eod_signals
        >>> result = generate_eod_signals.delay(['RSI_Reversal', 'MACD_Crossover'])
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting EOD signal generation task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'timeframe': 'EOD',
        'strategies_requested': len(strategy_names) if strategy_names else 0,
        'strategies_executed': 0,
        'symbols_scanned': 0,
        'signals_generated': 0,
        'buy_signals': 0,
        'sell_signals': 0,
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
                'status': 'Initializing EOD signal generation...'
            }
        )
        
        # Get strategies to run
        if strategy_names:
            strategies = []
            for name in strategy_names:
                strategy = registry.get(name)
                if strategy and strategy.is_tradeable():
                    strategies.append(strategy)
                else:
                    logger.warning(f"Strategy not found or not tradeable: {name}")
                    stats['errors'].append(f"Invalid strategy: {name}")
        else:
            # Use all tradeable strategies
            strategies = registry.get_tradeable()
            logger.info(f"No strategies specified, using all {len(strategies)} tradeable strategies")
        
        stats['strategies_requested'] = len(strategies)
        
        if not strategies:
            logger.error("No valid strategies to run")
            stats['status'] = 'failed'
            stats['error'] = 'No valid strategies to run'
            return stats
        
        logger.info(f"Running {len(strategies)} EOD strategies")
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': len(strategies),
                'status': f'Running {len(strategies)} strategies...',
                'progress_pct': 0
            }
        )
        
        # Create EOD scanner
        scanner = create_eod_scanner()
        stats['symbols_scanned'] = len(scanner.symbols)
        
        logger.info(f"Scanning {len(scanner.symbols)} symbols with {len(strategies)} strategies")
        
        # Run scanner for each strategy
        all_signals = []
        
        for idx, strategy in enumerate(strategies, 1):
            try:
                # Update progress
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': idx,
                        'total': len(strategies),
                        'status': f'Running strategy: {strategy.name}...',
                        'strategy': strategy.name,
                        'progress_pct': (idx / len(strategies)) * 100
                    }
                )
                
                logger.info(f"[{idx}/{len(strategies)}] Running strategy: {strategy.name}")
                
                # Run strategy across all symbols
                signals = scanner.scan_with_strategy(strategy.name)
                
                if signals:
                    all_signals.extend(signals)
                    logger.info(f"{strategy.name} generated {len(signals)} signals")
                else:
                    logger.info(f"{strategy.name} generated no signals")
                
                stats['strategies_executed'] += 1
                
            except Exception as e:
                logger.error(f"Error running strategy {strategy.name}: {e}", exc_info=True)
                stats['errors'].append(f"{strategy.name}: {str(e)}")
        
        # Process generated signals
        stats['signals_generated'] = len(all_signals)
        
        # Count buy/sell signals
        from data.models import OrderAction
        stats['buy_signals'] = sum(1 for s in all_signals if s.action == OrderAction.BUY)
        stats['sell_signals'] = sum(1 for s in all_signals if s.action == OrderAction.SELL)
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"EOD signal generation completed: {stats['signals_generated']} signals generated "
            f"({stats['buy_signals']} BUY, {stats['sell_signals']} SELL)"
        )
        
        # Create alert if significant signals generated
        if stats['signals_generated'] > 0:
            repository.add_alert(
                alert_type='signal_generation',
                title='EOD Signals Generated',
                message=f"Generated {stats['signals_generated']} signals: "
                        f"{stats['buy_signals']} BUY, {stats['sell_signals']} SELL",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in generate_eod_signals task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='signal_generation',
            title='EOD Signal Generation Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.signal_generation.generate_intraday_signals")
def generate_intraday_signals(self, strategy_names: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run intraday strategies and generate signals.
    
    Args:
        strategy_names: List of strategy names to run (runs all tradeable strategies if None)
    
    Returns:
        Dictionary with task results and statistics
    
    Example:
        >>> from workers.tasks.signal_generation import generate_intraday_signals
        >>> result = generate_intraday_signals.delay(['Momentum_Scalper'])
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting intraday signal generation task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'timeframe': 'Intraday',
        'strategies_requested': len(strategy_names) if strategy_names else 0,
        'strategies_executed': 0,
        'symbols_scanned': 0,
        'signals_generated': 0,
        'buy_signals': 0,
        'sell_signals': 0,
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
                'status': 'Initializing intraday signal generation...'
            }
        )
        
        # Check market hours (only run during trading hours)
        now = datetime.now()
        market_open = now.replace(hour=9, minute=15, second=0)
        market_close = now.replace(hour=15, minute=30, second=0)
        
        if not (market_open <= now <= market_close):
            logger.warning(f"Outside market hours, skipping intraday signal generation")
            stats['status'] = 'skipped'
            stats['error'] = 'Outside market hours'
            stats['end_time'] = datetime.utcnow().isoformat()
            return stats
        
        # Get strategies to run
        if strategy_names:
            strategies = []
            for name in strategy_names:
                strategy = registry.get(name)
                if strategy and strategy.is_tradeable():
                    strategies.append(strategy)
                else:
                    logger.warning(f"Strategy not found or not tradeable: {name}")
                    stats['errors'].append(f"Invalid strategy: {name}")
        else:
            # Use all tradeable strategies
            strategies = registry.get_tradeable()
            logger.info(f"No strategies specified, using all {len(strategies)} tradeable strategies")
        
        stats['strategies_requested'] = len(strategies)
        
        if not strategies:
            logger.error("No valid strategies to run")
            stats['status'] = 'failed'
            stats['error'] = 'No valid strategies to run'
            return stats
        
        logger.info(f"Running {len(strategies)} intraday strategies")
        
        # Update progress
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': len(strategies),
                'status': f'Running {len(strategies)} strategies...',
                'progress_pct': 0
            }
        )
        
        # Create intraday scanner (15-minute bars)
        scanner = create_intraday_scanner()
        stats['symbols_scanned'] = len(scanner.symbols)
        
        logger.info(f"Scanning {len(scanner.symbols)} symbols with {len(strategies)} strategies")
        
        # Run scanner for each strategy
        all_signals = []
        
        for idx, strategy in enumerate(strategies, 1):
            try:
                # Update progress
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': idx,
                        'total': len(strategies),
                        'status': f'Running strategy: {strategy.name}...',
                        'strategy': strategy.name,
                        'progress_pct': (idx / len(strategies)) * 100
                    }
                )
                
                logger.info(f"[{idx}/{len(strategies)}] Running strategy: {strategy.name}")
                
                # Run strategy across all symbols
                signals = scanner.scan_with_strategy(strategy.name)
                
                if signals:
                    all_signals.extend(signals)
                    logger.info(f"{strategy.name} generated {len(signals)} signals")
                else:
                    logger.info(f"{strategy.name} generated no signals")
                
                stats['strategies_executed'] += 1
                
            except Exception as e:
                logger.error(f"Error running strategy {strategy.name}: {e}", exc_info=True)
                stats['errors'].append(f"{strategy.name}: {str(e)}")
        
        # Process generated signals
        stats['signals_generated'] = len(all_signals)
        
        # Count buy/sell signals
        from data.models import OrderAction
        stats['buy_signals'] = sum(1 for s in all_signals if s.action == OrderAction.BUY)
        stats['sell_signals'] = sum(1 for s in all_signals if s.action == OrderAction.SELL)
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Intraday signal generation completed: {stats['signals_generated']} signals generated "
            f"({stats['buy_signals']} BUY, {stats['sell_signals']} SELL)"
        )
        
        # Create alert if significant signals generated
        if stats['signals_generated'] > 0:
            repository.add_alert(
                alert_type='signal_generation',
                title='Intraday Signals Generated',
                message=f"Generated {stats['signals_generated']} signals: "
                        f"{stats['buy_signals']} BUY, {stats['sell_signals']} SELL",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in generate_intraday_signals task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='signal_generation',
            title='Intraday Signal Generation Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.signal_generation.cleanup_old_signals")
def cleanup_old_signals(self, days: int = 90) -> Dict[str, Any]:
    """
    Archive or delete signals older than specified days.
    
    Args:
        days: Number of days to keep signals (default: 90)
    
    Returns:
        Dictionary with task results and statistics
    
    Example:
        >>> from workers.tasks.signal_generation import cleanup_old_signals
        >>> result = cleanup_old_signals.delay(days=90)
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting signal cleanup task (older than {days} days)")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'days_threshold': days,
        'signals_before': 0,
        'signals_archived': 0,
        'signals_deleted': 0,
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
                'status': f'Cleaning up signals older than {days} days...'
            }
        )
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        logger.info(f"Cleaning up signals before {cutoff_date.date()}")
        
        # Get old signals
        with repository.get_session() as session:
            # Count total signals before cleanup
            stats['signals_before'] = session.query(Signal).count()
            
            # Find old signals
            old_signals = session.query(Signal).filter(
                Signal.generated_at < cutoff_date
            ).all()
            
            logger.info(f"Found {len(old_signals)} signals older than {days} days")
            
            if not old_signals:
                stats['status'] = 'completed'
                stats['end_time'] = datetime.utcnow().isoformat()
                logger.info("No old signals to clean up")
                return stats
            
            # Update progress
            total_signals = len(old_signals)
            
            # Process signals in batches
            batch_size = 100
            
            for i in range(0, len(old_signals), batch_size):
                batch = old_signals[i:i + batch_size]
                
                # Update progress
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': i + len(batch),
                        'total': total_signals,
                        'status': f'Processing batch {i // batch_size + 1}...',
                        'progress_pct': ((i + len(batch)) / total_signals) * 100
                    }
                )
                
                for signal in batch:
                    try:
                        # Option 1: Delete signal
                        session.delete(signal)
                        stats['signals_deleted'] += 1
                        
                        # Option 2: Archive signal (if you have archive table)
                        # archive_signal = ArchivedSignal.from_signal(signal)
                        # session.add(archive_signal)
                        # session.delete(signal)
                        # stats['signals_archived'] += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing signal {signal.id}: {e}")
                        stats['errors'].append(f"Signal {signal.id}: {str(e)}")
                
                # Commit batch
                try:
                    session.commit()
                    logger.info(
                        f"Processed batch: {len(batch)} signals deleted"
                    )
                except Exception as e:
                    session.rollback()
                    logger.error(f"Error committing batch: {e}")
                    stats['errors'].append(f"Batch commit error: {str(e)}")
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Signal cleanup completed: "
            f"{stats['signals_deleted']} deleted, "
            f"{stats['signals_archived']} archived"
        )
        
        # Create alert if significant cleanup
        if stats['signals_deleted'] > 100:
            repository.add_alert(
                alert_type='maintenance',
                title='Signal Cleanup Completed',
                message=f"Deleted {stats['signals_deleted']} signals older than {days} days",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in cleanup_old_signals task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='maintenance',
            title='Signal Cleanup Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats
