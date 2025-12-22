# DataCollector/providers/nse_provider.py
"""
NSE India data provider.
Fetches data from NSE India website and APIs.
"""

import requests
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
)
from core.logger import get_logger

logger = get_logger(__name__)


# NSE API endpoints
NSE_BASE_URL = "https://www.nseindia.com"
NSE_API_ENDPOINTS = {
    "equity_list": "/api/equity-stockIndices",
    "quote": "/api/quote-equity",
    "historical": "/api/historical/cm/equity",
    "fno_list": "/api/equity-stockIndices?index=SECURITIES%20IN%20F%26O",
    "indices": "/api/allIndices",
    "market_status": "/api/marketStatus",
}


class NSEProvider(BaseDataProvider):
    """
    NSE India data provider.
    
    Fetches data from NSE India website using their internal APIs.
    Requires proper session handling and headers to avoid rate limiting.
    
    Example:
        >>> with NSEProvider() as provider:
        ...     symbols = provider.get_symbol_list(index="NIFTY50")
        ...     quote = provider.get_quote("RELIANCE")
    
    Note:
        NSE may block requests without proper headers. This provider
        maintains a session with appropriate cookies and headers.
    """
    
    def __init__(
        self,
        rate_limit_delay: float = 1.0,
        max_retries: int = 3,
        timeout: int = 30
    ):
        """
        Initialize NSE provider.
        
        Args:
            rate_limit_delay: Delay between API calls in seconds
            max_retries: Maximum retries for failed requests
            timeout: Request timeout in seconds
        """
        super().__init__(name="nse", exchange="NSE")
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self._session = None
        self._last_request_time = 0.0
        
        # Headers to mimic browser request
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://www.nseindia.com/",
            "Connection": "keep-alive",
        }
    
    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def _initialize_session(self) -> None:
        """Initialize session with cookies from main page."""
        self._session = requests.Session()
        self._session.headers.update(self._headers)
        
        try:
            # Get cookies from main page
            response = self._session.get(
                NSE_BASE_URL,
                timeout=self.timeout
            )
            response.raise_for_status()
            logger.info("NSE session initialized with cookies")
        except Exception as e:
            logger.warning(f"Failed to initialize NSE session: {e}")
    
    def _make_request(
        self,
        endpoint: str,
        params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Make request to NSE API with retry logic.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
        
        Returns:
            Dict: JSON response
        
        Raises:
            ProviderError: If request fails after retries
        """
        if not self._session:
            self._initialize_session()
        
        url = f"{NSE_BASE_URL}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                
                response = self._session.get(
                    url,
                    params=params,
                    timeout=self.timeout
                )
                
                if response.status_code == 429:
                    wait_time = self.rate_limit_delay * (attempt + 2)
                    logger.warning(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                response.raise_for_status()
                return response.json()
                
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"NSE request attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                
                # Re-initialize session on failure
                if attempt < self.max_retries - 1:
                    self._initialize_session()
                    time.sleep(self.rate_limit_delay * (attempt + 1))
                else:
                    raise ProviderError(f"NSE API request failed: {e}")
        
        raise ProviderError(f"NSE API request failed after {self.max_retries} attempts")
    
    def connect(self) -> bool:
        """
        Establish connection to NSE.
        
        Returns:
            bool: True if connection successful
        """
        self._is_connected = False  # Ensure clean state before attempting
        try:
            self._initialize_session()
            
            # Verify connection by checking market status
            self._make_request(NSE_API_ENDPOINTS["market_status"])
            
            self._is_connected = True
            logger.info("NSE provider connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to NSE: {e}")
            return False
    
    def disconnect(self) -> None:
        """Close NSE session."""
        if self._session:
            self._session.close()
            self._session = None
        self._is_connected = False
        logger.info("NSE provider disconnected")
    
    def get_symbol_list(
        self,
        index: Optional[str] = None,
        fno_only: bool = False
    ) -> List[SymbolInfo]:
        """
        Get list of symbols from NSE.
        
        Args:
            index: Filter by index (NIFTY50, NIFTY500, etc.)
            fno_only: Return only F&O enabled symbols
        
        Returns:
            List[SymbolInfo]: List of symbol information
        """
        logger.info(f"Fetching NSE symbols (index={index}, fno_only={fno_only})")
        
        try:
            if fno_only:
                endpoint = NSE_API_ENDPOINTS["fno_list"]
            elif index:
                endpoint = f"{NSE_API_ENDPOINTS['equity_list']}?index={index.upper()}"
            else:
                endpoint = f"{NSE_API_ENDPOINTS['equity_list']}?index=NIFTY%20500"
            
            data = self._make_request(endpoint)
            
            symbols = []
            for item in data.get("data", []):
                symbol_info = SymbolInfo(
                    symbol=item.get("symbol", ""),
                    company_name=item.get("companyName", item.get("meta", {}).get("companyName", "")),
                    exchange="NSE",
                    isin=item.get("meta", {}).get("isin"),
                    sector=item.get("meta", {}).get("industry"),
                    is_fno=fno_only or item.get("meta", {}).get("isFNOSec", False),
                    metadata={
                        "last_price": item.get("lastPrice"),
                        "change": item.get("change"),
                        "pct_change": item.get("pChange"),
                    }
                )
                if symbol_info.symbol:
                    symbols.append(symbol_info)
            
            logger.info(f"Retrieved {len(symbols)} symbols from NSE")
            return symbols
            
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Failed to fetch NSE symbol list: {e}")
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: str | date,
        end_date: str | date,
        interval: DataInterval = DataInterval.DAILY
    ) -> pd.DataFrame:
        """
        Fetch historical data from NSE.
        
        Note: NSE historical data API is limited. For extensive historical data,
        consider using Yahoo Finance as a fallback.
        
        Args:
            symbol: Stock symbol (e.g., "RELIANCE")
            start_date: Start date
            end_date: End date
            interval: Data interval (only daily supported by NSE)
        
        Returns:
            pd.DataFrame: DataFrame with OHLCV data
        """
        # Convert dates
        if isinstance(start_date, date):
            start_date = start_date.strftime("%d-%m-%Y")
        else:
            # Convert from YYYY-MM-DD to DD-MM-YYYY
            start_date = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d-%m-%Y")
        
        if isinstance(end_date, date):
            end_date = end_date.strftime("%d-%m-%Y")
        else:
            end_date = datetime.strptime(end_date, "%Y-%m-%d").strftime("%d-%m-%Y")
        
        logger.info(f"Fetching NSE historical data for {symbol} from {start_date} to {end_date}")
        
        try:
            params = {
                "symbol": symbol.upper(),
                "from": start_date,
                "to": end_date,
            }
            
            data = self._make_request(NSE_API_ENDPOINTS["historical"], params)
            
            if not data.get("data"):
                raise DataNotFoundError(f"No data found for {symbol}")
            
            # Convert to DataFrame
            records = []
            for item in data["data"]:
                records.append({
                    "timestamp": pd.to_datetime(item.get("CH_TIMESTAMP")),
                    "open": float(item.get("CH_OPENING_PRICE", 0)),
                    "high": float(item.get("CH_TRADE_HIGH_PRICE", 0)),
                    "low": float(item.get("CH_TRADE_LOW_PRICE", 0)),
                    "close": float(item.get("CH_CLOSING_PRICE", 0)),
                    "volume": int(item.get("CH_TOT_TRADED_QTY", 0)),
                    "turnover": float(item.get("CH_TOT_TRADED_VAL", 0)),
                })
            
            df = pd.DataFrame(records)
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)
            
            # Validate data
            df = self.validate_data(df)
            
            logger.info(f"Retrieved {len(df)} records for {symbol} from NSE")
            return df
            
        except DataNotFoundError:
            raise
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Failed to fetch NSE historical data: {e}")
    
    def get_quote(self, symbol: str) -> Quote:
        """
        Get real-time quote from NSE.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Quote: Real-time price quote
        """
        logger.info(f"Fetching NSE quote for {symbol}")
        
        try:
            params = {"symbol": symbol.upper()}
            data = self._make_request(NSE_API_ENDPOINTS["quote"], params)
            
            price_info = data.get("priceInfo", {})
            
            if not price_info:
                raise DataNotFoundError(f"No quote data for {symbol}")
            
            quote = Quote(
                symbol=symbol,
                last_price=float(price_info.get("lastPrice", 0)),
                change=float(price_info.get("change", 0)),
                change_percent=float(price_info.get("pChange", 0)),
                open=float(price_info.get("open", 0)),
                high=float(price_info.get("intraDayHighLow", {}).get("max", 0)),
                low=float(price_info.get("intraDayHighLow", {}).get("min", 0)),
                close=float(price_info.get("previousClose", 0)),
                volume=int(data.get("preOpenMarket", {}).get("totalTradedVolume", 0)),
                timestamp=datetime.now(),
            )
            
            logger.info(f"Quote for {symbol}: {quote.last_price}")
            return quote
            
        except DataNotFoundError:
            raise
        except Exception as e:
            raise ProviderError(f"Failed to fetch NSE quote for {symbol}: {e}")
    
    def get_market_status(self) -> Dict[str, Any]:
        """
        Get current market status from NSE.
        
        Returns:
            Dict: Market status information
        """
        try:
            data = self._make_request(NSE_API_ENDPOINTS["market_status"])
            
            return {
                "status": data.get("marketState", [{}])[0].get("marketStatus", "Unknown"),
                "timestamp": datetime.now().isoformat(),
                "raw": data,
            }
            
        except Exception as e:
            raise ProviderError(f"Failed to fetch market status: {e}")
    
    def get_indices(self) -> List[Dict[str, Any]]:
        """
        Get all NSE indices data.
        
        Returns:
            List[Dict]: List of index data
        """
        try:
            data = self._make_request(NSE_API_ENDPOINTS["indices"])
            
            indices = []
            for item in data.get("data", []):
                indices.append({
                    "index": item.get("index"),
                    "last": item.get("last"),
                    "change": item.get("percentChange"),
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("previousClose"),
                })
            
            return indices
            
        except Exception as e:
            raise ProviderError(f"Failed to fetch indices: {e}")
