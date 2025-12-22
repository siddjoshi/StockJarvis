# BrokerModules/Zerodha/kite_client.py
"""
Zerodha Kite Connect API client implementation.
Provides authentication, session management, rate limiting, and error handling.
"""

import time
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime
from functools import wraps

from kiteconnect import KiteConnect
from kiteconnect.exceptions import (
    KiteException,
    TokenException,
    GeneralException,
    PermissionException,
    InputException,
    DataException,
    NetworkException,
    OrderException,
)

from BrokerModules.base_broker import (
    BaseBroker,
    OrderRequest,
    OrderResponse,
    PositionData,
    HoldingData,
    QuoteData,
    MarginData,
    OrderType,
    TransactionType,
    ProductType,
    ExchangeType,
    BrokerError,
    AuthenticationError,
    OrderError,
    RateLimitError,
)
from config.settings import settings
from core.logger import get_logger

logger = get_logger(__name__)


def rate_limited(max_calls_per_second: int = 3):
    """
    Decorator to rate limit API calls.
    Zerodha allows 3 orders per second.
    
    Args:
        max_calls_per_second: Maximum calls allowed per second
    """
    min_interval = 1.0 / max_calls_per_second
    lock = threading.Lock()
    last_call_time = [0.0]  # Using list to allow modification in closure
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with lock:
                elapsed = time.time() - last_call_time[0]
                if elapsed < min_interval:
                    sleep_time = min_interval - elapsed
                    time.sleep(sleep_time)
                last_call_time[0] = time.time()
            return func(*args, **kwargs)
        return wrapper
    return decorator


