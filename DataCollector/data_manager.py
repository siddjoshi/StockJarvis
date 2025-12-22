# DataCollector/data_manager.py
"""
Unified data manager for coordinating multiple data providers.
Provides fallback logic, caching, data validation, and provider selection.
"""

import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any, Union
import time
from functools import lru_cache

from DataCollector.providers import (
    BaseDataProvider,
    YahooFinanceProvider,
    NSEProvider,
    BSEProvider,
    ZerodhaProvider,
    ProviderError,
    DataNotFoundError,
    AuthenticationError,
    get_provider,
)
from DataCollector.providers.base_provider import (
    SymbolInfo,
    Quote,
    DataInterval,
)
from data.models import Timeframe
from core.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


# Map our Timeframe enum to DataInterval
TIMEFRAME_TO_INTERVAL = {
    Timeframe.MINUTE_1: DataInterval.MINUTE_1,
    Timeframe.MINUTE_5: DataInterval.MINUTE_5,
    Timeframe.MINUTE_15: DataInterval.MINUTE_15,
    Timeframe.HOUR_1: DataInterval.HOUR_1,
    Timeframe.DAILY: DataInterval.DAILY,
    Timeframe.WEEKLY: DataInterval.WEEKLY,
    Timeframe.MONTHLY: DataInterval.MONTHLY,
}


