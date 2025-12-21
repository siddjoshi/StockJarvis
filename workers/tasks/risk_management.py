# workers/tasks/risk_management.py
"""
Celery tasks for risk management.
Handles portfolio exposure monitoring, circuit breakers, and position sizing calculations.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import asyncio

from workers.celery_app import celery_app
from core.logger import get_logger
from core.risk_manager import RiskManager
from core.position_tracker import PositionTracker
from data.repository import repository
from data.models import TradingMode, OrderAction
from config import settings
from config.risk_config import get_circuit_breaker_threshold, get_portfolio_limit

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


@celery_app.task(bind=True, name="workers.tasks.risk_management.check_risk_limits")
def check_risk_limits(self) -> Dict[str, Any]:
    """
    Check portfolio risk limits including exposure, position limits, and circuit breakers.
    Monitors overall portfolio health and triggers alerts for violations.
    
    Returns:
        Dictionary with task results and risk metrics
    
    Example:
        >>> from workers.tasks.risk_management import check_risk_limits
        >>> result = check_risk_limits.delay()
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting risk limits check task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'violations_found': 0,
        'warnings_found': 0,
        'checks_performed': 0,
        'circuit_breaker_active': False,
        'risk_metrics': {},
        'violations': [],
        'warnings': [],
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 5,
                'status': 'Checking portfolio risk limits...'
            }
        )
        
        # Create risk manager with sync session
        with repository.get_session() as session:
            risk_manager = RiskManager(session)
            
            # Check 1: Get portfolio metrics
            logger.info("Checking portfolio metrics...")
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': 1,
                    'total': 5,
                    'status': 'Calculating portfolio metrics...',
                    'progress_pct': 20
                }
            )
            
            portfolio_metrics = risk_manager.get_portfolio_metrics()
            stats['risk_metrics'] = portfolio_metrics
            stats['checks_performed'] += 1
            
            # Log key metrics
            logger.info(
                f"Portfolio Metrics: {portfolio_metrics['num_open_positions']} positions, "
                f"Exposure: {portfolio_metrics['exposure_pct']:.2f}%, "
                f"Unrealized P&L: ${portfolio_metrics['unrealized_pnl']:.2f}, "
                f"Win Rate: {portfolio_metrics['win_rate']*100:.1f}%"
            )
            
            # Check 2: Validate portfolio exposure
            logger.info("Checking portfolio exposure...")
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': 2,
                    'total': 5,
                    'status': 'Validating portfolio exposure...',
                    'progress_pct': 40
                }
            )
            
            account_balance = settings.trading.capital
            exposure_check = risk_manager._check_portfolio_exposure(
                new_position_value=0,  # Just checking current exposure
                account_balance=account_balance
            )
            
            stats['checks_performed'] += 1
            
            if not exposure_check.passed:
                stats['violations_found'] += len(exposure_check.violations)
                stats['violations'].extend(exposure_check.violations)
                logger.error(f"Exposure violations: {exposure_check.violations}")
                
                # Create alert for exposure violations
                repository.add_alert(
                    alert_type='risk_violation',
                    title='Portfolio Exposure Limit Exceeded',
                    message=f"Exposure: {exposure_check.metadata['exposure_pct']:.2f}% - "
                            f"Violations: {', '.join(exposure_check.violations)}",
                    metadata=exposure_check.metadata
                )
            
            if exposure_check.warnings:
                stats['warnings_found'] += len(exposure_check.warnings)
                stats['warnings'].extend(exposure_check.warnings)
                logger.warning(f"Exposure warnings: {exposure_check.warnings}")
            
            # Check 3: Validate position limits
            logger.info("Checking position limits...")
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': 3,
                    'total': 5,
                    'status': 'Validating position limits...',
                    'progress_pct': 60
                }
            )
            
            # Check total positions against limit
            total_positions = portfolio_metrics['num_open_positions']
            max_positions = get_portfolio_limit("max_open_positions")
            
            stats['checks_performed'] += 1
            
            if total_positions >= max_positions:
                violation_msg = f"Position count {total_positions} >= limit {max_positions}"
                stats['violations_found'] += 1
                stats['violations'].append(violation_msg)
                logger.error(violation_msg)
                
                repository.add_alert(
                    alert_type='risk_violation',
                    title='Maximum Position Limit Reached',
                    message=violation_msg,
                    metadata={'total_positions': total_positions, 'max_positions': max_positions}
                )
            elif total_positions >= max_positions * 0.9:
                warning_msg = f"Position count {total_positions} approaching limit {max_positions}"
                stats['warnings_found'] += 1
                stats['warnings'].append(warning_msg)
                logger.warning(warning_msg)
            
            # Check 4: Validate drawdown limits
            logger.info("Checking drawdown limits...")
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': 4,
                    'total': 5,
                    'status': 'Validating drawdown limits...',
                    'progress_pct': 80
                }
            )
            
            drawdown_check = risk_manager._check_drawdown_limits(account_balance)
            stats['checks_performed'] += 1
            
            if not drawdown_check.passed:
                stats['violations_found'] += len(drawdown_check.violations)
                stats['violations'].extend(drawdown_check.violations)
                logger.critical(f"Drawdown violations: {drawdown_check.violations}")
                
                # Create critical alert for drawdown violations
                repository.add_alert(
                    alert_type='risk_critical',
                    title='Drawdown Limit Exceeded - Circuit Breaker May Activate',
                    message=f"Violations: {', '.join(drawdown_check.violations)}",
                    metadata=drawdown_check.metadata
                )
            
            if drawdown_check.warnings:
                stats['warnings_found'] += len(drawdown_check.warnings)
                stats['warnings'].extend(drawdown_check.warnings)
                logger.warning(f"Drawdown warnings: {drawdown_check.warnings}")
            
            # Check 5: Circuit breaker status
            logger.info("Checking circuit breaker status...")
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': 5,
                    'total': 5,
                    'status': 'Checking circuit breaker status...',
                    'progress_pct': 100
                }
            )
            
            stats['circuit_breaker_active'] = risk_manager.circuit_breaker_active
            stats['checks_performed'] += 1
            
            if risk_manager.circuit_breaker_active:
                logger.critical(
                    f"CIRCUIT BREAKER ACTIVE: {risk_manager.circuit_breaker_reason} "
                    f"since {risk_manager.circuit_breaker_triggered_at}"
                )
                
                # Create critical alert
                repository.add_alert(
                    alert_type='circuit_breaker',
                    title='Circuit Breaker Active - Trading Halted',
                    message=f"Reason: {risk_manager.circuit_breaker_reason}",
                    metadata={
                        'triggered_at': risk_manager.circuit_breaker_triggered_at.isoformat(),
                        'reason': risk_manager.circuit_breaker_reason
                    }
                )
            
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Risk limits check completed: "
            f"{stats['checks_performed']} checks performed, "
            f"{stats['violations_found']} violations, "
            f"{stats['warnings_found']} warnings"
        )
        
        # Create summary alert if violations found
        if stats['violations_found'] > 0:
            repository.add_alert(
                alert_type='risk_summary',
                title='Risk Check Summary - Violations Found',
                message=f"Found {stats['violations_found']} violations and "
                        f"{stats['warnings_found']} warnings",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in check_risk_limits task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='risk_check_failed',
            title='Risk Limits Check Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.risk_management.update_circuit_breaker")
def update_circuit_breaker(self, manual_reset: bool = False) -> Dict[str, Any]:
    """
    Monitor portfolio drawdown and manage circuit breaker state.
    Triggers circuit breaker on excessive drawdown or resets after cooldown period.
    
    Args:
        manual_reset: If True, attempt manual reset of circuit breaker
    
    Returns:
        Dictionary with task results and circuit breaker status
    
    Example:
        >>> from workers.tasks.risk_management import update_circuit_breaker
        >>> # Check and auto-update
        >>> result = update_circuit_breaker.delay()
        >>> # Manual reset attempt
        >>> result = update_circuit_breaker.delay(manual_reset=True)
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting circuit breaker update task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'circuit_breaker_active': False,
        'circuit_breaker_triggered': False,
        'circuit_breaker_reset': False,
        'manual_reset_attempted': manual_reset,
        'reason': None,
        'drawdown_metrics': {},
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 0,
                'status': 'Checking circuit breaker state...'
            }
        )
        
        # Create risk manager with sync session
        with repository.get_session() as session:
            risk_manager = RiskManager(session)
            
            # Get current circuit breaker status
            stats['circuit_breaker_active'] = risk_manager.circuit_breaker_active
            
            if manual_reset:
                # Attempt manual reset
                logger.info("Attempting manual circuit breaker reset...")
                
                reset_success = risk_manager.reset_circuit_breaker(manual=True)
                stats['circuit_breaker_reset'] = reset_success
                
                if reset_success:
                    logger.info("Circuit breaker manually reset - trading resumed")
                    
                    repository.add_alert(
                        alert_type='circuit_breaker',
                        title='Circuit Breaker Manually Reset',
                        message='Trading has been manually resumed',
                        metadata=stats
                    )
                else:
                    logger.warning("Circuit breaker reset failed - cooldown or conditions not met")
                    
                    stats['error'] = 'Reset failed - cooldown not elapsed or conditions not met'
            
            else:
                # Check if circuit breaker should be triggered or auto-reset
                account_balance = settings.trading.capital
                
                # Check drawdown limits
                logger.info("Checking drawdown for circuit breaker triggers...")
                
                drawdown_check = risk_manager._check_drawdown_limits(account_balance)
                stats['drawdown_metrics'] = drawdown_check.metadata
                
                if not drawdown_check.passed:
                    # Circuit breaker should be/remain triggered
                    if not risk_manager.circuit_breaker_active:
                        logger.critical("Circuit breaker triggered by drawdown check!")
                        stats['circuit_breaker_triggered'] = True
                        stats['reason'] = ', '.join(drawdown_check.violations)
                    else:
                        logger.warning("Circuit breaker already active")
                        stats['reason'] = risk_manager.circuit_breaker_reason
                    
                    stats['circuit_breaker_active'] = True
                
                else:
                    # No violations - check if we can auto-reset
                    if risk_manager.circuit_breaker_active:
                        logger.info("Attempting auto-reset of circuit breaker...")
                        
                        reset_success = risk_manager.reset_circuit_breaker(manual=False)
                        stats['circuit_breaker_reset'] = reset_success
                        
                        if reset_success:
                            logger.info("Circuit breaker auto-reset - trading resumed")
                            
                            repository.add_alert(
                                alert_type='circuit_breaker',
                                title='Circuit Breaker Auto-Reset',
                                message='Trading has been automatically resumed after cooldown',
                                metadata=stats
                            )
                        else:
                            logger.warning("Auto-reset failed - manual reset may be required")
                    
                    stats['circuit_breaker_active'] = risk_manager.circuit_breaker_active
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Circuit breaker update completed: "
            f"Active: {stats['circuit_breaker_active']}, "
            f"Triggered: {stats['circuit_breaker_triggered']}, "
            f"Reset: {stats['circuit_breaker_reset']}"
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in update_circuit_breaker task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='circuit_breaker_failed',
            title='Circuit Breaker Update Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.risk_management.calculate_position_sizes")
def calculate_position_sizes(
    self,
    symbols: List[str],
    method: str = "fixed_fractional"
) -> Dict[str, Any]:
    """
    Pre-calculate position sizes for a list of symbols using specified sizing method.
    Useful for batch analysis and signal preparation.
    
    Args:
        symbols: List of symbols to calculate position sizes for
        method: Position sizing method (fixed_fractional, kelly_criterion, risk_parity, atr_based)
    
    Returns:
        Dictionary with task results and position size recommendations
    
    Example:
        >>> from workers.tasks.risk_management import calculate_position_sizes
        >>> result = calculate_position_sizes.delay(
        ...     symbols=['RELIANCE', 'TCS', 'INFY'],
        ...     method='kelly_criterion'
        ... )
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting position size calculation task for {len(symbols)} symbols")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'sizing_method': method,
        'symbols_requested': len(symbols),
        'symbols_processed': 0,
        'symbols_success': 0,
        'symbols_failed': 0,
        'recommendations': [],
        'errors': [],
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': len(symbols),
                'status': 'Calculating position sizes...'
            }
        )
        
        # Validate method
        valid_methods = ['fixed_fractional', 'kelly_criterion', 'risk_parity', 'atr_based']
        if method not in valid_methods:
            logger.error(f"Invalid sizing method: {method}, using fixed_fractional")
            method = 'fixed_fractional'
            stats['sizing_method'] = method
        
        # Get account balance
        account_balance = settings.trading.capital
        account_info = {'balance': account_balance}
        
        # Create risk manager with sync session
        with repository.get_session() as session:
            risk_manager = RiskManager(session)
            
            # Check circuit breaker
            if risk_manager.circuit_breaker_active:
                logger.error("Circuit breaker is active - cannot calculate position sizes")
                stats['status'] = 'failed'
                stats['error'] = f"Circuit breaker active: {risk_manager.circuit_breaker_reason}"
                return stats
            
            # Process each symbol
            for idx, symbol in enumerate(symbols, 1):
                try:
                    # Update progress
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'current': idx,
                            'total': len(symbols),
                            'status': f'Calculating position size for {symbol}...',
                            'symbol': symbol,
                            'progress_pct': (idx / len(symbols)) * 100
                        }
                    )
                    
                    logger.info(f"[{idx}/{len(symbols)}] Calculating position size for {symbol}")
                    
                    # Get symbol from database
                    symbol_obj = repository.get_symbol(symbol)
                    
                    if not symbol_obj:
                        logger.warning(f"Symbol not found: {symbol}")
                        stats['errors'].append(f"{symbol}: Symbol not found in database")
                        stats['symbols_failed'] += 1
                        stats['symbols_processed'] += 1
                        continue
                    
                    if not symbol_obj.is_active:
                        logger.warning(f"Symbol inactive: {symbol}")
                        stats['errors'].append(f"{symbol}: Symbol is inactive")
                        stats['symbols_failed'] += 1
                        stats['symbols_processed'] += 1
                        continue
                    
                    # Get latest price
                    from data.models import Timeframe
                    latest_price = repository.get_latest_price(symbol, Timeframe.DAILY)
                    
                    if not latest_price:
                        logger.warning(f"No price data for {symbol}")
                        stats['errors'].append(f"{symbol}: No price data available")
                        stats['symbols_failed'] += 1
                        stats['symbols_processed'] += 1
                        continue
                    
                    # Create sample signal data
                    # In production, this would come from actual signals
                    signal_data = {
                        'symbol': symbol,
                        'action': OrderAction.BUY,
                        'price': latest_price.close,
                        'stop_loss': 0,  # Will be calculated
                        'target': 0,  # Will be calculated
                    }
                    
                    # Get ATR for ATR-based sizing
                    symbol_data = {}
                    if method == 'atr_based':
                        # Get recent prices for ATR calculation
                        recent_prices = repository.get_price_history(
                            symbol=symbol,
                            timeframe=Timeframe.DAILY,
                            limit=20
                        )
                        
                        if recent_prices and len(recent_prices) >= 14:
                            # Calculate ATR (simplified - use proper TA library in production)
                            import numpy as np
                            
                            highs = np.array([p.high for p in recent_prices])
                            lows = np.array([p.low for p in recent_prices])
                            closes = np.array([p.close for p in recent_prices])
                            
                            tr = np.maximum(
                                highs - lows,
                                np.maximum(
                                    np.abs(highs - np.roll(closes, 1)),
                                    np.abs(lows - np.roll(closes, 1))
                                )
                            )
                            
                            atr = np.mean(tr[1:15])  # 14-period ATR
                            symbol_data['atr'] = atr
                            
                            logger.debug(f"{symbol}: ATR = {atr:.2f}")
                    
                    # Calculate position size
                    recommendation = risk_manager.calculate_position_size(
                        symbol=symbol,
                        signal_data=signal_data,
                        account_info=account_info,
                        method=method,
                        symbol_data=symbol_data
                    )
                    
                    # Convert to serializable dict
                    recommendation_dict = {
                        'symbol': recommendation.symbol,
                        'quantity': recommendation.quantity,
                        'entry_price': recommendation.entry_price,
                        'stop_loss': recommendation.stop_loss,
                        'target': recommendation.target,
                        'position_value': recommendation.position_value,
                        'risk_amount': recommendation.risk_amount,
                        'position_pct': recommendation.position_pct,
                        'sizing_method': recommendation.sizing_method,
                        'stop_method': recommendation.stop_method,
                        'risk_reward_ratio': recommendation.risk_reward_ratio,
                        'passed_checks': recommendation.passed_checks,
                        'warnings': recommendation.warnings,
                        'metadata': recommendation.metadata
                    }
                    
                    stats['recommendations'].append(recommendation_dict)
                    stats['symbols_success'] += 1
                    
                    logger.info(
                        f"{symbol}: Qty={recommendation.quantity}, "
                        f"Value=${recommendation.position_value:.2f}, "
                        f"Risk=${recommendation.risk_amount:.2f}, "
                        f"R:R={recommendation.risk_reward_ratio:.2f}, "
                        f"Passed={recommendation.passed_checks}"
                    )
                    
                except Exception as e:
                    logger.error(f"Error calculating position size for {symbol}: {e}", exc_info=True)
                    stats['symbols_failed'] += 1
                    stats['errors'].append(f"{symbol}: {str(e)}")
                
                finally:
                    stats['symbols_processed'] += 1
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        # Calculate summary statistics
        if stats['recommendations']:
            total_position_value = sum(r['position_value'] for r in stats['recommendations'])
            total_risk = sum(r['risk_amount'] for r in stats['recommendations'])
            avg_rr_ratio = sum(r['risk_reward_ratio'] for r in stats['recommendations']) / len(stats['recommendations'])
            
            stats['summary'] = {
                'total_position_value': total_position_value,
                'total_risk': total_risk,
                'total_risk_pct': (total_risk / account_balance) * 100.0,
                'avg_risk_reward_ratio': avg_rr_ratio,
                'positions_passed_checks': sum(1 for r in stats['recommendations'] if r['passed_checks'])
            }
            
            logger.info(
                f"Position sizing completed: "
                f"{stats['symbols_success']} success, {stats['symbols_failed']} failed, "
                f"Total Value: ${total_position_value:.2f}, "
                f"Total Risk: ${total_risk:.2f} ({stats['summary']['total_risk_pct']:.2f}%)"
            )
        else:
            logger.warning("No position size recommendations generated")
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in calculate_position_sizes task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='position_sizing_failed',
            title='Position Size Calculation Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats
