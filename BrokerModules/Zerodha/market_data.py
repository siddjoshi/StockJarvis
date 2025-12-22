# BrokerModules/Zerodha/market_data.py
"""
Market data module for Zerodha Kite Connect.
Provides market quotes, OHLC data, and historical data download.
"""

from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
import threading
import time

from BrokerModules.base_broker import (
    QuoteData,
    ExchangeType,
    BrokerError,
)
from BrokerModules.Zerodha.kite_client import KiteClient
from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class InstrumentInfo:
    """Instrument information."""
    instrument_token: int
    exchange_token: int
    tradingsymbol: str
    name: str
    exchange: str
    segment: str
    instrument_type: str
    lot_size: int
    tick_size: float
    expiry: Optional[datetime] = None
    strike: Optional[float] = None


class QuoteCache:
    """
    Simple in-memory cache for quotes.
    Reduces API calls for frequently requested symbols.
    """
    
    def __init__(self, ttl_seconds: int = 5):
        """
        Initialize quote cache.
        
        Args:
            ttl_seconds: Time-to-live for cached quotes
        """
        self._cache: Dict[str, tuple] = {}  # key -> (data, timestamp)
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        with self._lock:
            if key in self._cache:
                data, timestamp = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    return data
                else:
                    del self._cache[key]
            return None
    
    def set(self, key: str, value: Any) -> None:
        """Set cached value."""
        with self._lock:
            self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """Clear all cached values."""
        with self._lock:
            self._cache.clear()
    
    def remove(self, key: str) -> None:
        """Remove specific key from cache."""
        with self._lock:
            self._cache.pop(key, None)