class DataManager:
    """
    Unified data manager for market data.
    
    Coordinates multiple data providers with fallback logic,
    caching, and data validation.
    
    Features:
    - Provider fallback: Automatically tries secondary provider if primary fails
    - Data caching: Reduces redundant API calls
    - Data validation: Ensures data quality across providers
    - Cross-validation: Optionally validate data across multiple sources
    
    Example:
        >>> dm = DataManager(primary_provider="yahoo", fallback_provider="nse")
        >>> dm.connect()
        >>> 
        >>> # Fetch historical data
        >>> data = dm.get_historical_data("RELIANCE", "2024-01-01", "2024-12-20")
        >>> 
        >>> # Get current quote
        >>> quote = dm.get_quote("RELIANCE")
        >>> 
        >>> # Get symbol list
        >>> symbols = dm.get_symbols(fno_only=True)
        >>> 
        >>> dm.disconnect()
    
    Or with context manager:
        >>> with DataManager() as dm:
        ...     data = dm.get_historical_data("RELIANCE", "2024-01-01", "2024-12-20")
    """
    
    def __init__(
        self,
        primary_provider: str = None,
        fallback_provider: str = None,
        enable_cache: bool = True,
        cache_ttl: int = None,
        validate_data: bool = True
    ):
        """
        Initialize the data manager.
        
        Args:
            primary_provider: Primary provider name (yahoo, nse, bse, zerodha)
            fallback_provider: Fallback provider name
            enable_cache: Enable data caching
            cache_ttl: Cache time-to-live in seconds
            validate_data: Enable data validation
        """
        # Use settings or defaults with safe access
        app_settings = getattr(settings, 'app', None)
        
        if primary_provider:
            self.primary_provider_name = primary_provider
        elif app_settings and hasattr(app_settings, 'primary_data_provider'):
            self.primary_provider_name = app_settings.primary_data_provider
        else:
            self.primary_provider_name = 'yahoo'
        
        if fallback_provider:
            self.fallback_provider_name = fallback_provider
        elif app_settings and hasattr(app_settings, 'fallback_data_provider'):
            self.fallback_provider_name = app_settings.fallback_data_provider
        else:
            self.fallback_provider_name = 'yahoo'
        
        self.enable_cache = enable_cache
        
        if cache_ttl is not None:
            self.cache_ttl = cache_ttl
        elif app_settings and hasattr(app_settings, 'data_cache_ttl'):
            self.cache_ttl = app_settings.data_cache_ttl
        else:
            self.cache_ttl = 60
        
        self.validate_data = validate_data
        
        # Provider instances
        self._primary: Optional[BaseDataProvider] = None
        self._fallback: Optional[BaseDataProvider] = None
        
        # Quote cache: {symbol: (quote, timestamp)}
        self._quote_cache: Dict[str, tuple] = {}
        
        # Symbol list cache
        self._symbol_cache: Dict[str, List[SymbolInfo]] = {}
        self._symbol_cache_time: Optional[float] = None
        
        # Statistics
        self._stats = {
            "primary_requests": 0,
            "fallback_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "errors": 0,
        }
    
    @property
    def primary(self) -> BaseDataProvider:
        """Get primary provider instance."""
        if self._primary is None:
            self._primary = get_provider(self.primary_provider_name)
        return self._primary
    
    @property
    def fallback(self) -> Optional[BaseDataProvider]:
        """Get fallback provider instance."""
        if self._fallback is None and self.fallback_provider_name:
            if self.fallback_provider_name != self.primary_provider_name:
                self._fallback = get_provider(self.fallback_provider_name)
        return self._fallback
    
    def connect(self) -> bool:
        """
        Connect to data providers.
        
        Returns:
            bool: True if at least one provider connected successfully
        """
        primary_connected = False
        fallback_connected = False
        
        try:
            primary_connected = self.primary.connect()
            logger.info(f"Primary provider ({self.primary_provider_name}) connected: {primary_connected}")
        except Exception as e:
            logger.error(f"Failed to connect primary provider: {e}")
        
        if self.fallback:
            try:
                fallback_connected = self.fallback.connect()
                logger.info(f"Fallback provider ({self.fallback_provider_name}) connected: {fallback_connected}")
            except Exception as e:
                logger.warning(f"Failed to connect fallback provider: {e}")
        
        return primary_connected or fallback_connected
    
    def disconnect(self) -> None:
        """Disconnect from all providers."""
        if self._primary:
            try:
                self._primary.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting primary provider: {e}")
        
        if self._fallback:
            try:
                self._fallback.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting fallback provider: {e}")
        
        logger.info("Data manager disconnected")
    
    def _is_cache_valid(self, cache_time: float) -> bool:
        """Check if cache is still valid."""
        if not self.enable_cache:
            return False
        return (time.time() - cache_time) < self.cache_ttl
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date],
        timeframe: Timeframe = Timeframe.DAILY,
        use_fallback: bool = True
    ) -> pd.DataFrame:
        """
        Get historical OHLCV data for a symbol.
        
        Attempts primary provider first, falls back to secondary if enabled.
        
        Args:
            symbol: Stock symbol
            start_date: Start date (YYYY-MM-DD or date object)
            end_date: End date (YYYY-MM-DD or date object)
            timeframe: Data timeframe
            use_fallback: Whether to use fallback provider on failure
        
        Returns:
            pd.DataFrame: DataFrame with OHLCV data
        
        Raises:
            DataNotFoundError: If no data available from any provider
            ProviderError: If all providers fail
        """
        interval = TIMEFRAME_TO_INTERVAL.get(timeframe, DataInterval.DAILY)
        
        logger.info(f"Fetching historical data for {symbol} ({timeframe.value})")
        
        # Try primary provider
        try:
            self._stats["primary_requests"] += 1
            df = self.primary.get_historical_data(symbol, start_date, end_date, interval)
            
            if self.validate_data and not df.empty:
                df = self.primary.validate_data(df)
            
            logger.info(f"Got {len(df)} records from primary provider")
            return df
            
        except (DataNotFoundError, ProviderError, AuthenticationError) as e:
            logger.warning(f"Primary provider failed for {symbol}: {e}")
            self._stats["errors"] += 1
            
            if not use_fallback or not self.fallback:
                raise
        
        # Try fallback provider
        try:
            self._stats["fallback_requests"] += 1
            logger.info(f"Trying fallback provider for {symbol}")
            
            df = self.fallback.get_historical_data(symbol, start_date, end_date, interval)
            
            if self.validate_data and not df.empty:
                df = self.fallback.validate_data(df)
            
            logger.info(f"Got {len(df)} records from fallback provider")
            return df
            
        except Exception as e:
            logger.error(f"Fallback provider also failed for {symbol}: {e}")
            self._stats["errors"] += 1
            raise DataNotFoundError(f"No data available for {symbol} from any provider")
    
    def get_quote(
        self,
        symbol: str,
        use_cache: bool = True,
        use_fallback: bool = True
    ) -> Quote:
        """
        Get real-time quote for a symbol.
        
        Args:
            symbol: Stock symbol
            use_cache: Whether to use cached quote if available
            use_fallback: Whether to use fallback provider on failure
        
        Returns:
            Quote: Real-time price quote
        """
        # Check cache
        if use_cache and self.enable_cache and symbol in self._quote_cache:
            quote, cache_time = self._quote_cache[symbol]
            if self._is_cache_valid(cache_time):
                self._stats["cache_hits"] += 1
                logger.debug(f"Quote cache hit for {symbol}")
                return quote
        
        self._stats["cache_misses"] += 1
        
        # Try primary provider
        try:
            self._stats["primary_requests"] += 1
            quote = self.primary.get_quote(symbol)
            
            # Update cache
            if self.enable_cache:
                self._quote_cache[symbol] = (quote, time.time())
            
            return quote
            
        except (DataNotFoundError, ProviderError, AuthenticationError) as e:
            logger.warning(f"Primary provider failed for quote {symbol}: {e}")
            self._stats["errors"] += 1
            
            if not use_fallback or not self.fallback:
                raise
        
        # Try fallback
        try:
            self._stats["fallback_requests"] += 1
            quote = self.fallback.get_quote(symbol)
            
            if self.enable_cache:
                self._quote_cache[symbol] = (quote, time.time())
            
            return quote
            
        except Exception as e:
            logger.error(f"Fallback provider also failed for quote {symbol}: {e}")
            self._stats["errors"] += 1
            raise DataNotFoundError(f"No quote available for {symbol}")
    
    def get_quotes(
        self,
        symbols: List[str],
        use_cache: bool = True,
        use_fallback: bool = True
    ) -> Dict[str, Quote]:
        """
        Get quotes for multiple symbols.
        
        Args:
            symbols: List of stock symbols
            use_cache: Whether to use cached quotes
            use_fallback: Whether to use fallback provider
        
        Returns:
            Dict[str, Quote]: Dictionary mapping symbol to quote
        """
        quotes = {}
        symbols_to_fetch = []
        
        # Check cache first
        if use_cache and self.enable_cache:
            for symbol in symbols:
                if symbol in self._quote_cache:
                    quote, cache_time = self._quote_cache[symbol]
                    if self._is_cache_valid(cache_time):
                        quotes[symbol] = quote
                        self._stats["cache_hits"] += 1
                    else:
                        symbols_to_fetch.append(symbol)
                else:
                    symbols_to_fetch.append(symbol)
        else:
            symbols_to_fetch = symbols
        
        if not symbols_to_fetch:
            return quotes
        
        self._stats["cache_misses"] += len(symbols_to_fetch)
        
        # Fetch from provider
        try:
            self._stats["primary_requests"] += 1
            new_quotes = self.primary.get_quotes(symbols_to_fetch)
            
            for symbol, quote in new_quotes.items():
                quotes[symbol] = quote
                if self.enable_cache:
                    self._quote_cache[symbol] = (quote, time.time())
            
            # Check if any symbols are missing
            missing = set(symbols_to_fetch) - set(new_quotes.keys())
            
            if missing and use_fallback and self.fallback:
                self._stats["fallback_requests"] += 1
                fallback_quotes = self.fallback.get_quotes(list(missing))
                
                for symbol, quote in fallback_quotes.items():
                    quotes[symbol] = quote
                    if self.enable_cache:
                        self._quote_cache[symbol] = (quote, time.time())
            
        except Exception as e:
            logger.error(f"Failed to fetch quotes: {e}")
            self._stats["errors"] += 1
        
        return quotes
    
    def get_symbols(
        self,
        index: Optional[str] = None,
        fno_only: bool = False,
        use_cache: bool = True
    ) -> List[SymbolInfo]:
        """
        Get list of available symbols.
        
        Args:
            index: Filter by index (NIFTY50, NIFTY500)
            fno_only: Return only F&O symbols
            use_cache: Whether to use cached list
        
        Returns:
            List[SymbolInfo]: List of symbol information
        """
        cache_key = f"{index or 'all'}_{fno_only}"
        
        # Check cache
        if use_cache and self.enable_cache:
            if cache_key in self._symbol_cache:
                if self._symbol_cache_time and self._is_cache_valid(self._symbol_cache_time):
                    self._stats["cache_hits"] += 1
                    return self._symbol_cache[cache_key]
        
        self._stats["cache_misses"] += 1
        
        # Fetch from provider
        try:
            self._stats["primary_requests"] += 1
            symbols = self.primary.get_symbol_list(index=index, fno_only=fno_only)
            
            if self.enable_cache:
                self._symbol_cache[cache_key] = symbols
                self._symbol_cache_time = time.time()
            
            return symbols
            
        except Exception as e:
            logger.warning(f"Primary provider failed for symbols: {e}")
            self._stats["errors"] += 1
            
            if self.fallback:
                try:
                    self._stats["fallback_requests"] += 1
                    return self.fallback.get_symbol_list(index=index, fno_only=fno_only)
                except Exception as e2:
                    logger.error(f"Fallback also failed: {e2}")
            
            return []
    
    def cross_validate_data(
        self,
        symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date],
        tolerance: float = 0.02
    ) -> Dict[str, Any]:
        """
        Cross-validate data between primary and fallback providers.
        
        Compares closing prices from different sources to detect discrepancies.
        
        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            tolerance: Maximum allowed price difference (as percentage)
        
        Returns:
            Dict with validation results
        """
        if not self.fallback:
            return {"valid": True, "message": "No fallback provider for validation"}
        
        try:
            df_primary = self.primary.get_historical_data(
                symbol, start_date, end_date, DataInterval.DAILY
            )
            df_fallback = self.fallback.get_historical_data(
                symbol, start_date, end_date, DataInterval.DAILY
            )
            
            if df_primary.empty or df_fallback.empty:
                return {"valid": False, "message": "Empty data from one or both providers"}
            
            # Compare on common dates
            common_dates = df_primary.index.intersection(df_fallback.index)
            
            if len(common_dates) == 0:
                return {"valid": False, "message": "No common dates between providers"}
            
            # Compare close prices
            discrepancies = []
            for dt in common_dates:
                price1 = df_primary.loc[dt, 'close']
                price2 = df_fallback.loc[dt, 'close']
                
                diff_pct = abs(price1 - price2) / max(price1, price2)
                
                if diff_pct > tolerance:
                    discrepancies.append({
                        "date": str(dt),
                        "primary_price": price1,
                        "fallback_price": price2,
                        "diff_pct": round(diff_pct * 100, 2)
                    })
            
            return {
                "valid": len(discrepancies) == 0,
                "total_dates": len(common_dates),
                "discrepancy_count": len(discrepancies),
                "discrepancies": discrepancies[:10],  # Limit to first 10
                "tolerance_pct": tolerance * 100,
            }
            
        except Exception as e:
            return {"valid": False, "message": f"Validation failed: {e}"}
    
    def clear_cache(self) -> None:
        """Clear all caches."""
        self._quote_cache.clear()
        self._symbol_cache.clear()
        self._symbol_cache_time = None
        logger.info("Data manager cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get data manager statistics.
        
        Returns:
            Dict with usage statistics
        """
        total_requests = self._stats["primary_requests"] + self._stats["fallback_requests"]
        cache_requests = self._stats["cache_hits"] + self._stats["cache_misses"]
        
        return {
            **self._stats,
            "total_requests": total_requests,
            "fallback_rate": (
                self._stats["fallback_requests"] / total_requests * 100
                if total_requests > 0 else 0
            ),
            "cache_hit_rate": (
                self._stats["cache_hits"] / cache_requests * 100
                if cache_requests > 0 else 0
            ),
            "primary_provider": self.primary_provider_name,
            "fallback_provider": self.fallback_provider_name,
            "cache_enabled": self.enable_cache,
            "cache_ttl": self.cache_ttl,
        }
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
    
    def __repr__(self) -> str:
        return (
            f"DataManager("
            f"primary='{self.primary_provider_name}', "
            f"fallback='{self.fallback_provider_name}')"
        )


# Global data manager instance
_data_manager: Optional[DataManager] = None


def get_data_manager() -> DataManager:
    """
    Get or create global data manager instance.
    
    Returns:
        DataManager: Global data manager
    """
    global _data_manager
    
    if _data_manager is None:
        _data_manager = DataManager()
        _data_manager.connect()
    
    return _data_manager


def reset_data_manager() -> None:
    """Reset the global data manager instance."""
    global _data_manager
    
    if _data_manager is not None:
        try:
            _data_manager.disconnect()
        except Exception:
            pass
        _data_manager = None
