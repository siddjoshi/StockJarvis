# DataCollector/providers/zerodha_provider.py
"""
Zerodha Kite Connect data provider.
Provides historical and real-time data via Kite Connect API.
"""

import pandas as pd
from datetime import datetime, date
from typing import List, Optional, Dict, Any
import time

from DataCollector.providers.base_provider import (
    BaseDataProvider,
    SymbolInfo,
    Quote,
    DataInterval,
    ProviderError,
    DataNotFoundError,
    AuthenticationError,
)
from core.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


# Zerodha Kite Connect interval mapping
INTERVAL_MAP = {
    DataInterval.MINUTE_1: "minute",
    DataInterval.MINUTE_5: "5minute",
    DataInterval.MINUTE_15: "15minute",
    DataInterval.MINUTE_30: "30minute",
    DataInterval.HOUR_1: "60minute",
    DataInterval.DAILY: "day",
}


class ZerodhaProvider(BaseDataProvider):
    """
    Zerodha Kite Connect data provider.
    
    Uses Kite Connect API for historical and real-time data.
    Requires valid API credentials and access token.
    
    Note:
        - Requires Zerodha trading account
        - Requires Kite Connect API subscription
        - Access token must be refreshed daily after login
    
    Example:
        >>> provider = ZerodhaProvider(
        ...     api_key="your_api_key",
        ...     api_secret="your_api_secret",
        ...     access_token="your_access_token"  # From daily login
        ... )
        >>> provider.connect()
        >>> data = provider.get_historical_data("RELIANCE", "2024-01-01", "2024-12-20")
    
    Or with settings from config:
        >>> provider = ZerodhaProvider()  # Uses settings from config
        >>> provider.connect()
    """
    
    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        access_token: str = None,
        rate_limit_delay: float = 0.3,
        max_retries: int = 3
    ):
        """
        Initialize Zerodha provider.
        
        Args:
            api_key: Kite Connect API key (uses settings if not provided)
            api_secret: Kite Connect API secret (uses settings if not provided)
            access_token: Access token from OAuth login (uses settings if not provided)
            rate_limit_delay: Delay between API calls in seconds
            max_retries: Maximum retries for failed requests
        """
        super().__init__(name="zerodha", exchange="NSE")
        
        # Use settings if credentials not provided, with safe access
        zerodha_settings = getattr(settings, 'zerodha', None)
        self.api_key = api_key or (getattr(zerodha_settings, 'api_key', None) if zerodha_settings else None) or "not_configured"
        self.api_secret = api_secret or (getattr(zerodha_settings, 'api_secret', None) if zerodha_settings else None) or "not_configured"
        self.access_token = access_token or (getattr(zerodha_settings, 'access_token', None) if zerodha_settings else None)
        
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self._last_request_time = 0.0
        
        # Kite Connect client instance
        self._kite = None
        
        # Instrument token cache
        self._instrument_cache: Dict[str, int] = {}
    
    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def _ensure_kite_client(self) -> None:
        """Ensure Kite Connect client is initialized."""
        if self._kite is not None:
            return
        
        try:
            from kiteconnect import KiteConnect
            
            self._kite = KiteConnect(api_key=self.api_key)
            
            if self.access_token:
                self._kite.set_access_token(self.access_token)
            
            logger.info("Kite Connect client initialized")
            
        except ImportError:
            raise ProviderError(
                "kiteconnect package not installed. "
                "Install with: pip install kiteconnect"
            )
        except Exception as e:
            raise ProviderError(f"Failed to initialize Kite Connect: {e}")
    
    def _get_instrument_token(self, symbol: str, exchange: str = "NSE") -> int:
        """
        Get Zerodha instrument token for a symbol.
        
        Args:
            symbol: Stock symbol
            exchange: Exchange (NSE/BSE)
        
        Returns:
            int: Instrument token
        """
        cache_key = f"{exchange}:{symbol}"
        
        if cache_key in self._instrument_cache:
            return self._instrument_cache[cache_key]
        
        # Try to get from instruments list
        try:
            instruments = self._kite.instruments(exchange)
            
            for inst in instruments:
                if inst["tradingsymbol"] == symbol.upper():
                    self._instrument_cache[cache_key] = inst["instrument_token"]
                    return inst["instrument_token"]
            
            raise DataNotFoundError(f"Instrument not found: {symbol} on {exchange}")
            
        except Exception as e:
            if "DataNotFoundError" in str(type(e).__name__):
                raise
            raise ProviderError(f"Failed to get instrument token: {e}")
    
    def connect(self) -> bool:
        """
        Establish connection to Zerodha Kite Connect.
        
        Returns:
            bool: True if connection successful
        
        Raises:
            AuthenticationError: If access token is invalid or expired
        """
        try:
            self._ensure_kite_client()
            
            if not self.access_token:
                logger.warning(
                    "No access token configured. "
                    "Login required to generate access token."
                )
                # Connection is partial without access token
                self._is_connected = False
                return False
            
            # Verify access token by fetching profile
            self._rate_limit()
            profile = self._kite.profile()
            
            logger.info(f"Zerodha connected for user: {profile.get('user_name')}")
            self._is_connected = True
            return True
            
        except Exception as e:
            error_str = str(e).lower()
            if "token" in error_str or "auth" in error_str or "invalid" in error_str:
                raise AuthenticationError(
                    f"Zerodha authentication failed: {e}. "
                    "Access token may be expired. Please login again."
                )
            raise ProviderError(f"Failed to connect to Zerodha: {e}")
    
    def disconnect(self) -> None:
        """Disconnect from Zerodha."""
        self._kite = None
        self._is_connected = False
        logger.info("Zerodha provider disconnected")
    
    def get_login_url(self) -> str:
        """
        Get Zerodha login URL for OAuth flow.
        
        Returns:
            str: Login URL
        """
        self._ensure_kite_client()
        return self._kite.login_url()
    
    def generate_access_token(self, request_token: str) -> str:
        """
        Generate access token from request token after OAuth login.
        
        Args:
            request_token: Request token from OAuth callback
        
        Returns:
            str: Access token
        """
        self._ensure_kite_client()
        
        try:
            data = self._kite.generate_session(
                request_token,
                api_secret=self.api_secret
            )
            
            self.access_token = data["access_token"]
            self._kite.set_access_token(self.access_token)
            self._is_connected = True
            
            logger.info("Access token generated successfully")
            return self.access_token
            
        except Exception as e:
            raise AuthenticationError(f"Failed to generate access token: {e}")
    
    def get_symbol_list(
        self,
        index: Optional[str] = None,
        fno_only: bool = False
    ) -> List[SymbolInfo]:
        """
        Get list of instruments from Zerodha.
        
        Args:
            index: Not directly supported by Zerodha
            fno_only: Return only F&O instruments
        
        Returns:
            List[SymbolInfo]: List of symbol information
        """
        self._ensure_kite_client()
        
        logger.info(f"Fetching Zerodha instruments (fno_only={fno_only})")
        
        try:
            self._rate_limit()
            
            exchange = "NFO" if fno_only else "NSE"
            instruments = self._kite.instruments(exchange)
            
            symbols = []
            seen = set()
            
            for inst in instruments:
                symbol = inst["tradingsymbol"]
                
                # Skip duplicates and derivatives
                if symbol in seen:
                    continue
                if fno_only and inst["segment"] != "NFO":
                    continue
                if not fno_only and inst["instrument_type"] not in ["EQ", ""]:
                    continue
                
                seen.add(symbol)
                
                symbols.append(SymbolInfo(
                    symbol=symbol,
                    company_name=inst.get("name", symbol),
                    exchange=inst.get("exchange", "NSE"),
                    is_fno=fno_only or inst.get("segment") in ["NFO", "NSE-FO"],
                    lot_size=inst.get("lot_size"),
                    metadata={
                        "instrument_token": inst["instrument_token"],
                        "instrument_type": inst.get("instrument_type"),
                        "segment": inst.get("segment"),
                        "expiry": inst.get("expiry"),
                        "tick_size": inst.get("tick_size"),
                    }
                ))
            
            logger.info(f"Retrieved {len(symbols)} instruments from Zerodha")
            return symbols
            
        except Exception as e:
            raise ProviderError(f"Failed to fetch Zerodha instruments: {e}")
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: str | date,
        end_date: str | date,
        interval: DataInterval = DataInterval.DAILY
    ) -> pd.DataFrame:
        """
        Fetch historical data from Zerodha.
        
        Args:
            symbol: Stock symbol
            start_date: Start date
            end_date: End date
            interval: Data interval
        
        Returns:
            pd.DataFrame: DataFrame with OHLCV data
        
        Note:
            Zerodha has limits on historical data:
            - Minute data: 60 days
            - Day data: 2000 days
        """
        self._ensure_kite_client()
        
        if not self.access_token:
            raise AuthenticationError("Access token required for historical data")
        
        # Convert dates
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        elif isinstance(start_date, date):
            start_date = datetime.combine(start_date, datetime.min.time())
        
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")
        elif isinstance(end_date, date):
            end_date = datetime.combine(end_date, datetime.max.time().replace(microsecond=0))
        
        logger.info(
            f"Fetching Zerodha historical data for {symbol} "
            f"from {start_date} to {end_date}"
        )
        
        try:
            # Get instrument token
            instrument_token = self._get_instrument_token(symbol)
            
            # Map interval
            kite_interval = INTERVAL_MAP.get(interval, "day")
            
            self._rate_limit()
            
            data = self._kite.historical_data(
                instrument_token,
                start_date,
                end_date,
                kite_interval
            )
            
            if not data:
                raise DataNotFoundError(f"No data found for {symbol}")
            
            # Convert to DataFrame
            df = pd.DataFrame(data)
            
            # Standardize columns
            df = df.rename(columns={
                "date": "timestamp",
            })
            
            df.set_index("timestamp", inplace=True)
            
            # Keep only required columns
            required_cols = ["open", "high", "low", "close", "volume"]
            df = df[[col for col in required_cols if col in df.columns]]
            
            # Validate data
            df = self.validate_data(df)
            
            logger.info(f"Retrieved {len(df)} records for {symbol} from Zerodha")
            return df
            
        except DataNotFoundError:
            raise
        except AuthenticationError:
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "token" in error_str or "auth" in error_str:
                raise AuthenticationError(f"Zerodha authentication error: {e}")
            raise ProviderError(f"Failed to fetch Zerodha historical data: {e}")
    
    def get_quote(self, symbol: str) -> Quote:
        """
        Get real-time quote from Zerodha.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Quote: Real-time price quote
        """
        self._ensure_kite_client()
        
        if not self.access_token:
            raise AuthenticationError("Access token required for quotes")
        
        logger.info(f"Fetching Zerodha quote for {symbol}")
        
        try:
            # Validate instrument exists (warms cache)
            self._get_instrument_token(symbol)
            
            self._rate_limit()
            
            # Get LTP quote
            quote_data = self._kite.quote([f"NSE:{symbol.upper()}"])
            
            if not quote_data:
                raise DataNotFoundError(f"No quote data for {symbol}")
            
            key = f"NSE:{symbol.upper()}"
            data = quote_data.get(key, {})
            
            if not data:
                raise DataNotFoundError(f"No quote data for {symbol}")
            
            ohlc = data.get("ohlc", {})
            
            quote = Quote(
                symbol=symbol,
                last_price=float(data.get("last_price", 0)),
                change=float(data.get("change", 0)),
                change_percent=float(data.get("change_percent", 0)) if data.get("change_percent") else 0,
                open=float(ohlc.get("open", 0)),
                high=float(ohlc.get("high", 0)),
                low=float(ohlc.get("low", 0)),
                close=float(ohlc.get("close", 0)),
                volume=int(data.get("volume", 0)),
                bid=float(data.get("depth", {}).get("buy", [{}])[0].get("price", 0)),
                ask=float(data.get("depth", {}).get("sell", [{}])[0].get("price", 0)),
                timestamp=datetime.now(),
            )
            
            logger.info(f"Quote for {symbol}: {quote.last_price}")
            return quote
            
        except DataNotFoundError:
            raise
        except AuthenticationError:
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "token" in error_str or "auth" in error_str:
                raise AuthenticationError(f"Zerodha authentication error: {e}")
            raise ProviderError(f"Failed to fetch Zerodha quote: {e}")
    
    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """
        Get quotes for multiple symbols efficiently.
        
        Uses Zerodha batch quote API.
        
        Args:
            symbols: List of stock symbols
        
        Returns:
            Dict[str, Quote]: Dictionary mapping symbol to quote
        """
        self._ensure_kite_client()
        
        if not self.access_token:
            raise AuthenticationError("Access token required for quotes")
        
        logger.info(f"Fetching Zerodha batch quotes for {len(symbols)} symbols")
        
        try:
            self._rate_limit()
            
            # Build instrument list
            instruments = [f"NSE:{s.upper()}" for s in symbols]
            
            # Get batch quotes
            quote_data = self._kite.quote(instruments)
            
            quotes = {}
            
            for symbol in symbols:
                key = f"NSE:{symbol.upper()}"
                data = quote_data.get(key, {})
                
                if not data:
                    continue
                
                ohlc = data.get("ohlc", {})
                
                quotes[symbol] = Quote(
                    symbol=symbol,
                    last_price=float(data.get("last_price", 0)),
                    change=float(data.get("change", 0)),
                    change_percent=float(data.get("change_percent", 0)) if data.get("change_percent") else 0,
                    open=float(ohlc.get("open", 0)),
                    high=float(ohlc.get("high", 0)),
                    low=float(ohlc.get("low", 0)),
                    close=float(ohlc.get("close", 0)),
                    volume=int(data.get("volume", 0)),
                    timestamp=datetime.now(),
                )
            
            logger.info(f"Retrieved {len(quotes)} quotes from Zerodha")
            return quotes
            
        except AuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Batch quote fetch failed: {e}")
            return {}
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions from Zerodha.
        
        Returns:
            List[Dict]: List of position data
        """
        self._ensure_kite_client()
        
        if not self.access_token:
            raise AuthenticationError("Access token required")
        
        try:
            self._rate_limit()
            positions = self._kite.positions()
            
            return positions.get("net", [])
            
        except Exception as e:
            raise ProviderError(f"Failed to fetch positions: {e}")
    
    def get_holdings(self) -> List[Dict[str, Any]]:
        """
        Get holdings from Zerodha.
        
        Returns:
            List[Dict]: List of holding data
        """
        self._ensure_kite_client()
        
        if not self.access_token:
            raise AuthenticationError("Access token required")
        
        try:
            self._rate_limit()
            return self._kite.holdings()
            
        except Exception as e:
            raise ProviderError(f"Failed to fetch holdings: {e}")