class MarketDataManager:
    """
    High-level market data management for Zerodha.
    
    Provides market data operations with:
    - Quote fetching with caching
    - OHLC and LTP data
    - Historical data download
    - Instrument information
    
    Example:
        >>> from BrokerModules.Zerodha.kite_client import KiteClient
        >>> client = KiteClient()
        >>> # ... authenticate client
        >>> 
        >>> market_data = MarketDataManager(client)
        >>> 
        >>> # Get quote
        >>> quote = market_data.get_quote("RELIANCE", ExchangeType.NSE)
        >>> print(f"Last Price: {quote.last_price}")
        >>> 
        >>> # Get historical data
        >>> data = market_data.get_historical_data(
        ...     symbol="RELIANCE",
        ...     exchange=ExchangeType.NSE,
        ...     days_back=30
        ... )
    """
    
    # Interval mappings
    INTERVAL_MAP = {
        "minute": "minute",
        "3minute": "3minute",
        "5minute": "5minute",
        "10minute": "10minute",
        "15minute": "15minute",
        "30minute": "30minute",
        "60minute": "60minute",
        "day": "day",
        "week": "week",
        "month": "month",
    }
    
    def __init__(self, client: KiteClient, cache_ttl: int = 5):
        """
        Initialize market data manager.
        
        Args:
            client: Authenticated KiteClient instance
            cache_ttl: Cache time-to-live in seconds
        """
        self._client = client
        self._quote_cache = QuoteCache(ttl_seconds=cache_ttl)
        self._instruments_cache: Dict[str, List[InstrumentInfo]] = {}
        
        logger.info(f"MarketDataManager initialized (cache_ttl={cache_ttl}s)")
    
    # ==========================================================================
    # Quote Operations
    # ==========================================================================
    
    def get_quote(
        self,
        symbol: str,
        exchange: ExchangeType,
        use_cache: bool = True
    ) -> QuoteData:
        """
        Get current market quote for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            use_cache: Whether to use cached data
        
        Returns:
            QuoteData: Current market quote
        
        Example:
            >>> quote = market_data.get_quote("RELIANCE", ExchangeType.NSE)
            >>> print(f"Last: {quote.last_price}, Bid: {quote.bid_price}")
        """
        cache_key = f"{exchange.value}:{symbol}"
        
        if use_cache:
            cached = self._quote_cache.get(cache_key)
            if cached:
                return cached
        
        quote = self._client.get_quote(symbol, exchange)
        
        if use_cache:
            self._quote_cache.set(cache_key, quote)
        
        return quote
    
    def get_quotes(
        self,
        symbols: List[tuple],
        use_cache: bool = True
    ) -> Dict[str, QuoteData]:
        """
        Get quotes for multiple symbols.
        
        Args:
            symbols: List of (symbol, exchange) tuples
            use_cache: Whether to use cached data
        
        Returns:
            Dict[str, QuoteData]: Symbol -> Quote mapping
        
        Example:
            >>> symbols = [
            ...     ("RELIANCE", ExchangeType.NSE),
            ...     ("TCS", ExchangeType.NSE)
            ... ]
            >>> quotes = market_data.get_quotes(symbols)
        """
        result = {}
        symbols_to_fetch = []
        
        # Check cache first
        if use_cache:
            for symbol, exchange in symbols:
                cache_key = f"{exchange.value}:{symbol}"
                cached = self._quote_cache.get(cache_key)
                if cached:
                    result[symbol] = cached
                else:
                    symbols_to_fetch.append((symbol, exchange))
        else:
            symbols_to_fetch = symbols
        
        # Fetch remaining symbols
        for symbol, exchange in symbols_to_fetch:
            try:
                quote = self._client.get_quote(symbol, exchange)
                result[symbol] = quote
                
                if use_cache:
                    cache_key = f"{exchange.value}:{symbol}"
                    self._quote_cache.set(cache_key, quote)
            except Exception as e:
                logger.error(f"Failed to get quote for {symbol}: {e}")
        
        return result
    
    def get_ltp(
        self,
        symbol: str,
        exchange: ExchangeType
    ) -> float:
        """
        Get Last Traded Price for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
        
        Returns:
            float: Last traded price
        
        Example:
            >>> ltp = market_data.get_ltp("RELIANCE", ExchangeType.NSE)
            >>> print(f"LTP: {ltp}")
        """
        result = self._client.get_ltp([(symbol, exchange)])
        return result.get(symbol, 0.0)
    
    def get_multiple_ltp(
        self,
        symbols: List[tuple]
    ) -> Dict[str, float]:
        """
        Get LTP for multiple symbols.
        
        Args:
            symbols: List of (symbol, exchange) tuples
        
        Returns:
            Dict[str, float]: Symbol -> LTP mapping
        """
        return self._client.get_ltp(symbols)
    
    def get_ohlc(
        self,
        symbol: str,
        exchange: ExchangeType
    ) -> Dict[str, float]:
        """
        Get OHLC data for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
        
        Returns:
            Dict with open, high, low, close, last_price
        
        Example:
            >>> ohlc = market_data.get_ohlc("RELIANCE", ExchangeType.NSE)
            >>> print(f"Open: {ohlc['open']}, High: {ohlc['high']}")
        """
        result = self._client.get_ohlc([(symbol, exchange)])
        return result.get(symbol, {})
    
    def get_multiple_ohlc(
        self,
        symbols: List[tuple]
    ) -> Dict[str, Dict[str, float]]:
        """
        Get OHLC data for multiple symbols.
        
        Args:
            symbols: List of (symbol, exchange) tuples
        
        Returns:
            Dict[str, Dict]: Symbol -> OHLC mapping
        """
        return self._client.get_ohlc(symbols)
    
    # ==========================================================================
    # Historical Data
    # ==========================================================================
    
    def get_historical_data(
        self,
        symbol: str,
        exchange: ExchangeType,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        days_back: int = 30,
        interval: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV data.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            from_date: Start date (optional)
            to_date: End date (optional, defaults to today)
            days_back: Days to look back if from_date not provided
            interval: Data interval (minute, day, etc.)
        
        Returns:
            List[Dict]: Historical OHLCV data
        
        Example:
            >>> # Last 30 days of daily data
            >>> data = market_data.get_historical_data(
            ...     symbol="RELIANCE",
            ...     exchange=ExchangeType.NSE,
            ...     days_back=30,
            ...     interval="day"
            ... )
            >>> 
            >>> # Specific date range
            >>> data = market_data.get_historical_data(
            ...     symbol="RELIANCE",
            ...     exchange=ExchangeType.NSE,
            ...     from_date=datetime(2024, 1, 1),
            ...     to_date=datetime(2024, 1, 31),
            ...     interval="day"
            ... )
        """
        if interval not in self.INTERVAL_MAP:
            raise BrokerError(
                message=f"Invalid interval: {interval}. Valid: {list(self.INTERVAL_MAP.keys())}",
                code="INVALID_INTERVAL"
            )
        
        if to_date is None:
            to_date = datetime.now()
        
        if from_date is None:
            from_date = to_date - timedelta(days=days_back)
        
        return self._client.get_historical_data(
            symbol=symbol,
            exchange=exchange,
            from_date=from_date,
            to_date=to_date,
            interval=self.INTERVAL_MAP[interval]
        )
    
    def get_intraday_data(
        self,
        symbol: str,
        exchange: ExchangeType,
        interval: str = "minute"
    ) -> List[Dict[str, Any]]:
        """
        Get intraday OHLCV data for today.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            interval: Data interval (minute, 5minute, etc.)
        
        Returns:
            List[Dict]: Intraday OHLCV data
        
        Example:
            >>> data = market_data.get_intraday_data(
            ...     symbol="RELIANCE",
            ...     exchange=ExchangeType.NSE,
            ...     interval="5minute"
            ... )
        """
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        return self.get_historical_data(
            symbol=symbol,
            exchange=exchange,
            from_date=today,
            to_date=datetime.now(),
            interval=interval
        )
    
    # ==========================================================================
    # Instrument Operations
    # ==========================================================================
    
    def get_instruments(
        self,
        exchange: Optional[ExchangeType] = None,
        refresh: bool = False
    ) -> List[InstrumentInfo]:
        """
        Get list of tradeable instruments.
        
        Args:
            exchange: Filter by exchange (optional)
            refresh: Force refresh from API
        
        Returns:
            List[InstrumentInfo]: List of instruments
        
        Example:
            >>> instruments = market_data.get_instruments(ExchangeType.NSE)
            >>> for inst in instruments[:10]:
            ...     print(f"{inst.tradingsymbol}: {inst.name}")
        """
        cache_key = exchange.value if exchange else "ALL"
        
        if not refresh and cache_key in self._instruments_cache:
            return self._instruments_cache[cache_key]
        
        raw_instruments = self._client.get_instruments(exchange)
        
        instruments = [
            self._parse_instrument(inst)
            for inst in raw_instruments
        ]
        
        self._instruments_cache[cache_key] = instruments
        
        return instruments
    
    def _parse_instrument(self, data: Dict[str, Any]) -> InstrumentInfo:
        """Parse raw instrument data to InstrumentInfo."""
        # Safely extract and validate numeric fields
        def safe_int(value, default: int = 0) -> int:
            """Safely convert value to int."""
            if value is None:
                return default
            try:
                return int(value)
            except (ValueError, TypeError):
                return default
        
        def safe_float(value, default: float = 0.0) -> float:
            """Safely convert value to float."""
            if value is None:
                return default
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        
        return InstrumentInfo(
            instrument_token=safe_int(data.get("instrument_token"), 0),
            exchange_token=safe_int(data.get("exchange_token"), 0),
            tradingsymbol=str(data.get("tradingsymbol", "")),
            name=str(data.get("name", "")),
            exchange=str(data.get("exchange", "")),
            segment=str(data.get("segment", "")),
            instrument_type=str(data.get("instrument_type", "")),
            lot_size=safe_int(data.get("lot_size"), 1),
            tick_size=safe_float(data.get("tick_size"), 0.05),
            expiry=data.get("expiry"),
            strike=safe_float(data.get("strike")) if data.get("strike") is not None else None
        )
    
    def get_instrument_token(
        self,
        symbol: str,
        exchange: ExchangeType
    ) -> Optional[int]:
        """
        Get instrument token for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
        
        Returns:
            int or None: Instrument token
        """
        instruments = self.get_instruments(exchange)
        
        for inst in instruments:
            if inst.tradingsymbol == symbol.upper():
                return inst.instrument_token
        
        return None
    
    def search_instruments(
        self,
        query: str,
        exchange: Optional[ExchangeType] = None
    ) -> List[InstrumentInfo]:
        """
        Search instruments by name or symbol.
        
        Args:
            query: Search query
            exchange: Filter by exchange (optional)
        
        Returns:
            List[InstrumentInfo]: Matching instruments
        
        Example:
            >>> results = market_data.search_instruments("RELIANCE")
            >>> for inst in results:
            ...     print(f"{inst.tradingsymbol}: {inst.name}")
        """
        instruments = self.get_instruments(exchange)
        query_upper = query.upper()
        
        return [
            inst for inst in instruments
            if query_upper in inst.tradingsymbol or query_upper in inst.name.upper()
        ]
    
    def get_equity_instruments(
        self,
        exchange: ExchangeType = ExchangeType.NSE
    ) -> List[InstrumentInfo]:
        """
        Get equity instruments only.
        
        Args:
            exchange: Exchange type
        
        Returns:
            List[InstrumentInfo]: Equity instruments
        """
        instruments = self.get_instruments(exchange)
        return [
            inst for inst in instruments
            if inst.instrument_type == "EQ"
        ]
    
    def get_fno_instruments(
        self,
        exchange: ExchangeType = ExchangeType.NFO
    ) -> List[InstrumentInfo]:
        """
        Get F&O instruments only.
        
        Args:
            exchange: Exchange type (default: NFO)
        
        Returns:
            List[InstrumentInfo]: F&O instruments
        """
        instruments = self.get_instruments(exchange)
        return [
            inst for inst in instruments
            if inst.instrument_type in ["FUT", "CE", "PE"]
        ]
    
    # ==========================================================================
    # Cache Management
    # ==========================================================================
    
    def clear_quote_cache(self) -> None:
        """Clear the quote cache."""
        self._quote_cache.clear()
        logger.info("Quote cache cleared")
    
    def clear_instruments_cache(self) -> None:
        """Clear the instruments cache."""
        self._instruments_cache.clear()
        logger.info("Instruments cache cleared")
    
    def clear_all_cache(self) -> None:
        """Clear all caches."""
        self.clear_quote_cache()
        self.clear_instruments_cache()
    
    # ==========================================================================
    # Utility Methods
    # ==========================================================================
    
    def is_market_open(self) -> bool:
        """
        Check if market is currently open.
        
        Note: This is a simple check based on time.
        Holidays are not considered.
        
        Returns:
            bool: True if market is likely open
        """
        now = datetime.now()
        
        # Market hours: 9:15 AM to 3:30 PM IST
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        # Check if weekday (Monday = 0, Sunday = 6)
        if now.weekday() >= 5:
            return False
        
        return market_open <= now <= market_close
    
    def get_market_status(self) -> Dict[str, Any]:
        """
        Get market status information.
        
        Returns:
            Dict with market status details
        """
        now = datetime.now()
        is_open = self.is_market_open()
        
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        if is_open:
            time_remaining = market_close - now
            status = "OPEN"
        elif now < market_open:
            time_remaining = market_open - now
            status = "PRE_OPEN"
        else:
            next_open = market_open + timedelta(days=1)
            # Skip weekends
            while next_open.weekday() >= 5:
                next_open += timedelta(days=1)
            time_remaining = next_open - now
            status = "CLOSED"
        
        return {
            "status": status,
            "is_open": is_open,
            "current_time": now.isoformat(),
            "market_open_time": "09:15:00",
            "market_close_time": "15:30:00",
            "time_remaining": str(time_remaining).split(".")[0]
        }