def retry_on_error(max_retries: int = 3, delay: float = 1.0):
    """
    Decorator to retry failed API calls.
    
    Args:
        max_retries: Maximum retry attempts
        delay: Delay between retries (with exponential backoff)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (NetworkException, GeneralException) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        sleep_time = delay * (2 ** attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                            f"after {sleep_time}s: {e}"
                        )
                        time.sleep(sleep_time)
                except TokenException as e:
                    # Don't retry token errors - authentication issue
                    raise AuthenticationError(
                        message=str(e),
                        code="TOKEN_ERROR",
                        original_error=e
                    )
            raise last_exception
        return wrapper
    return decorator


class KiteClient(BaseBroker):
    """
    Zerodha Kite Connect client implementation.
    
    Provides a high-level interface to Zerodha's trading API with features:
    - OAuth authentication flow
    - Session management
    - Rate limiting (3 requests/second for orders)
    - Automatic retry with exponential backoff
    - Error handling and logging
    
    Example:
        >>> client = KiteClient()
        >>> login_url = client.get_login_url()
        >>> # Redirect user to login_url
        >>> # After callback with request_token:
        >>> client.authenticate(request_token)
        >>> 
        >>> # Place order
        >>> from BrokerModules.base_broker import OrderRequest, OrderType, TransactionType
        >>> order = OrderRequest(
        ...     symbol="RELIANCE",
        ...     exchange=ExchangeType.NSE,
        ...     transaction_type=TransactionType.BUY,
        ...     quantity=1,
        ...     order_type=OrderType.MARKET,
        ... )
        >>> response = client.place_order(order)
        >>> print(f"Order ID: {response.order_id}")
    """
    
    # Zerodha exchange mappings
    EXCHANGE_MAP = {
        ExchangeType.NSE: "NSE",
        ExchangeType.BSE: "BSE",
        ExchangeType.NFO: "NFO",
        ExchangeType.BFO: "BFO",
    }
    
    REVERSE_EXCHANGE_MAP = {v: k for k, v in EXCHANGE_MAP.items()}
    
    # Order type mappings
    ORDER_TYPE_MAP = {
        OrderType.MARKET: KiteConnect.ORDER_TYPE_MARKET,
        OrderType.LIMIT: KiteConnect.ORDER_TYPE_LIMIT,
        OrderType.STOP_LOSS: KiteConnect.ORDER_TYPE_SL,
        OrderType.STOP_LOSS_MARKET: KiteConnect.ORDER_TYPE_SLM,
    }
    
    # Transaction type mappings
    TRANSACTION_TYPE_MAP = {
        TransactionType.BUY: KiteConnect.TRANSACTION_TYPE_BUY,
        TransactionType.SELL: KiteConnect.TRANSACTION_TYPE_SELL,
    }
    
    # Product type mappings
    PRODUCT_TYPE_MAP = {
        ProductType.CNC: KiteConnect.PRODUCT_CNC,
        ProductType.MIS: KiteConnect.PRODUCT_MIS,
        ProductType.NRML: KiteConnect.PRODUCT_NRML,
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        """
        Initialize Kite client.
        
        Args:
            api_key: Kite Connect API key (default: from settings)
            api_secret: Kite Connect API secret (default: from settings)
            access_token: Pre-existing access token (optional)
        
        Raises:
            ValueError: If API key or secret are not properly configured
        """
        self._api_key = api_key or settings.zerodha.api_key
        self._api_secret = api_secret or settings.zerodha.api_secret
        self._access_token = access_token or settings.zerodha.access_token
        
        # Validate credentials in non-development environments
        if settings.app.env != "development":
            if self._api_key in ("test_key", "", None):
                raise ValueError(
                    "Zerodha API key not configured. "
                    "Set ZERODHA_API_KEY environment variable."
                )
            if self._api_secret in ("test_secret", "", None):
                raise ValueError(
                    "Zerodha API secret not configured. "
                    "Set ZERODHA_API_SECRET environment variable."
                )
        
        # Initialize KiteConnect client
        self._kite = KiteConnect(api_key=self._api_key)
        
        # Set access token if provided
        if self._access_token:
            self._kite.set_access_token(self._access_token)
        
        self._authenticated = bool(self._access_token)
        
        logger.info(f"KiteClient initialized (authenticated={self._authenticated})")
    
    @property
    def name(self) -> str:
        """Return the broker name."""
        return "Zerodha"
    
    @property
    def is_authenticated(self) -> bool:
        """Check if broker session is authenticated."""
        return self._authenticated
    
    @property
    def kite(self) -> KiteConnect:
        """Get the underlying KiteConnect instance."""
        return self._kite
    
    # ==========================================================================
    # Authentication Methods
    # ==========================================================================
    
    def get_login_url(self) -> str:
        """
        Get the login URL for OAuth authentication.
        
        Returns:
            str: Login URL to redirect user to
        """
        return self._kite.login_url()
    
    def authenticate(self, request_token: str) -> bool:
        """
        Authenticate with Zerodha using request token.
        
        Args:
            request_token: OAuth request token received from callback
        
        Returns:
            bool: True if authentication successful
        
        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            logger.info("Authenticating with Zerodha...")
            
            data = self._kite.generate_session(
                request_token=request_token,
                api_secret=self._api_secret
            )
            
            self._access_token = data["access_token"]
            self._kite.set_access_token(self._access_token)
            self._authenticated = True
            
            logger.info(
                f"Authentication successful. User: {data.get('user_id', 'unknown')}"
            )
            
            return True
            
        except TokenException as e:
            logger.error(f"Token error during authentication: {e}")
            raise AuthenticationError(
                message=f"Failed to generate session: {e}",
                code="TOKEN_ERROR",
                original_error=e
            )
        except KiteException as e:
            logger.error(f"Kite error during authentication: {e}")
            raise AuthenticationError(
                message=f"Authentication failed: {e}",
                code="AUTH_ERROR",
                original_error=e
            )
    
    def set_access_token(self, access_token: str) -> None:
        """
        Set access token for authenticated session.
        
        Args:
            access_token: Valid access token
        """
        self._access_token = access_token
        self._kite.set_access_token(access_token)
        self._authenticated = True
        logger.info("Access token set successfully")
    
    def logout(self) -> bool:
        """
        Logout and invalidate the session.
        
        Returns:
            bool: True if logout successful
        """
        try:
            if self._access_token:
                self._kite.invalidate_access_token()
            
            self._access_token = None
            self._authenticated = False
            logger.info("Logged out successfully")
            return True
            
        except KiteException as e:
            logger.error(f"Error during logout: {e}")
            # Still clear local session even if API call fails
            self._access_token = None
            self._authenticated = False
            return True
    
    def _ensure_authenticated(self) -> None:
        """Ensure the client is authenticated before making API calls."""
        if not self._authenticated:
            raise AuthenticationError(
                message="Not authenticated. Please login first.",
                code="NOT_AUTHENTICATED"
            )
    
    # ==========================================================================
    # Order Management Methods
    # ==========================================================================
    
    @rate_limited(max_calls_per_second=3)
    @retry_on_error(max_retries=3)
    def place_order(self, order: OrderRequest) -> OrderResponse:
        """
        Place a new order.
        
        Args:
            order: Order request with all required parameters
        
        Returns:
            OrderResponse: Response with order details
        
        Raises:
            OrderError: If order placement fails
        """
        self._ensure_authenticated()
        
        try:
            logger.info(
                f"Placing {order.transaction_type.value} order for "
                f"{order.quantity} {order.symbol} @ {order.order_type.value}"
            )
            
            # Build order parameters
            params = {
                "tradingsymbol": order.symbol,
                "exchange": self.EXCHANGE_MAP[order.exchange],
                "transaction_type": self.TRANSACTION_TYPE_MAP[order.transaction_type],
                "quantity": order.quantity,
                "order_type": self.ORDER_TYPE_MAP[order.order_type],
                "product": self.PRODUCT_TYPE_MAP[order.product],
                "validity": order.validity,
            }
            
            # Add optional parameters
            if order.price is not None:
                params["price"] = order.price
            
            if order.trigger_price is not None:
                params["trigger_price"] = order.trigger_price
            
            if order.tag:
                params["tag"] = order.tag
            
            # Place order
            order_id = self._kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                **params
            )
            
            logger.info(f"Order placed successfully. Order ID: {order_id}")
            
            # Get order details
            return self.get_order_status(order_id)
            
        except OrderException as e:
            logger.error(f"Order placement failed: {e}")
            raise OrderError(
                message=f"Failed to place order: {e}",
                code="ORDER_FAILED",
                original_error=e
            )
        except InputException as e:
            logger.error(f"Invalid order parameters: {e}")
            raise OrderError(
                message=f"Invalid order parameters: {e}",
                code="INVALID_PARAMS",
                original_error=e
            )
    
    @rate_limited(max_calls_per_second=3)
    @retry_on_error(max_retries=3)
    def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        order_type: Optional[OrderType] = None
    ) -> OrderResponse:
        """
        Modify an existing order.
        
        Args:
            order_id: Order ID to modify
            quantity: New quantity (optional)
            price: New price (optional)
            trigger_price: New trigger price (optional)
            order_type: New order type (optional)
        
        Returns:
            OrderResponse: Updated order details
        
        Raises:
            OrderError: If modification fails
        """
        self._ensure_authenticated()
        
        try:
            logger.info(f"Modifying order {order_id}")
            
            params = {"order_id": order_id}
            
            if quantity is not None:
                params["quantity"] = quantity
            
            if price is not None:
                params["price"] = price
            
            if trigger_price is not None:
                params["trigger_price"] = trigger_price
            
            if order_type is not None:
                params["order_type"] = self.ORDER_TYPE_MAP[order_type]
            
            self._kite.modify_order(
                variety=KiteConnect.VARIETY_REGULAR,
                **params
            )
            
            logger.info(f"Order {order_id} modified successfully")
            
            return self.get_order_status(order_id)
            
        except OrderException as e:
            logger.error(f"Order modification failed: {e}")
            raise OrderError(
                message=f"Failed to modify order: {e}",
                code="MODIFY_FAILED",
                original_error=e
            )
    
    @rate_limited(max_calls_per_second=3)
    @retry_on_error(max_retries=3)
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            bool: True if cancellation successful
        
        Raises:
            OrderError: If cancellation fails
        """
        self._ensure_authenticated()
        
        try:
            logger.info(f"Cancelling order {order_id}")
            
            self._kite.cancel_order(
                variety=KiteConnect.VARIETY_REGULAR,
                order_id=order_id
            )
            
            logger.info(f"Order {order_id} cancelled successfully")
            return True
            
        except OrderException as e:
            logger.error(f"Order cancellation failed: {e}")
            raise OrderError(
                message=f"Failed to cancel order: {e}",
                code="CANCEL_FAILED",
                original_error=e
            )
    
    @retry_on_error(max_retries=3)
    def get_order_status(self, order_id: str) -> OrderResponse:
        """
        Get status of a specific order.
        
        Args:
            order_id: Order ID to query
        
        Returns:
            OrderResponse: Order details with current status
        """
        self._ensure_authenticated()
        
        try:
            orders = self._kite.orders()
            
            for order in orders:
                if order["order_id"] == order_id:
                    return self._parse_order(order)
            
            raise OrderError(
                message=f"Order {order_id} not found",
                code="ORDER_NOT_FOUND"
            )
            
        except KiteException as e:
            logger.error(f"Failed to get order status: {e}")
            raise BrokerError(
                message=f"Failed to get order status: {e}",
                original_error=e
            )
    
    @retry_on_error(max_retries=3)
    def get_orders(self) -> List[OrderResponse]:
        """
        Get all orders for the day.
        
        Returns:
            List[OrderResponse]: List of all orders
        """
        self._ensure_authenticated()
        
        try:
            orders = self._kite.orders()
            return [self._parse_order(order) for order in orders]
            
        except KiteException as e:
            logger.error(f"Failed to get orders: {e}")
            raise BrokerError(
                message=f"Failed to get orders: {e}",
                original_error=e
            )
    
    def _parse_order(self, order: Dict[str, Any]) -> OrderResponse:
        """Parse Kite order response to OrderResponse."""
        return OrderResponse(
            order_id=order["order_id"],
            status=order.get("status", "UNKNOWN"),
            symbol=order["tradingsymbol"],
            transaction_type=order["transaction_type"],
            quantity=order["quantity"],
            order_type=order["order_type"],
            price=order.get("price"),
            average_price=order.get("average_price", 0.0),
            filled_quantity=order.get("filled_quantity", 0),
            pending_quantity=order.get("pending_quantity", order["quantity"]),
            placed_at=order.get("order_timestamp", datetime.now()),
            exchange_order_id=order.get("exchange_order_id"),
            message=order.get("status_message", "")
        )
    
    # ==========================================================================
    # Position Management Methods
    # ==========================================================================
    
    @retry_on_error(max_retries=3)
    def get_positions(self) -> List[PositionData]:
        """
        Get all current positions.
        
        Returns:
            List[PositionData]: List of all positions (day + net)
        """
        self._ensure_authenticated()
        
        try:
            positions_data = self._kite.positions()
            positions = []
            
            # Process net positions
            for pos in positions_data.get("net", []):
                if pos["quantity"] != 0:
                    positions.append(self._parse_position(pos))
            
            return positions
            
        except KiteException as e:
            logger.error(f"Failed to get positions: {e}")
            raise BrokerError(
                message=f"Failed to get positions: {e}",
                original_error=e
            )
    
    def _parse_position(self, pos: Dict[str, Any]) -> PositionData:
        """Parse Kite position data to PositionData."""
        return PositionData(
            symbol=pos["tradingsymbol"],
            exchange=pos["exchange"],
            quantity=pos["quantity"],
            average_price=pos["average_price"],
            last_price=pos["last_price"],
            pnl=pos.get("pnl", 0.0),
            day_pnl=pos.get("day_m2m", 0.0),
            product=pos["product"],
            overnight_quantity=pos.get("overnight_quantity", 0),
            multiplier=pos.get("multiplier", 1.0)
        )
    
    @retry_on_error(max_retries=3)
    def get_holdings(self) -> List[HoldingData]:
        """
        Get all holdings (delivery positions).
        
        Returns:
            List[HoldingData]: List of all holdings
        """
        self._ensure_authenticated()
        
        try:
            holdings = self._kite.holdings()
            return [self._parse_holding(holding) for holding in holdings]
            
        except KiteException as e:
            logger.error(f"Failed to get holdings: {e}")
            raise BrokerError(
                message=f"Failed to get holdings: {e}",
                original_error=e
            )
    
    def _parse_holding(self, holding: Dict[str, Any]) -> HoldingData:
        """Parse Kite holding data to HoldingData."""
        return HoldingData(
            symbol=holding["tradingsymbol"],
            exchange=holding["exchange"],
            isin=holding.get("isin", ""),
            quantity=holding["quantity"],
            average_price=holding["average_price"],
            last_price=holding["last_price"],
            pnl=holding.get("pnl", 0.0),
            day_change=holding.get("day_change", 0.0),
            day_change_pct=holding.get("day_change_percentage", 0.0)
        )
    
    @rate_limited(max_calls_per_second=3)
    @retry_on_error(max_retries=3)
    def convert_position(
        self,
        symbol: str,
        exchange: ExchangeType,
        transaction_type: TransactionType,
        quantity: int,
        from_product: ProductType,
        to_product: ProductType
    ) -> bool:
        """
        Convert position from one product type to another.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            transaction_type: BUY or SELL
            quantity: Quantity to convert
            from_product: Source product type (e.g., MIS)
            to_product: Target product type (e.g., CNC)
        
        Returns:
            bool: True if conversion successful
        """
        self._ensure_authenticated()
        
        try:
            logger.info(
                f"Converting position {symbol}: {quantity} from "
                f"{from_product.value} to {to_product.value}"
            )
            
            self._kite.convert_position(
                exchange=self.EXCHANGE_MAP[exchange],
                tradingsymbol=symbol,
                transaction_type=self.TRANSACTION_TYPE_MAP[transaction_type],
                position_type="day",
                quantity=quantity,
                old_product=self.PRODUCT_TYPE_MAP[from_product],
                new_product=self.PRODUCT_TYPE_MAP[to_product]
            )
            
            logger.info(f"Position conversion successful")
            return True
            
        except KiteException as e:
            logger.error(f"Position conversion failed: {e}")
            raise BrokerError(
                message=f"Failed to convert position: {e}",
                original_error=e
            )
    
    # ==========================================================================
    # Market Data Methods
    # ==========================================================================
    
    @retry_on_error(max_retries=3)
    def get_quote(self, symbol: str, exchange: ExchangeType) -> QuoteData:
        """
        Get current market quote for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
        
        Returns:
            QuoteData: Current market quote
        """
        self._ensure_authenticated()
        
        try:
            instrument = f"{self.EXCHANGE_MAP[exchange]}:{symbol}"
            quotes = self._kite.quote([instrument])
            
            if instrument not in quotes:
                raise BrokerError(
                    message=f"Quote not found for {instrument}",
                    code="QUOTE_NOT_FOUND"
                )
            
            quote = quotes[instrument]
            return self._parse_quote(symbol, exchange, quote)
            
        except KiteException as e:
            logger.error(f"Failed to get quote: {e}")
            raise BrokerError(
                message=f"Failed to get quote: {e}",
                original_error=e
            )
    
    def _parse_quote(
        self, symbol: str, exchange: ExchangeType, quote: Dict[str, Any]
    ) -> QuoteData:
        """Parse Kite quote data to QuoteData."""
        ohlc = quote.get("ohlc", {})
        depth = quote.get("depth", {})
        
        # Get best bid/ask from depth
        buy_depth = depth.get("buy", [{}])
        sell_depth = depth.get("sell", [{}])
        
        best_bid = buy_depth[0] if buy_depth else {}
        best_ask = sell_depth[0] if sell_depth else {}
        
        return QuoteData(
            symbol=symbol,
            exchange=self.EXCHANGE_MAP[exchange],
            last_price=quote.get("last_price", 0.0),
            open_price=ohlc.get("open", 0.0),
            high_price=ohlc.get("high", 0.0),
            low_price=ohlc.get("low", 0.0),
            close_price=ohlc.get("close", 0.0),
            volume=quote.get("volume", 0),
            bid_price=best_bid.get("price", 0.0),
            ask_price=best_ask.get("price", 0.0),
            bid_quantity=best_bid.get("quantity", 0),
            ask_quantity=best_ask.get("quantity", 0),
            timestamp=quote.get("timestamp", datetime.now())
        )
    
    @retry_on_error(max_retries=3)
    def get_ltp(self, symbols: List[tuple]) -> Dict[str, float]:
        """
        Get Last Traded Price for multiple symbols.
        
        Args:
            symbols: List of (symbol, exchange) tuples
        
        Returns:
            Dict[str, float]: Symbol -> LTP mapping
        """
        self._ensure_authenticated()
        
        try:
            instruments = [
                f"{self.EXCHANGE_MAP[exchange]}:{symbol}"
                for symbol, exchange in symbols
            ]
            
            ltp_data = self._kite.ltp(instruments)
            
            result = {}
            for instrument, data in ltp_data.items():
                # Extract symbol from "EXCHANGE:SYMBOL" format
                symbol = instrument.split(":")[1]
                result[symbol] = data.get("last_price", 0.0)
            
            return result
            
        except KiteException as e:
            logger.error(f"Failed to get LTP: {e}")
            raise BrokerError(
                message=f"Failed to get LTP: {e}",
                original_error=e
            )
    
    @retry_on_error(max_retries=3)
    def get_ohlc(self, symbols: List[tuple]) -> Dict[str, Dict[str, float]]:
        """
        Get OHLC data for multiple symbols.
        
        Args:
            symbols: List of (symbol, exchange) tuples
        
        Returns:
            Dict[str, Dict]: Symbol -> OHLC mapping
        """
        self._ensure_authenticated()
        
        try:
            instruments = [
                f"{self.EXCHANGE_MAP[exchange]}:{symbol}"
                for symbol, exchange in symbols
            ]
            
            ohlc_data = self._kite.ohlc(instruments)
            
            result = {}
            for instrument, data in ohlc_data.items():
                symbol = instrument.split(":")[1]
                ohlc = data.get("ohlc", {})
                result[symbol] = {
                    "open": ohlc.get("open", 0.0),
                    "high": ohlc.get("high", 0.0),
                    "low": ohlc.get("low", 0.0),
                    "close": ohlc.get("close", 0.0),
                    "last_price": data.get("last_price", 0.0)
                }
            
            return result
            
        except KiteException as e:
            logger.error(f"Failed to get OHLC: {e}")
            raise BrokerError(
                message=f"Failed to get OHLC: {e}",
                original_error=e
            )
    
    @retry_on_error(max_retries=3)
    def get_historical_data(
        self,
        symbol: str,
        exchange: ExchangeType,
        from_date: datetime,
        to_date: datetime,
        interval: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV data.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            from_date: Start date
            to_date: End date
            interval: Data interval (minute, day, etc.)
        
        Returns:
            List[Dict]: Historical OHLCV data
        """
        self._ensure_authenticated()
        
        try:
            # Get instrument token
            instrument_token = self._get_instrument_token(symbol, exchange)
            
            if not instrument_token:
                raise BrokerError(
                    message=f"Instrument token not found for {symbol}",
                    code="INSTRUMENT_NOT_FOUND"
                )
            
            data = self._kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=interval
            )
            
            return data
            
        except KiteException as e:
            logger.error(f"Failed to get historical data: {e}")
            raise BrokerError(
                message=f"Failed to get historical data: {e}",
                original_error=e
            )
    
    def _get_instrument_token(self, symbol: str, exchange: ExchangeType) -> Optional[int]:
        """Get instrument token for a symbol."""
        try:
            instruments = self._kite.instruments(self.EXCHANGE_MAP[exchange])
            
            for instrument in instruments:
                if instrument["tradingsymbol"] == symbol:
                    return instrument["instrument_token"]
            
            return None
            
        except KiteException as e:
            logger.error(f"Failed to get instrument token: {e}")
            return None
    
    # ==========================================================================
    # Account Methods
    # ==========================================================================
    
    @retry_on_error(max_retries=3)
    def get_margins(self) -> MarginData:
        """
        Get account margins.
        
        Returns:
            MarginData: Account margin details
        """
        self._ensure_authenticated()
        
        try:
            margins = self._kite.margins()
            equity = margins.get("equity", {})
            
            return MarginData(
                available_cash=equity.get("available", {}).get("cash", 0.0),
                used_margin=equity.get("utilised", {}).get("debits", 0.0),
                total_margin=equity.get("net", 0.0),
                available_margin=equity.get("available", {}).get("live_balance", 0.0)
            )
            
        except KiteException as e:
            logger.error(f"Failed to get margins: {e}")
            raise BrokerError(
                message=f"Failed to get margins: {e}",
                original_error=e
            )
    
    @retry_on_error(max_retries=3)
    def get_profile(self) -> Dict[str, Any]:
        """
        Get user profile.
        
        Returns:
            Dict: User profile information
        """
        self._ensure_authenticated()
        
        try:
            return self._kite.profile()
            
        except KiteException as e:
            logger.error(f"Failed to get profile: {e}")
            raise BrokerError(
                message=f"Failed to get profile: {e}",
                original_error=e
            )
    
    # ==========================================================================
    # Utility Methods
    # ==========================================================================
    
    def get_instruments(self, exchange: Optional[ExchangeType] = None) -> List[Dict[str, Any]]:
        """
        Get list of tradeable instruments.
        
        Args:
            exchange: Filter by exchange (optional)
        
        Returns:
            List[Dict]: List of instruments
        """
        self._ensure_authenticated()
        
        try:
            if exchange:
                return self._kite.instruments(self.EXCHANGE_MAP[exchange])
            else:
                # Get instruments from all exchanges
                instruments = []
                for ex in ExchangeType:
                    try:
                        instruments.extend(self._kite.instruments(self.EXCHANGE_MAP[ex]))
                    except Exception:
                        continue
                return instruments
                
        except KiteException as e:
            logger.error(f"Failed to get instruments: {e}")
            raise BrokerError(
                message=f"Failed to get instruments: {e}",
                original_error=e
            )
