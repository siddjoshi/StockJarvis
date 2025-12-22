# DataCollector/providers/base_provider.py
"""
Abstract base class for data providers.
Defines the interface that all data providers must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from enum import Enum
import pandas as pd


class ProviderError(Exception):
    """Base exception for data provider errors."""
    pass


class RateLimitError(ProviderError):
    """Raised when API rate limit is exceeded."""
    pass


class DataNotFoundError(ProviderError):
    """Raised when requested data is not available."""
    pass


class AuthenticationError(ProviderError):
    """Raised when authentication fails."""
    pass


class DataInterval(Enum):
    """Supported data intervals for historical data."""
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    DAILY = "1d"
    WEEKLY = "1wk"
    MONTHLY = "1mo"


@dataclass
class SymbolInfo:
    """Information about a tradable symbol."""
    symbol: str
    company_name: str
    exchange: str
    isin: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_fno: bool = False
    is_index: bool = False
    lot_size: Optional[int] = None
    face_value: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "exchange": self.exchange,
            "isin": self.isin,
            "sector": self.sector,
            "industry": self.industry,
            "is_fno": self.is_fno,
            "is_index": self.is_index,
            "lot_size": self.lot_size,
            "face_value": self.face_value,
            "metadata": self.metadata,
        }


@dataclass
class Quote:
    """Real-time price quote for a symbol."""
    symbol: str
    last_price: float
    change: float
    change_percent: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None  # Previous close
    volume: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    timestamp: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "last_price": self.last_price,
            "change": self.change,
            "change_percent": self.change_percent,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "bid": self.bid,
            "ask": self.ask,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class BaseDataProvider(ABC):
    """
    Abstract base class for market data providers.
    
    All data providers (Yahoo Finance, NSE, BSE, Zerodha) must implement
    this interface to ensure consistent behavior across the application.
    
    Example usage:
        >>> provider = YahooFinanceProvider()
        >>> symbols = provider.get_symbol_list()
        >>> data = provider.get_historical_data("RELIANCE.NS", "2024-01-01", "2024-12-20")
        >>> quote = provider.get_quote("RELIANCE.NS")
    """
    
    def __init__(self, name: str, exchange: str = "NSE"):
        """
        Initialize the data provider.
        
        Args:
            name: Provider name (e.g., "yahoo", "nse", "bse", "zerodha")
            exchange: Primary exchange for this provider
        """
        self.name = name
        self.exchange = exchange
        self._is_connected = False
    
    @property
    def is_connected(self) -> bool:
        """Check if provider is connected and ready."""
        return self._is_connected
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the data source.
        
        Returns:
            bool: True if connection successful, False otherwise
        
        Raises:
            AuthenticationError: If authentication fails
            ProviderError: If connection fails for other reasons
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """
        Close connection to the data source.
        Clean up any resources.
        """
        pass
    
    @abstractmethod
    def get_symbol_list(
        self,
        index: Optional[str] = None,
        fno_only: bool = False
    ) -> List[SymbolInfo]:
        """
        Get list of available symbols from the exchange.
        
        Args:
            index: Filter by index membership (e.g., "NIFTY50", "NIFTY500")
            fno_only: Return only F&O enabled symbols
        
        Returns:
            List[SymbolInfo]: List of symbol information objects
        
        Raises:
            ProviderError: If fetching symbols fails
        """
        pass
    
    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        start_date: str | date,
        end_date: str | date,
        interval: DataInterval = DataInterval.DAILY
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data for a symbol.
        
        Args:
            symbol: Stock symbol (with exchange suffix if needed)
            start_date: Start date (YYYY-MM-DD format or date object)
            end_date: End date (YYYY-MM-DD format or date object)
            interval: Data interval (default: daily)
        
        Returns:
            pd.DataFrame: DataFrame with columns:
                - timestamp (index): Datetime
                - open: Opening price
                - high: Highest price
                - low: Lowest price
                - close: Closing price
                - volume: Trading volume
                - turnover: (optional) Trading turnover
        
        Raises:
            DataNotFoundError: If no data is available for the symbol
            ProviderError: If fetching data fails
        
        Example:
            >>> df = provider.get_historical_data("RELIANCE.NS", "2024-01-01", "2024-12-20")
            >>> print(df.head())
        """
        pass
    
    @abstractmethod
    def get_quote(self, symbol: str) -> Quote:
        """
        Get real-time quote for a symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Quote: Real-time price quote
        
        Raises:
            DataNotFoundError: If symbol not found
            ProviderError: If fetching quote fails
        """
        pass
    
    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """
        Get real-time quotes for multiple symbols.
        
        Default implementation calls get_quote() for each symbol.
        Providers can override for batch optimization.
        
        Args:
            symbols: List of stock symbols
        
        Returns:
            Dict[str, Quote]: Dictionary mapping symbol to quote
        """
        quotes = {}
        for symbol in symbols:
            try:
                quotes[symbol] = self.get_quote(symbol)
            except DataNotFoundError:
                continue
        return quotes
    
    def validate_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate and clean OHLCV data.
        
        Checks:
        - No negative prices
        - High >= Open, Close, Low
        - Low <= Open, Close, High
        - Non-negative volume
        
        Args:
            df: DataFrame with OHLCV data
        
        Returns:
            pd.DataFrame: Validated and cleaned DataFrame
        """
        if df.empty:
            return df
        
        # Make a copy to avoid modifying original
        df = df.copy()
        
        # Required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        
        # Remove rows with invalid data using single boolean mask
        valid_mask = (
            (df['open'] > 0) &
            (df['high'] > 0) &
            (df['low'] > 0) &
            (df['close'] > 0) &
            (df['volume'] >= 0)
        )
        df = df[valid_mask]
        
        # Fix OHLC relationships
        # High should be >= Open, Close, Low
        df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
        # Low should be <= Open, Close, High
        df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)
        
        return df
    
    def map_symbol(self, symbol: str, target_exchange: str = None) -> str:
        """
        Map symbol to the format required by this provider.
        
        Override in subclasses for provider-specific symbol formats.
        
        Args:
            symbol: Input symbol (e.g., "RELIANCE")
            target_exchange: Target exchange (NSE, BSE, etc.)
        
        Returns:
            str: Symbol in provider-specific format
        
        Example:
            >>> yahoo_provider.map_symbol("RELIANCE", "NSE")
            "RELIANCE.NS"
        """
        return symbol
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', exchange='{self.exchange}')"
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
