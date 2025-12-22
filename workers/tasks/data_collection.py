# workers/tasks/data_collection.py
"""
Celery tasks for data collection.
Handles EOD price data, intraday data, and symbol list updates.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import pandas as pd

from workers.celery_app import celery_app
from core.logger import get_logger
from data.repository import repository
from data.models import Timeframe, Symbol
from config import settings

logger = get_logger(__name__)


def _get_data_manager():
    """Get data manager instance (lazy import to avoid circular imports)."""
    from DataCollector.data_manager import get_data_manager
    return get_data_manager()


@celery_app.task(bind=True, name="workers.tasks.data_collection.collect_daily_data")
def collect_daily_data(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Fetch end-of-day price data for symbols and update database.
    
    Uses configured data providers (Yahoo Finance, NSE, etc.) to fetch
    historical daily OHLCV data and store in the prices table.
    
    Args:
        symbols: List of symbols to update (uses all F&O symbols if None)
    
    Returns:
        Dictionary with task results and statistics
    
    Example:
        >>> from workers.tasks.data_collection import collect_daily_data
        >>> result = collect_daily_data.delay(['RELIANCE', 'TCS', 'INFY'])
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting daily data collection task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'symbols_requested': len(symbols) if symbols else 0,
        'symbols_processed': 0,
        'symbols_success': 0,
        'symbols_failed': 0,
        'total_records_added': 0,
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
                'status': 'Initializing data collection...'
            }
        )
        
        # Get data manager
        data_manager = _get_data_manager()
        
        # Get symbols to process
        if symbols:
            # Validate symbols
            symbol_objects = []
            for symbol in symbols:
                sym_obj = repository.get_symbol(symbol)
                if sym_obj and sym_obj.is_active:
                    symbol_objects.append(sym_obj)
                else:
                    logger.warning(f"Symbol not found or inactive: {symbol}")
                    stats['errors'].append(f"Invalid symbol: {symbol}")
        else:
            # Use all F&O symbols
            symbol_objects = repository.get_fno_symbols()
            logger.info(f"No symbols specified, using {len(symbol_objects)} F&O symbols")
        
        stats['symbols_requested'] = len(symbol_objects)
        
        if not symbol_objects:
            logger.error("No valid symbols to process")
            stats['status'] = 'failed'
            stats['error'] = 'No valid symbols to process'
            return stats
        
        # Calculate date range (last 30 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        logger.info(f"Collecting data from {start_date.date()} to {end_date.date()}")
        
        # Process each symbol
        for idx, symbol_obj in enumerate(symbol_objects, 1):
            symbol = symbol_obj.symbol
            
            try:
                # Update progress
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': idx,
                        'total': len(symbol_objects),
                        'status': f'Processing {symbol}...',
                        'symbol': symbol,
                        'progress_pct': (idx / len(symbol_objects)) * 100
                    }
                )
                
                logger.info(f"[{idx}/{len(symbol_objects)}] Fetching data for {symbol}")
                
                # Fetch data using data manager
                try:
                    df = data_manager.get_historical_data(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date,
                        timeframe=Timeframe.DAILY
                    )
                    
                    if not df.empty:
                        # Store in database
                        repository.add_prices_bulk(symbol, df, Timeframe.DAILY)
                        stats['total_records_added'] += len(df)
                        stats['symbols_success'] += 1
                        logger.info(f"{symbol}: Added {len(df)} daily records")
                    else:
                        logger.warning(f"{symbol}: No data returned from provider")
                        stats['errors'].append(f"{symbol}: No data available")
                        
                except Exception as fetch_error:
                    logger.warning(f"{symbol}: Data fetch failed - {fetch_error}")
                    
                    # Check if recent data exists (fallback behavior)
                    latest_price = repository.get_latest_price(symbol, Timeframe.DAILY)
                    
                    if latest_price:
                        days_old = (datetime.now() - latest_price.timestamp).days
                        
                        if days_old > 1:
                            logger.warning(
                                f"{symbol}: Latest data is {days_old} days old"
                            )
                            stats['errors'].append(
                                f"{symbol}: Data outdated ({days_old} days old) - fetch error: {fetch_error}"
                            )
                        else:
                            logger.info(f"{symbol}: Data is up-to-date (from cache)")
                            stats['symbols_success'] += 1
                    else:
                        logger.warning(f"{symbol}: No price data found")
                        stats['errors'].append(f"{symbol}: No data - {fetch_error}")
                
                stats['symbols_processed'] += 1
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)
                stats['symbols_failed'] += 1
                stats['errors'].append(f"{symbol}: {str(e)}")
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Daily data collection completed: "
            f"{stats['symbols_success']} success, {stats['symbols_failed']} failed, "
            f"{stats['total_records_added']} records added"
        )
        
        # Create alert if there were failures
        if stats['symbols_failed'] > 0:
            repository.add_alert(
                alert_type='data_collection',
                title='Daily Data Collection Completed with Errors',
                message=f"Processed {stats['symbols_processed']} symbols: "
                        f"{stats['symbols_success']} success, {stats['symbols_failed']} failed",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in collect_daily_data task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        # Create alert
        repository.add_alert(
            alert_type='data_collection',
            title='Daily Data Collection Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.data_collection.collect_intraday_data")
def collect_intraday_data(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Fetch 1-minute intraday price data for symbols.
    
    Args:
        symbols: List of symbols to update (uses all active F&O symbols if None)
    
    Returns:
        Dictionary with task results and statistics
    
    Example:
        >>> from workers.tasks.data_collection import collect_intraday_data
        >>> result = collect_intraday_data.delay(['NIFTY', 'BANKNIFTY'])
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting intraday data collection task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'symbols_requested': len(symbols) if symbols else 0,
        'symbols_processed': 0,
        'symbols_success': 0,
        'symbols_failed': 0,
        'total_records_added': 0,
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
                'status': 'Initializing intraday data collection...'
            }
        )
        
        # Get data manager
        data_manager = _get_data_manager()
        
        # Get symbols to process
        if symbols:
            symbol_objects = []
            for symbol in symbols:
                sym_obj = repository.get_symbol(symbol)
                if sym_obj and sym_obj.is_active:
                    symbol_objects.append(sym_obj)
                else:
                    logger.warning(f"Symbol not found or inactive: {symbol}")
                    stats['errors'].append(f"Invalid symbol: {symbol}")
        else:
            # Use top 50 F&O stocks for intraday
            all_fno = repository.get_fno_symbols()
            symbol_objects = all_fno[:50] if len(all_fno) > 50 else all_fno
            logger.info(f"No symbols specified, using top {len(symbol_objects)} F&O symbols")
        
        stats['symbols_requested'] = len(symbol_objects)
        
        if not symbol_objects:
            logger.error("No valid symbols to process")
            stats['status'] = 'failed'
            stats['error'] = 'No valid symbols to process'
            return stats
        
        # Intraday data: Today's data only
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        logger.info(f"Collecting intraday data for {today.date()}")
        
        # Process each symbol
        for idx, symbol_obj in enumerate(symbol_objects, 1):
            symbol = symbol_obj.symbol
            
            try:
                # Update progress
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': idx,
                        'total': len(symbol_objects),
                        'status': f'Processing {symbol}...',
                        'symbol': symbol,
                        'progress_pct': (idx / len(symbol_objects)) * 100
                    }
                )
                
                logger.info(f"[{idx}/{len(symbol_objects)}] Fetching intraday data for {symbol}")
                
                # Fetch intraday data
                try:
                    df = data_manager.get_historical_data(
                        symbol=symbol,
                        start_date=today,
                        end_date=datetime.now(),
                        timeframe=Timeframe.MINUTE_1
                    )
                    
                    if not df.empty:
                        repository.add_prices_bulk(symbol, df, Timeframe.MINUTE_1)
                        stats['total_records_added'] += len(df)
                        stats['symbols_success'] += 1
                        logger.info(f"{symbol}: Added {len(df)} 1-min records")
                    else:
                        logger.warning(f"{symbol}: No intraday data available")
                        stats['errors'].append(f"{symbol}: No intraday data")
                        
                except Exception as fetch_error:
                    logger.warning(f"{symbol}: Intraday fetch failed - {fetch_error}")
                    stats['errors'].append(f"{symbol}: {fetch_error}")
                
                stats['symbols_processed'] += 1
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)
                stats['symbols_failed'] += 1
                stats['errors'].append(f"{symbol}: {str(e)}")
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Intraday data collection completed: "
            f"{stats['symbols_success']} success, {stats['symbols_failed']} failed"
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in collect_intraday_data task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='data_collection',
            title='Intraday Data Collection Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.data_collection.update_symbol_list")
def update_symbol_list(self, exchange: str = "NSE") -> Dict[str, Any]:
    """
    Sync symbols from exchange (NSE/BSE) and update database.
    
    Fetches the latest symbol list from the data provider and updates
    the symbols table with new, updated, and deactivated symbols.
    
    Args:
        exchange: Exchange name (NSE or BSE)
    
    Returns:
        Dictionary with task results and statistics
    
    Example:
        >>> from workers.tasks.data_collection import update_symbol_list
        >>> result = update_symbol_list.delay(exchange="NSE")
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting symbol list update task for {exchange}")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'exchange': exchange,
        'start_time': datetime.utcnow().isoformat(),
        'symbols_before': 0,
        'symbols_after': 0,
        'symbols_added': 0,
        'symbols_updated': 0,
        'symbols_deactivated': 0,
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
                'status': f'Fetching symbol list from {exchange}...'
            }
        )
        
        # Get current symbols count
        current_symbols = repository.get_all_symbols(active_only=False)
        stats['symbols_before'] = len(current_symbols)
        
        logger.info(f"Current symbols in database: {stats['symbols_before']}")
        
        # Get data manager and fetch symbols
        data_manager = _get_data_manager()
        
        try:
            exchange_symbols = data_manager.get_symbols(fno_only=True)
            logger.info(f"Fetched {len(exchange_symbols)} symbols from provider")
        except Exception as e:
            logger.warning(f"Provider symbol fetch failed: {e}, using empty list")
            exchange_symbols = []
        
        exchange_symbol_set = {s.symbol for s in exchange_symbols}
        
        # Process fetched symbols
        for symbol_info in exchange_symbols:
            try:
                existing = repository.get_symbol(symbol_info.symbol)
                
                if not existing:
                    # Add new symbol
                    repository.add_symbol(
                        symbol=symbol_info.symbol,
                        company_name=symbol_info.company_name,
                        exchange=exchange,
                        is_fno=symbol_info.is_fno,
                        is_active=True,
                        sector=symbol_info.sector,
                        industry=symbol_info.industry,
                        isin=symbol_info.isin
                    )
                    stats['symbols_added'] += 1
                    logger.info(f"Added new symbol: {symbol_info.symbol}")
                else:
                    # Update existing symbol if needed
                    if not existing.is_active:
                        with repository.get_session() as session:
                            sym = session.query(Symbol).filter(
                                Symbol.symbol == symbol_info.symbol
                            ).first()
                            if sym:
                                sym.is_active = True
                                sym.updated_at = datetime.utcnow()
                        stats['symbols_updated'] += 1
                        logger.info(f"Reactivated symbol: {symbol_info.symbol}")
            except Exception as e:
                logger.warning(f"Error processing symbol {symbol_info.symbol}: {e}")
                stats['errors'].append(f"{symbol_info.symbol}: {e}")
        
        # Deactivate symbols not in exchange list (only if we got symbols from provider)
        if exchange_symbols:
            for symbol_obj in current_symbols:
                if symbol_obj.symbol not in exchange_symbol_set and symbol_obj.is_active:
                    try:
                        with repository.get_session() as session:
                            sym = session.query(Symbol).filter(
                                Symbol.symbol == symbol_obj.symbol
                            ).first()
                            if sym:
                                sym.is_active = False
                                sym.updated_at = datetime.utcnow()
                        stats['symbols_deactivated'] += 1
                        logger.info(f"Deactivated symbol: {symbol_obj.symbol}")
                    except Exception as e:
                        logger.warning(f"Error deactivating {symbol_obj.symbol}: {e}")
        
        # Get updated count
        updated_symbols = repository.get_all_symbols(active_only=False)
        stats['symbols_after'] = len(updated_symbols)
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Symbol list update completed: "
            f"{stats['symbols_added']} added, "
            f"{stats['symbols_updated']} updated, "
            f"{stats['symbols_deactivated']} deactivated"
        )
        
        # Create alert if significant changes
        if stats['symbols_added'] > 10 or stats['symbols_deactivated'] > 10:
            repository.add_alert(
                alert_type='symbol_update',
                title=f'Symbol List Updated - {exchange}',
                message=f"Added: {stats['symbols_added']}, "
                        f"Updated: {stats['symbols_updated']}, "
                        f"Deactivated: {stats['symbols_deactivated']}",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in update_symbol_list task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='symbol_update',
            title=f'Symbol List Update Failed - {exchange}',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.data_collection.backfill_historical_data")
def backfill_historical_data(
    self,
    symbols: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Backfill historical data for symbols.
    
    Downloads historical data from the configured start date to fill gaps
    in the price data.
    
    Args:
        symbols: List of symbols to backfill (uses F&O symbols if None)
        start_date: Start date (uses config default if None)
        end_date: End date (uses today if None)
    
    Returns:
        Dictionary with task results and statistics
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting historical data backfill task")
    
    # Parse dates
    start_dt = datetime.strptime(
        start_date or settings.app.historical_data_start_date,
        "%Y-%m-%d"
    )
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'date_range': f"{start_dt.date()} to {end_dt.date()}",
        'symbols_requested': 0,
        'symbols_processed': 0,
        'symbols_success': 0,
        'symbols_failed': 0,
        'total_records_added': 0,
        'errors': [],
        'status': 'in_progress'
    }
    
    try:
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 0,
                'status': 'Initializing historical data backfill...'
            }
        )
        
        # Get data manager
        data_manager = _get_data_manager()
        
        # Get symbols
        if symbols:
            symbol_objects = []
            for symbol in symbols:
                sym_obj = repository.get_symbol(symbol)
                if sym_obj:
                    symbol_objects.append(sym_obj)
        else:
            symbol_objects = repository.get_fno_symbols()
        
        stats['symbols_requested'] = len(symbol_objects)
        
        if not symbol_objects:
            stats['status'] = 'failed'
            stats['error'] = 'No symbols to process'
            return stats
        
        logger.info(f"Backfilling data for {len(symbol_objects)} symbols")
        
        for idx, symbol_obj in enumerate(symbol_objects, 1):
            symbol = symbol_obj.symbol
            
            try:
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': idx,
                        'total': len(symbol_objects),
                        'status': f'Backfilling {symbol}...',
                        'symbol': symbol,
                        'progress_pct': (idx / len(symbol_objects)) * 100
                    }
                )
                
                logger.info(f"[{idx}/{len(symbol_objects)}] Backfilling {symbol}")
                
                df = data_manager.get_historical_data(
                    symbol=symbol,
                    start_date=start_dt,
                    end_date=end_dt,
                    timeframe=Timeframe.DAILY
                )
                
                if not df.empty:
                    repository.add_prices_bulk(symbol, df, Timeframe.DAILY)
                    stats['total_records_added'] += len(df)
                    stats['symbols_success'] += 1
                    logger.info(f"{symbol}: Added {len(df)} historical records")
                else:
                    stats['errors'].append(f"{symbol}: No data")
                    
                stats['symbols_processed'] += 1
                
            except Exception as e:
                logger.error(f"Error backfilling {symbol}: {e}")
                stats['symbols_failed'] += 1
                stats['errors'].append(f"{symbol}: {str(e)}")
        
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Historical backfill completed: "
            f"{stats['symbols_success']} success, "
            f"{stats['total_records_added']} records"
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in backfill task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        return stats
