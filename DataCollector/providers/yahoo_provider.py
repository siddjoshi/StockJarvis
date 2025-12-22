# DataCollector/providers/yahoo_provider.py
"""
Yahoo Finance data provider using yfinance library.
Provides historical data and quotes for Indian stocks.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
import time

from DataCollector.providers.base_provider import (
    BaseDataProvider,
    SymbolInfo,
    Quote,
    DataInterval,
    ProviderError,
    DataNotFoundError,
    RateLimitError,
)
from core.logger import get_logger

logger = get_logger(__name__)


# Symbol suffix mapping for different exchanges
EXCHANGE_SUFFIX = {
    "NSE": ".NS",
    "BSE": ".BO",
}

# Interval mapping from our format to yfinance format
INTERVAL_MAP = {
    DataInterval.MINUTE_1: "1m",
    DataInterval.MINUTE_5: "5m",
    DataInterval.MINUTE_15: "15m",
    DataInterval.MINUTE_30: "30m",
    DataInterval.HOUR_1: "1h",
    DataInterval.DAILY: "1d",
    DataInterval.WEEKLY: "1wk",
    DataInterval.MONTHLY: "1mo",
}


class YahooFinanceProvider(BaseDataProvider):
    """
    Yahoo Finance data provider.
    
    Uses yfinance library to fetch historical and real-time data.
    Supports NSE and BSE stocks with automatic symbol suffix handling.
    
    Example:
        >>> provider = YahooFinanceProvider()
        >>> provider.connect()
        >>> data = provider.get_historical_data("RELIANCE", "2024-01-01", "2024-12-20")
        >>> quote = provider.get_quote("RELIANCE")
        >>> provider.disconnect()
    
    Or using context manager:
        >>> with YahooFinanceProvider() as provider:
        ...     data = provider.get_historical_data("RELIANCE", "2024-01-01", "2024-12-20")
    """
    
    def __init__(
        self,
        exchange: str = "NSE",
        rate_limit_delay: float = 0.5,
        max_retries: int = 3
    ):
        """
        Initialize Yahoo Finance provider.
        
        Args:
            exchange: Default exchange (NSE or BSE)
            rate_limit_delay: Delay between API calls in seconds
            max_retries: Maximum retries for failed requests
        """
        super().__init__(name="yahoo", exchange=exchange)
        self.rate_limit_delay = rate_limit_delay
        self.max_retries = max_retries
        self._last_request_time = 0.0
    
    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()
    
    def connect(self) -> bool:
        """
        Establish connection (no-op for Yahoo Finance as it's stateless).
        
        Returns:
            bool: Always True for Yahoo Finance
        """
        logger.info("Yahoo Finance provider connected (stateless)")
        self._is_connected = True
        return True
    
    def disconnect(self) -> None:
        """Disconnect (no-op for Yahoo Finance)."""
        logger.info("Yahoo Finance provider disconnected")
        self._is_connected = False
    
    def map_symbol(self, symbol: str, target_exchange: str = None) -> str:
        """
        Map symbol to Yahoo Finance format.
        
        Args:
            symbol: Stock symbol (e.g., "RELIANCE")
            target_exchange: Exchange (NSE or BSE)
        
        Returns:
            str: Yahoo Finance format symbol (e.g., "RELIANCE.NS")
        """
        target_exchange = target_exchange or self.exchange
        
        # If symbol already has suffix, return as-is
        if symbol.endswith((".NS", ".BO")):
            return symbol
        
        suffix = EXCHANGE_SUFFIX.get(target_exchange.upper(), ".NS")
        return f"{symbol}{suffix}"
    
    def get_symbol_list(
        self,
        index: Optional[str] = None,
        fno_only: bool = False
    ) -> List[SymbolInfo]:
        """
        Get list of available symbols.
        
        Note: Yahoo Finance doesn't provide a direct symbol list API.
        This method returns a predefined list of popular Indian stocks.
        For a complete list, use NSE provider.
        
        Args:
            index: Filter by index (NIFTY50, NIFTY500)
            fno_only: Return only F&O symbols
        
        Returns:
            List[SymbolInfo]: List of symbol information
        """
        # Predefined list of popular Indian stocks
        # In production, this would come from NSE or a database
        nifty50_symbols = [
            ("ADANIENT", "Adani Enterprises Ltd", True),
            ("ADANIPORTS", "Adani Ports and SEZ Ltd", True),
            ("APOLLOHOSP", "Apollo Hospitals Enterprise Ltd", True),
            ("ASIANPAINT", "Asian Paints Ltd", True),
            ("AXISBANK", "Axis Bank Ltd", True),
            ("BAJAJ-AUTO", "Bajaj Auto Ltd", True),
            ("BAJFINANCE", "Bajaj Finance Ltd", True),
            ("BAJAJFINSV", "Bajaj Finserv Ltd", True),
            ("BHARTIARTL", "Bharti Airtel Ltd", True),
            ("BPCL", "Bharat Petroleum Corporation Ltd", True),
            ("BRITANNIA", "Britannia Industries Ltd", True),
            ("CIPLA", "Cipla Ltd", True),
            ("COALINDIA", "Coal India Ltd", True),
            ("DIVISLAB", "Divi's Laboratories Ltd", True),
            ("DRREDDY", "Dr. Reddy's Laboratories Ltd", True),
            ("EICHERMOT", "Eicher Motors Ltd", True),
            ("GRASIM", "Grasim Industries Ltd", True),
            ("HCLTECH", "HCL Technologies Ltd", True),
            ("HDFCBANK", "HDFC Bank Ltd", True),
            ("HDFCLIFE", "HDFC Life Insurance Company Ltd", True),
            ("HEROMOTOCO", "Hero MotoCorp Ltd", True),
            ("HINDALCO", "Hindalco Industries Ltd", True),
            ("HINDUNILVR", "Hindustan Unilever Ltd", True),
            ("ICICIBANK", "ICICI Bank Ltd", True),
            ("INDUSINDBK", "IndusInd Bank Ltd", True),
            ("INFY", "Infosys Ltd", True),
            ("ITC", "ITC Ltd", True),
            ("JSWSTEEL", "JSW Steel Ltd", True),
            ("KOTAKBANK", "Kotak Mahindra Bank Ltd", True),
            ("LT", "Larsen & Toubro Ltd", True),
            ("LTIM", "LTIMindtree Ltd", True),
            ("M&M", "Mahindra & Mahindra Ltd", True),
            ("MARUTI", "Maruti Suzuki India Ltd", True),
            ("NESTLEIND", "Nestle India Ltd", True),
            ("NTPC", "NTPC Ltd", True),
            ("ONGC", "Oil and Natural Gas Corporation Ltd", True),
            ("POWERGRID", "Power Grid Corporation of India Ltd", True),
            ("RELIANCE", "Reliance Industries Ltd", True),
            ("SBILIFE", "SBI Life Insurance Company Ltd", True),
            ("SBIN", "State Bank of India", True),
            ("SUNPHARMA", "Sun Pharmaceutical Industries Ltd", True),
            ("TATACONSUM", "Tata Consumer Products Ltd", True),
            ("TATAMOTORS", "Tata Motors Ltd", True),
            ("TATASTEEL", "Tata Steel Ltd", True),
            ("TCS", "Tata Consultancy Services Ltd", True),
            ("TECHM", "Tech Mahindra Ltd", True),
            ("TITAN", "Titan Company Ltd", True),
            ("ULTRACEMCO", "UltraTech Cement Ltd", True),
            ("UPL", "UPL Ltd", True),
            ("WIPRO", "Wipro Ltd", True),
        ]
        
        symbols = []
        for sym, name, is_fno in nifty50_symbols:
            if fno_only and not is_fno:
                continue
            
            symbols.append(SymbolInfo(
                symbol=sym,
                company_name=name,
                exchange=self.exchange,
                is_fno=is_fno,
            ))
        
        logger.info(f"Returning {len(symbols)} symbols from Yahoo Finance provider")
        return symbols
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: str | date,
        end_date: str | date,
        interval: DataInterval = DataInterval.DAILY
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data from Yahoo Finance.
        
        Args:
            symbol: Stock symbol (e.g., "RELIANCE" or "RELIANCE.NS")
            start_date: Start date (YYYY-MM-DD format or date object)
            end_date: End date (YYYY-MM-DD format or date object)
            interval: Data interval (default: daily)
        
        Returns:
            pd.DataFrame: DataFrame with OHLCV data
        
        Raises:
            DataNotFoundError: If no data available
            ProviderError: If fetching fails
        """
        yahoo_symbol = self.map_symbol(symbol)
        yf_interval = INTERVAL_MAP.get(interval, "1d")
        
        # Convert dates to string format
        if isinstance(start_date, date):
            start_date = start_date.strftime("%Y-%m-%d")
        if isinstance(end_date, date):
            end_date = end_date.strftime("%Y-%m-%d")
        
        logger.info(
            f"Fetching historical data for {yahoo_symbol} "
            f"from {start_date} to {end_date} ({yf_interval})"
        )
        
        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                
                # Create ticker object
                ticker = yf.Ticker(yahoo_symbol)
                
                # Fetch historical data
                df = ticker.history(
                    start=start_date,
                    end=end_date,
                    interval=yf_interval,
                    auto_adjust=True,  # Adjust for splits/dividends
                    prepost=False,  # No pre/post market data
                )
                
                if df.empty:
                    raise DataNotFoundError(
                        f"No data found for {yahoo_symbol} "
                        f"between {start_date} and {end_date}"
                    )
                
                # Standardize column names
                df = df.rename(columns={
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                })
                
                # Keep only required columns
                df = df[["open", "high", "low", "close", "volume"]]
                
                # Set index name
                df.index.name = "timestamp"
                
                # Validate data
                df = self.validate_data(df)
                
                logger.info(f"Retrieved {len(df)} records for {yahoo_symbol}")
                return df
                
            except DataNotFoundError:
                raise
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{self.max_retries} failed for {yahoo_symbol}: {e}"
                )
                if attempt < self.max_retries - 1:
                    time.sleep(self.rate_limit_delay * (attempt + 1))
                else:
                    raise ProviderError(f"Failed to fetch data for {yahoo_symbol}: {e}")
    
    def get_quote(self, symbol: str) -> Quote:
        """
        Get real-time quote from Yahoo Finance.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Quote: Real-time price quote
        
        Raises:
            DataNotFoundError: If symbol not found
            ProviderError: If fetching quote fails
        """
        yahoo_symbol = self.map_symbol(symbol)
        
        logger.info(f"Fetching quote for {yahoo_symbol}")
        
        try:
            self._rate_limit()
            
            ticker = yf.Ticker(yahoo_symbol)
            info = ticker.info
            
            if not info or "regularMarketPrice" not in info:
                raise DataNotFoundError(f"No quote data for {yahoo_symbol}")
            
            # Calculate change
            current_price = info.get("regularMarketPrice", 0)
            prev_close = info.get("regularMarketPreviousClose", 0)
            change = current_price - prev_close if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0
            
            quote = Quote(
                symbol=symbol,
                last_price=current_price,
                change=change,
                change_percent=round(change_pct, 2),
                open=info.get("regularMarketOpen"),
                high=info.get("regularMarketDayHigh"),
                low=info.get("regularMarketDayLow"),
                close=prev_close,
                volume=info.get("regularMarketVolume"),
                bid=info.get("bid"),
                ask=info.get("ask"),
                timestamp=datetime.now(),
            )
            
            logger.info(f"Quote for {yahoo_symbol}: {quote.last_price}")
            return quote
            
        except DataNotFoundError:
            raise
        except Exception as e:
            raise ProviderError(f"Failed to fetch quote for {yahoo_symbol}: {e}")
    
    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        """
        Get quotes for multiple symbols efficiently.
        
        Uses yfinance batch download for efficiency.
        
        Args:
            symbols: List of stock symbols
        
        Returns:
            Dict[str, Quote]: Dictionary mapping symbol to quote
        """
        yahoo_symbols = [self.map_symbol(s) for s in symbols]
        
        logger.info(f"Fetching batch quotes for {len(symbols)} symbols")
        
        try:
            self._rate_limit()
            
            # Use download for batch data
            data = yf.download(
                yahoo_symbols,
                period="1d",
                interval="1m",
                group_by="ticker",
                progress=False,
                threads=True,
            )
            
            quotes = {}
            
            for symbol, yahoo_symbol in zip(symbols, yahoo_symbols):
                try:
                    if len(yahoo_symbols) == 1:
                        ticker_data = data
                    else:
                        ticker_data = data[yahoo_symbol]
                    
                    if ticker_data.empty:
                        continue
                    
                    last_row = ticker_data.iloc[-1]
                    first_row = ticker_data.iloc[0]
                    
                    current_price = float(last_row["Close"])
                    open_price = float(first_row["Open"])
                    change = current_price - open_price
                    change_pct = (change / open_price * 100) if open_price else 0
                    
                    quotes[symbol] = Quote(
                        symbol=symbol,
                        last_price=current_price,
                        change=round(change, 2),
                        change_percent=round(change_pct, 2),
                        open=open_price,
                        high=float(ticker_data["High"].max()),
                        low=float(ticker_data["Low"].min()),
                        volume=int(ticker_data["Volume"].sum()),
                        timestamp=datetime.now(),
                    )
                    
                except Exception as e:
                    logger.warning(f"Failed to get quote for {symbol}: {e}")
                    continue
            
            logger.info(f"Retrieved {len(quotes)} quotes")
            return quotes
            
        except Exception as e:
            logger.error(f"Batch quote fetch failed: {e}")
            # Fall back to individual quotes
            return super().get_quotes(symbols)
