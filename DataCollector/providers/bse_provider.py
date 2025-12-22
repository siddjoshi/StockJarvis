# DataCollector/providers/bse_provider.py
"""
BSE India data provider.
Fetches data from BSE India website and APIs.
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


# BSE API endpoints
BSE_BASE_URL = "https://api.bseindia.com"
BSE_WEB_URL = "https://www.bseindia.com"
BSE_API_ENDPOINTS = {
    "quote": "/BseIndiaAPI/api/StockReachGraph/w",
    "scripcode": "/BseIndiaAPI/api/ScripCode/w",
    "historical": "/BseIndiaAPI/api/StockPriceCSVDownload/w",
    "market_cap": "/BseIndiaAPI/api/MktCapAmt/w",
    "indices": "/BseIndiaAPI/api/GetBSEIndicesAll/w",
}


class BSEProvider(BaseDataProvider):
    """
    BSE India data provider.
    
    Fetches data from BSE India website using their APIs.
    BSE uses scrip codes instead of symbol names for most APIs.
    
    Example:
        >>> with BSEProvider() as provider:
        ...     quote = provider.get_quote("RELIANCE")  # Uses scrip code lookup
    
    Note:
        BSE data may have different trading hours and price points
        compared to NSE. Cross-validation recommended.
    """
    
    def __init__(
        self,
        rate_limit_delay: float = 1.0,
        max_retries: int = 3,
        timeout: int = 30
    ):
        """
        Initialize BSE provider.
        
        Args:
            rate_limit_delay: Delay between API calls in seconds
            max_retries: Maximum retries for failed requests
            timeout: Request timeout in seconds
        """
        super().__init__(name="bse", exchange="BSE")
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self.timeout = timeout
        self._session = None
        self._last_request_time = 0.0
        
        # Cache for symbol to scrip code mapping
        self._scrip_code_cache: Dict[str, str] = {}
        
        # Headers to mimic browser request
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Origin": "https://www.bseindia.com",
            "Referer": "https://www.bseindia.com/",
        }
        
        # Common symbol to BSE scrip code mapping
        self._common_scrip_codes = {
            "RELIANCE": "500325",
            "TCS": "532540",
            "INFY": "500209",
            "HDFCBANK": "500180",
            "ICICIBANK": "532174",
            "HINDUNILVR": "500696",
            "ITC": "500875",
            "SBIN": "500112",
            "BHARTIARTL": "532454",
            "KOTAKBANK": "500247",
            "ASIANPAINT": "500820",
            "AXISBANK": "532215",
            "MARUTI": "532500",
            "LT": "500510",
            "BAJFINANCE": "500034",
            "HCLTECH": "532281",
            "SUNPHARMA": "524715",
            "WIPRO": "507685",
            "TATAMOTORS": "500570",
            "TATASTEEL": "500470",
        }
    
    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def _initialize_session(self) -> None:
        """Initialize session with cookies."""
        self._session = requests.Session()
        self._session.headers.update(self._headers)
        
        try:
            # Get cookies from main page
            response = self._session.get(
                BSE_WEB_URL,
                timeout=self.timeout
            )
            response.raise_for_status()
            logger.info("BSE session initialized with cookies")
        except Exception as e:
            logger.warning(f"Failed to initialize BSE session: {e}")
    
    def _make_request(
        self,
        endpoint: str,
        params: Dict[str, Any] = None,
        base_url: str = None
    ) -> Any:
        """
        Make request to BSE API with retry logic.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            base_url: Base URL to use
        
        Returns:
            Any: JSON response
        """
        if not self._session:
            self._initialize_session()
        
        url = f"{base_url or BSE_BASE_URL}{endpoint}"
        
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
                
                # BSE may return HTML error pages
                content_type = response.headers.get("Content-Type", "")
                if "application/json" not in content_type and "text/javascript" not in content_type:
                    raise ProviderError("BSE returned non-JSON response")
                
                return response.json()
                
            except requests.exceptions.RequestException as e:
                logger.warning(
                    f"BSE request attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                
                if attempt < self.max_retries - 1:
                    self._initialize_session()
                    time.sleep(self.rate_limit_delay * (attempt + 1))
                else:
                    raise ProviderError(f"BSE API request failed: {e}")
        
        raise ProviderError(f"BSE API request failed after {self.max_retries} attempts")
    
    def _get_scrip_code(self, symbol: str) -> str:
        """
        Get BSE scrip code for a symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            str: BSE scrip code
        """
        # Check cache first
        if symbol.upper() in self._scrip_code_cache:
            return self._scrip_code_cache[symbol.upper()]
        
        # Check common mapping
        if symbol.upper() in self._common_scrip_codes:
            return self._common_scrip_codes[symbol.upper()]
        
        # Try to look up from API
        try:
            params = {"scripcode": symbol.upper()}
            data = self._make_request(BSE_API_ENDPOINTS["scripcode"], params)
            
            if data and isinstance(data, list) and len(data) > 0:
                scrip_code = str(data[0].get("scrip_cd", ""))
                if scrip_code:
                    self._scrip_code_cache[symbol.upper()] = scrip_code
                    return scrip_code
        except Exception as e:
            logger.warning(f"Failed to lookup scrip code for {symbol}: {e}")
        
        raise DataNotFoundError(f"Could not find BSE scrip code for {symbol}")
    
    def connect(self) -> bool:
        """
        Establish connection to BSE.
        
        Returns:
            bool: True if connection successful
        """
        try:
            self._initialize_session()
            
            # Verify connection by fetching indices
            self._make_request(BSE_API_ENDPOINTS["indices"])
            
            self._is_connected = True
            logger.info("BSE provider connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to BSE: {e}")
            self._is_connected = False
            return False
    
    def disconnect(self) -> None:
        """Close BSE session."""
        if self._session:
            self._session.close()
            self._session = None
        self._is_connected = False
        logger.info("BSE provider disconnected")
    
    def get_symbol_list(
        self,
        index: Optional[str] = None,
        fno_only: bool = False
    ) -> List[SymbolInfo]:
        """
        Get list of symbols from BSE.
        
        Note: BSE API for full symbol list is limited.
        Returns common BSE symbols from cached mapping.
        
        Args:
            index: Filter by index (SENSEX, BSE500)
            fno_only: Return only F&O symbols
        
        Returns:
            List[SymbolInfo]: List of symbol information
        """
        logger.info(f"Fetching BSE symbols (index={index}, fno_only={fno_only})")
        
        # Return from common scrip codes mapping
        symbols = []
        
        for symbol, scrip_code in self._common_scrip_codes.items():
            symbols.append(SymbolInfo(
                symbol=symbol,
                company_name=symbol,  # Would need additional lookup
                exchange="BSE",
                is_fno=True,  # These are major stocks, likely F&O
                metadata={"scrip_code": scrip_code}
            ))
        
        logger.info(f"Returning {len(symbols)} BSE symbols")
        return symbols
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: str | date,
        end_date: str | date,
        interval: DataInterval = DataInterval.DAILY
    ) -> pd.DataFrame:
        """
        Fetch historical data from BSE.
        
        Note: BSE historical data API may have limitations.
        Consider using Yahoo Finance (.BO suffix) for better coverage.
        
        Args:
            symbol: Stock symbol or scrip code
            start_date: Start date
            end_date: End date
            interval: Data interval (only daily supported)
        
        Returns:
            pd.DataFrame: DataFrame with OHLCV data
        """
        # Convert dates
        if isinstance(start_date, date):
            start_str = start_date.strftime("%Y%m%d")
        else:
            start_str = datetime.strptime(start_date, "%Y-%m-%d").strftime("%Y%m%d")
        
        if isinstance(end_date, date):
            end_str = end_date.strftime("%Y%m%d")
        else:
            end_str = datetime.strptime(end_date, "%Y-%m-%d").strftime("%Y%m%d")
        
        logger.info(f"Fetching BSE historical data for {symbol}")
        
        try:
            # Get scrip code
            scrip_code = self._get_scrip_code(symbol)
            
            params = {
                "scripcode": scrip_code,
                "FromDate": start_str,
                "ToDate": end_str,
            }
            
            data = self._make_request(BSE_API_ENDPOINTS["historical"], params)
            
            if not data:
                raise DataNotFoundError(f"No data found for {symbol}")
            
            # Parse data - BSE returns different formats
            records = []
            
            if isinstance(data, list):
                for item in data:
                    try:
                        records.append({
                            "timestamp": pd.to_datetime(item.get("trd_date")),
                            "open": float(item.get("open_price", 0)),
                            "high": float(item.get("high_price", 0)),
                            "low": float(item.get("low_price", 0)),
                            "close": float(item.get("close_price", 0)),
                            "volume": int(item.get("no_of_shrs", 0)),
                        })
                    except (ValueError, TypeError):
                        continue
            
            if not records:
                raise DataNotFoundError(f"No valid data for {symbol}")
            
            df = pd.DataFrame(records)
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)
            
            # Validate data
            df = self.validate_data(df)
            
            logger.info(f"Retrieved {len(df)} records for {symbol} from BSE")
            return df
            
        except DataNotFoundError:
            raise
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Failed to fetch BSE historical data: {e}")
    
    def get_quote(self, symbol: str) -> Quote:
        """
        Get real-time quote from BSE.
        
        Args:
            symbol: Stock symbol or scrip code
        
        Returns:
            Quote: Real-time price quote
        """
        logger.info(f"Fetching BSE quote for {symbol}")
        
        try:
            # Get scrip code
            scrip_code = self._get_scrip_code(symbol)
            
            params = {
                "scripcode": scrip_code,
                "flag": "0",
            }
            
            data = self._make_request(BSE_API_ENDPOINTS["quote"], params)
            
            if not data or not isinstance(data, dict):
                raise DataNotFoundError(f"No quote data for {symbol}")
            
            header = data.get("Header", {})
            current_val = header.get("CurrVal", {})
            
            current_price = float(current_val.get("CurrVal", 0))
            prev_close = float(header.get("PrevClose", 0))
            change = current_price - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0
            
            quote = Quote(
                symbol=symbol,
                last_price=current_price,
                change=round(change, 2),
                change_percent=round(change_pct, 2),
                open=float(header.get("Open", 0)),
                high=float(header.get("High", 0)),
                low=float(header.get("Low", 0)),
                close=prev_close,
                volume=int(header.get("TotQty", 0)),
                timestamp=datetime.now(),
            )
            
            logger.info(f"Quote for {symbol}: {quote.last_price}")
            return quote
            
        except DataNotFoundError:
            raise
        except Exception as e:
            raise ProviderError(f"Failed to fetch BSE quote for {symbol}: {e}")
    
    def get_indices(self) -> List[Dict[str, Any]]:
        """
        Get all BSE indices data.
        
        Returns:
            List[Dict]: List of index data
        """
        try:
            data = self._make_request(BSE_API_ENDPOINTS["indices"])
            
            indices = []
            for item in data if isinstance(data, list) else []:
                indices.append({
                    "index": item.get("indxnm"),
                    "last": item.get("currentvalue"),
                    "change": item.get("chg"),
                    "pct_change": item.get("perchg"),
                })
            
            return indices
            
        except Exception as e:
            raise ProviderError(f"Failed to fetch BSE indices: {e}")
    
    def map_symbol(self, symbol: str, target_exchange: str = None) -> str:
        """
        Map symbol to BSE format (returns scrip code).
        
        Args:
            symbol: Stock symbol
            target_exchange: Not used for BSE
        
        Returns:
            str: BSE scrip code
        """
        try:
            return self._get_scrip_code(symbol)
        except DataNotFoundError:
            return symbol
