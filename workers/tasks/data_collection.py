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


@celery_app.task(bind=True, name="workers.tasks.data_collection.collect_daily_data")
def collect_daily_data(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Fetch end-of-day price data for symbols and update database.
    
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
                
                # TODO: Replace with actual data fetching from your data source
                # This is a placeholder - integrate with your data provider (NSE, Zerodha, etc.)
                # Example integrations:
                # - NSE India API
                # - Zerodha Historical API
                # - Yahoo Finance
                # - Alpha Vantage
                # - Quandl
                
                # For now, check if recent data exists
                latest_price = repository.get_latest_price(symbol, Timeframe.DAILY)
                
                if latest_price:
                    days_old = (datetime.now() - latest_price.timestamp).days
                    
                    if days_old > 1:
                        logger.warning(
                            f"{symbol}: Latest data is {days_old} days old, "
                            f"needs update from data provider"
                        )
                        stats['errors'].append(
                            f"{symbol}: Data outdated ({days_old} days old) - "
                            f"integrate data provider"
                        )
                    else:
                        logger.info(f"{symbol}: Data is up-to-date")
                        stats['symbols_success'] += 1
                else:
                    logger.warning(f"{symbol}: No price data found - needs initial data load")
                    stats['errors'].append(f"{symbol}: No data - integrate data provider")
                
                stats['symbols_processed'] += 1
                
                # Placeholder for actual data fetching:
                """
                # Example with Zerodha:
                from BrokerModules.Zerodha import ZerodhaAPI
                zerodha = ZerodhaAPI()
                data = zerodha.get_historical_data(
                    symbol=symbol,
                    from_date=start_date,
                    to_date=end_date,
                    interval='day'
                )
                
                if not data.empty:
                    repository.add_prices_bulk(symbol, data, Timeframe.DAILY)
                    stats['total_records_added'] += len(data)
                    stats['symbols_success'] += 1
                    logger.info(f"{symbol}: Added {len(data)} daily records")
                """
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)
                stats['symbols_failed'] += 1
                stats['errors'].append(f"{symbol}: {str(e)}")
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Daily data collection completed: "
            f"{stats['symbols_success']} success, {stats['symbols_failed']} failed"
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
                
                # TODO: Replace with actual intraday data fetching
                # Example integrations:
                # - Zerodha WebSocket for live data
                # - Zerodha Historical API for 1-minute candles
                # - NSE Real-time feed
                
                # Placeholder logging
                logger.info(f"{symbol}: Intraday data collection requires live feed integration")
                stats['errors'].append(
                    f"{symbol}: Intraday data requires live feed - integrate WebSocket/API"
                )
                
                stats['symbols_processed'] += 1
                
                # Placeholder for actual implementation:
                """
                # Example with Zerodha:
                from BrokerModules.Zerodha import ZerodhaAPI
                zerodha = ZerodhaAPI()
                data = zerodha.get_historical_data(
                    symbol=symbol,
                    from_date=today,
                    to_date=datetime.now(),
                    interval='minute'
                )
                
                if not data.empty:
                    repository.add_prices_bulk(symbol, data, Timeframe.MINUTE_1)
                    stats['total_records_added'] += len(data)
                    stats['symbols_success'] += 1
                    logger.info(f"{symbol}: Added {len(data)} 1-min records")
                """
                
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
        
        # TODO: Replace with actual exchange API integration
        # Example integrations:
        # - NSE India API for equity list
        # - BSE API
        # - Download CSV from NSE/BSE websites
        # - Zerodha instruments list
        
        # Placeholder implementation
        logger.warning(
            f"Symbol list update requires integration with {exchange} API or data source"
        )
        stats['errors'].append(
            f"Symbol list update not implemented - needs {exchange} integration"
        )
        
        # Placeholder for actual implementation:
        """
        # Example with NSE:
        import requests
        
        # Fetch equity list from NSE
        url = "https://www.nseindia.com/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O"
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json'
        }
        response = requests.get(url, headers=headers)
        data = response.json()
        
        # Process symbols
        exchange_symbols = set()
        for item in data.get('data', []):
            symbol = item['symbol']
            company_name = item.get('companyName', symbol)
            exchange_symbols.add(symbol)
            
            # Check if symbol exists
            existing = repository.get_symbol(symbol)
            
            if not existing:
                # Add new symbol
                repository.add_symbol(
                    symbol=symbol,
                    company_name=company_name,
                    exchange=exchange,
                    is_fno=True,
                    is_active=True
                )
                stats['symbols_added'] += 1
                logger.info(f"Added new symbol: {symbol}")
            else:
                # Update existing symbol
                if not existing.is_active:
                    with repository.get_session() as session:
                        existing.is_active = True
                        existing.updated_at = datetime.utcnow()
                        stats['symbols_updated'] += 1
        
        # Deactivate symbols not in exchange list
        for symbol_obj in current_symbols:
            if symbol_obj.symbol not in exchange_symbols and symbol_obj.is_active:
                with repository.get_session() as session:
                    symbol_obj.is_active = False
                    symbol_obj.updated_at = datetime.utcnow()
                    stats['symbols_deactivated'] += 1
                    logger.info(f"Deactivated symbol: {symbol_obj.symbol}")
        """
        
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
