# BrokerModules/base_broker.py
"""
Abstract base class for broker integrations.
All broker implementations must inherit from this class and implement the abstract methods.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderType(Enum):
    """Order types supported by brokers."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "SL"
    STOP_LOSS_MARKET = "SL-M"


class TransactionType(Enum):
    """Transaction types."""
    BUY = "BUY"
    SELL = "SELL"


class ProductType(Enum):
    """Product types for orders."""
    CNC = "CNC"  # Cash and Carry (delivery)
    MIS = "MIS"  # Margin Intraday Square-off
    NRML = "NRML"  # Normal (F&O)


class ExchangeType(Enum):
    """Exchange types."""
    NSE = "NSE"
    BSE = "BSE"
    NFO = "NFO"  # NSE F&O
    BFO = "BFO"  # BSE F&O


@dataclass
class OrderRequest:
    """Order request data structure."""
    symbol: str
    exchange: ExchangeType
    transaction_type: TransactionType
    quantity: int
    order_type: OrderType
    product: ProductType = ProductType.CNC
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    validity: str = "DAY"
    tag: Optional[str] = None


@dataclass
class OrderResponse:
    """Order response from broker."""
    order_id: str
    status: str
    symbol: str
    transaction_type: str
    quantity: int
    order_type: str
    price: Optional[float]
    average_price: float
    filled_quantity: int
    pending_quantity: int
    placed_at: datetime
    exchange_order_id: Optional[str] = None
    message: str = ""


@dataclass
class PositionData:
    """Position data from broker."""
    symbol: str
    exchange: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    day_pnl: float
    product: str
    overnight_quantity: int = 0
    multiplier: float = 1.0


@dataclass
class HoldingData:
    """Holdings data from broker."""
    symbol: str
    exchange: str
    isin: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    day_change: float
    day_change_pct: float


@dataclass
class QuoteData:
    """Market quote data."""
    symbol: str
    exchange: str
    last_price: float
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    bid_price: float
    ask_price: float
    bid_quantity: int
    ask_quantity: int
    timestamp: datetime


@dataclass
class MarginData:
    """Account margin data."""
    available_cash: float
    used_margin: float
    total_margin: float
    available_margin: float


class BrokerError(Exception):
    """Base exception for broker errors."""
    
    def __init__(self, message: str, code: Optional[str] = None, original_error: Optional[Exception] = None):
        self.message = message
        self.code = code
        self.original_error = original_error
        super().__init__(self.message)
    
    def __str__(self) -> str:
        """Return a string representation including code and original error context."""
        parts = []
        if self.code:
            parts.append(f"[{self.code}]")
        if self.message:
            parts.append(self.message)
        if self.original_error:
            parts.append(
                f"(caused by {type(self.original_error).__name__}: {self.original_error})"
            )
        return " ".join(parts) if parts else super().__str__()


class AuthenticationError(BrokerError):
    """Raised when authentication fails."""
    pass


class OrderError(BrokerError):
    """Raised when order operation fails."""
    pass


class RateLimitError(BrokerError):
    """Raised when rate limit is exceeded."""
    pass


class BaseBroker(ABC):
    """
    Abstract base class for broker integrations.
    
    All broker implementations must inherit from this class and implement
    all abstract methods. This ensures a consistent interface across
    different broker APIs.
    
    Example:
        class ZerodhaBroker(BaseBroker):
            def authenticate(self):
                # Zerodha-specific authentication
                pass
            
            def place_order(self, order: OrderRequest) -> OrderResponse:
                # Zerodha-specific order placement
                pass
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the broker name."""
        pass
    
    @property
    @abstractmethod
    def is_authenticated(self) -> bool:
        """Check if broker session is authenticated."""
        pass
    
    # ==========================================================================
    # Authentication Methods
    # ==========================================================================
    
    @abstractmethod
    def get_login_url(self) -> str:
        """
        Get the login URL for OAuth authentication.
        
        Returns:
            str: Login URL to redirect user to
        """
        pass
    
    @abstractmethod
    def authenticate(self, request_token: str) -> bool:
        """
        Authenticate with the broker using request token.
        
        Args:
            request_token: OAuth request token received from callback
        
        Returns:
            bool: True if authentication successful
        
        Raises:
            AuthenticationError: If authentication fails
        """
        pass
    
    @abstractmethod
    def set_access_token(self, access_token: str) -> None:
        """
        Set access token for authenticated session.
        
        Args:
            access_token: Valid access token
        """
        pass
    
    @abstractmethod
    def logout(self) -> bool:
        """
        Logout and invalidate the session.
        
        Returns:
            bool: True if logout successful
        """
        pass
    
    # ==========================================================================
    # Order Management Methods
    # ==========================================================================
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> OrderResponse:
        """
        Get status of a specific order.
        
        Args:
            order_id: Order ID to query
        
        Returns:
            OrderResponse: Order details with current status
        """
        pass
    
    @abstractmethod
    def get_orders(self) -> List[OrderResponse]:
        """
        Get all orders for the day.
        
        Returns:
            List[OrderResponse]: List of all orders
        """
        pass
    
    # ==========================================================================
    # Position Management Methods
    # ==========================================================================
    
    @abstractmethod
    def get_positions(self) -> List[PositionData]:
        """
        Get all current positions.
        
        Returns:
            List[PositionData]: List of all positions (day + net)
        """
        pass
    
    @abstractmethod
    def get_holdings(self) -> List[HoldingData]:
        """
        Get all holdings (delivery positions).
        
        Returns:
            List[HoldingData]: List of all holdings
        """
        pass
    
    @abstractmethod
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
        pass
    
    # ==========================================================================
    # Market Data Methods
    # ==========================================================================
    
    @abstractmethod
    def get_quote(self, symbol: str, exchange: ExchangeType) -> QuoteData:
        """
        Get current market quote for a symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
        
        Returns:
            QuoteData: Current market quote
        """
        pass
    
    @abstractmethod
    def get_ltp(self, symbols: List[tuple]) -> Dict[str, float]:
        """
        Get Last Traded Price for multiple symbols.
        
        Args:
            symbols: List of (symbol, exchange) tuples
        
        Returns:
            Dict[str, float]: Symbol -> LTP mapping
        """
        pass
    
    @abstractmethod
    def get_ohlc(self, symbols: List[tuple]) -> Dict[str, Dict[str, float]]:
        """
        Get OHLC data for multiple symbols.
        
        Args:
            symbols: List of (symbol, exchange) tuples
        
        Returns:
            Dict[str, Dict]: Symbol -> OHLC mapping
        """
        pass
    
    @abstractmethod
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
        pass
    
    # ==========================================================================
    # Account Methods
    # ==========================================================================
    
    @abstractmethod
    def get_margins(self) -> MarginData:
        """
        Get account margins.
        
        Returns:
            MarginData: Account margin details
        """
        pass
    
    @abstractmethod
    def get_profile(self) -> Dict[str, Any]:
        """
        Get user profile.
        
        Returns:
            Dict: User profile information
        """
        pass
