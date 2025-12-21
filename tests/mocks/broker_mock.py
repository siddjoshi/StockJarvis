# tests/mocks/broker_mock.py
"""
Mock broker implementation for testing.
Simulates broker API responses without making actual API calls.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import random
from enum import Enum


class OrderType(Enum):
    """Order types."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class OrderStatus(Enum):
    """Order status."""
    PENDING = "PENDING"
    PLACED = "PLACED"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class TransactionType(Enum):
    """Transaction type."""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class MockOrder:
    """Mock order representation."""
    order_id: str
    symbol: str
    transaction_type: TransactionType
    quantity: int
    order_type: OrderType
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    average_price: float = 0.0
    placed_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    message: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert order to dictionary."""
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "transaction_type": self.transaction_type.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "price": self.price,
            "status": self.status.value,
            "filled_quantity": self.filled_quantity,
            "average_price": self.average_price,
            "placed_at": self.placed_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "message": self.message
        }


@dataclass
class MockPosition:
    """Mock position representation."""
    symbol: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    day_pnl: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert position to dictionary."""
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "last_price": self.last_price,
            "pnl": self.pnl,
            "day_pnl": self.day_pnl,
            "value": self.quantity * self.last_price
        }


@dataclass
class MockQuote:
    """Mock quote representation."""
    symbol: str
    last_price: float
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    bid: float
    ask: float
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert quote to dictionary."""
        return {
            "symbol": self.symbol,
            "last_price": self.last_price,
            "open": self.open_price,
            "high": self.high_price,
            "low": self.low_price,
            "close": self.close_price,
            "volume": self.volume,
            "bid": self.bid,
            "ask": self.ask,
            "timestamp": self.timestamp.isoformat()
        }


class MockBrokerClient:
    """
    Mock broker client for testing.
    
    Simulates broker API without making actual calls.
    Useful for testing trading logic, order management, and position tracking.
    
    Example:
        broker = MockBrokerClient()
        order = broker.place_order("RELIANCE", "BUY", 10, "MARKET")
        positions = broker.get_positions()
        quote = broker.get_quote("RELIANCE")
    """
    
    def __init__(
        self,
        initial_positions: Optional[List[Dict[str, Any]]] = None,
        fail_mode: bool = False,
        delay_seconds: float = 0.0
    ):
        """
        Initialize mock broker client.
        
        Args:
            initial_positions: Initial positions (for testing existing positions)
            fail_mode: If True, simulate API failures
            delay_seconds: Simulate network delay
        """
        self.orders: Dict[str, MockOrder] = {}
        self.positions: Dict[str, MockPosition] = {}
        self.fail_mode = fail_mode
        self.delay_seconds = delay_seconds
        self._order_counter = 1000
        
        # Initialize positions if provided
        if initial_positions:
            for pos in initial_positions:
                self.positions[pos["symbol"]] = MockPosition(**pos)
        
        # Mock price data for different symbols
        self.mock_prices = {
            "RELIANCE": 2450.0,
            "TCS": 3500.0,
            "INFY": 1450.0,
            "HDFCBANK": 1650.0,
            "ICICIBANK": 950.0,
            "SBIN": 580.0,
            "WIPRO": 420.0,
            "LT": 3200.0,
            "AXISBANK": 1050.0,
            "BHARTIARTL": 850.0,
        }
    
    def _generate_order_id(self) -> str:
        """Generate unique order ID."""
        self._order_counter += 1
        return f"MOCK{self._order_counter:06d}"
    
    def _check_fail_mode(self) -> None:
        """Raise exception if in fail mode."""
        if self.fail_mode:
            raise Exception("Mock broker in fail mode - simulating API error")
    
    def _get_current_price(self, symbol: str) -> float:
        """
        Get current price for symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Current price with some random variation
        """
        base_price = self.mock_prices.get(symbol, 1000.0)
        # Add random variation ±2%
        variation = random.uniform(-0.02, 0.02)
        return round(base_price * (1 + variation), 2)
    
    def place_order(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        order_type: str,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Place a new order.
        
        Args:
            symbol: Stock symbol
            transaction_type: "BUY" or "SELL"
            quantity: Order quantity
            order_type: "MARKET", "LIMIT", "STOP_LOSS", etc.
            price: Limit price (for LIMIT orders)
            trigger_price: Trigger price (for stop loss orders)
            **kwargs: Additional order parameters
        
        Returns:
            Dict: Order response with order_id and status
        
        Example:
            order = broker.place_order("RELIANCE", "BUY", 10, "MARKET")
            assert order["status"] == "COMPLETE"
        """
        self._check_fail_mode()
        
        order_id = self._generate_order_id()
        current_price = self._get_current_price(symbol)
        
        # Create order
        order = MockOrder(
            order_id=order_id,
            symbol=symbol,
            transaction_type=TransactionType[transaction_type],
            quantity=quantity,
            order_type=OrderType[order_type],
            price=price,
            status=OrderStatus.PLACED
        )
        
        # For MARKET orders, fill immediately at current price
        if order_type == "MARKET":
            order.status = OrderStatus.COMPLETE
            order.filled_quantity = quantity
            order.average_price = current_price
            order.message = "Order executed successfully"
            
            # Update positions
            self._update_position(symbol, transaction_type, quantity, current_price)
        
        # For LIMIT orders, check if price is met
        elif order_type == "LIMIT":
            if price:
                if (transaction_type == "BUY" and current_price <= price) or \
                   (transaction_type == "SELL" and current_price >= price):
                    order.status = OrderStatus.COMPLETE
                    order.filled_quantity = quantity
                    order.average_price = price
                    self._update_position(symbol, transaction_type, quantity, price)
                else:
                    order.message = "Limit order placed, waiting for price"
        
        self.orders[order_id] = order
        
        return order.to_dict()
    
    def modify_order(
        self,
        order_id: str,
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        order_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Modify an existing order.
        
        Args:
            order_id: Order ID to modify
            quantity: New quantity
            price: New price
            order_type: New order type
        
        Returns:
            Dict: Modified order response
        
        Example:
            modified = broker.modify_order("MOCK001000", quantity=15, price=2500.0)
        """
        self._check_fail_mode()
        
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        order = self.orders[order_id]
        
        # Can only modify pending/placed orders
        if order.status not in [OrderStatus.PENDING, OrderStatus.PLACED]:
            raise ValueError(f"Cannot modify order in status {order.status.value}")
        
        # Update order parameters
        if quantity is not None:
            order.quantity = quantity
        if price is not None:
            order.price = price
        if order_type is not None:
            order.order_type = OrderType[order_type]
        
        order.updated_at = datetime.now()
        order.message = "Order modified successfully"
        
        return order.to_dict()
    
    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        """
        Cancel an existing order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            Dict: Cancellation response
        
        Example:
            result = broker.cancel_order("MOCK001000")
            assert result["status"] == "CANCELLED"
        """
        self._check_fail_mode()
        
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        order = self.orders[order_id]
        
        # Can only cancel pending/placed orders
        if order.status not in [OrderStatus.PENDING, OrderStatus.PLACED]:
            raise ValueError(f"Cannot cancel order in status {order.status.value}")
        
        order.status = OrderStatus.CANCELLED
        order.updated_at = datetime.now()
        order.message = "Order cancelled successfully"
        
        return order.to_dict()
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Get order status.
        
        Args:
            order_id: Order ID
        
        Returns:
            Dict: Order details
        
        Example:
            status = broker.get_order_status("MOCK001000")
            print(status["status"])
        """
        self._check_fail_mode()
        
        if order_id not in self.orders:
            raise ValueError(f"Order {order_id} not found")
        
        return self.orders[order_id].to_dict()
    
    def get_orders(self) -> List[Dict[str, Any]]:
        """
        Get all orders.
        
        Returns:
            List[Dict]: List of all orders
        
        Example:
            orders = broker.get_orders()
            print(f"Total orders: {len(orders)}")
        """
        self._check_fail_mode()
        
        return [order.to_dict() for order in self.orders.values()]
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current positions.
        
        Returns:
            List[Dict]: List of current positions
        
        Example:
            positions = broker.get_positions()
            for pos in positions:
                print(f"{pos['symbol']}: {pos['quantity']} @ {pos['average_price']}")
        """
        self._check_fail_mode()
        
        # Update positions with current prices
        for symbol, position in self.positions.items():
            current_price = self._get_current_price(symbol)
            position.last_price = current_price
            position.pnl = (current_price - position.average_price) * position.quantity
        
        return [pos.to_dict() for pos in self.positions.values()]
    
    def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get current quote for a symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Dict: Quote data with OHLC, volume, bid/ask
        
        Example:
            quote = broker.get_quote("RELIANCE")
            print(f"Last price: {quote['last_price']}")
        """
        self._check_fail_mode()
        
        current_price = self._get_current_price(symbol)
        
        # Generate realistic OHLC
        quote = MockQuote(
            symbol=symbol,
            last_price=current_price,
            open_price=current_price * random.uniform(0.98, 1.02),
            high_price=current_price * random.uniform(1.00, 1.03),
            low_price=current_price * random.uniform(0.97, 1.00),
            close_price=current_price,
            volume=random.randint(100000, 5000000),
            bid=current_price * 0.9995,
            ask=current_price * 1.0005
        )
        
        return quote.to_dict()
    
    def get_historical_data(
        self,
        symbol: str,
        from_date: datetime,
        to_date: datetime,
        interval: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Get historical OHLCV data.
        
        Args:
            symbol: Stock symbol
            from_date: Start date
            to_date: End date
            interval: Data interval ("minute", "day")
        
        Returns:
            List[Dict]: Historical OHLCV data
        
        Example:
            data = broker.get_historical_data(
                "RELIANCE",
                datetime.now() - timedelta(days=30),
                datetime.now()
            )
        """
        self._check_fail_mode()
        
        base_price = self.mock_prices.get(symbol, 1000.0)
        data = []
        
        # Generate data points
        current_date = from_date
        days = (to_date - from_date).days
        
        for i in range(days + 1):
            # Random walk for price
            price = base_price * (1 + random.uniform(-0.02, 0.02))
            
            data.append({
                "timestamp": current_date + timedelta(days=i),
                "open": round(price * random.uniform(0.99, 1.01), 2),
                "high": round(price * random.uniform(1.00, 1.02), 2),
                "low": round(price * random.uniform(0.98, 1.00), 2),
                "close": round(price, 2),
                "volume": random.randint(100000, 3000000)
            })
        
        return data
    
    def get_holdings(self) -> List[Dict[str, Any]]:
        """
        Get long-term holdings.
        
        Returns:
            List[Dict]: List of holdings
        """
        self._check_fail_mode()
        
        # Mock holdings (different from intraday positions)
        return [
            {
                "symbol": "RELIANCE",
                "quantity": 50,
                "average_price": 2300.0,
                "last_price": self._get_current_price("RELIANCE"),
                "pnl": (self._get_current_price("RELIANCE") - 2300.0) * 50
            }
        ]
    
    def get_margins(self) -> Dict[str, Any]:
        """
        Get account margins.
        
        Returns:
            Dict: Margin details
        """
        self._check_fail_mode()
        
        return {
            "equity": {
                "available": 100000.0,
                "utilised": 25000.0,
                "net": 125000.0
            },
            "commodity": {
                "available": 0.0,
                "utilised": 0.0,
                "net": 0.0
            }
        }
    
    def _update_position(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        price: float
    ) -> None:
        """
        Update position after order execution.
        
        Args:
            symbol: Stock symbol
            transaction_type: "BUY" or "SELL"
            quantity: Quantity traded
            price: Execution price
        """
        if symbol not in self.positions:
            # New position
            if transaction_type == "BUY":
                self.positions[symbol] = MockPosition(
                    symbol=symbol,
                    quantity=quantity,
                    average_price=price,
                    last_price=price,
                    pnl=0.0
                )
        else:
            # Update existing position
            position = self.positions[symbol]
            
            if transaction_type == "BUY":
                # Add to position
                total_cost = (position.quantity * position.average_price) + (quantity * price)
                position.quantity += quantity
                position.average_price = total_cost / position.quantity
            else:  # SELL
                # Reduce position
                position.quantity -= quantity
                if position.quantity <= 0:
                    # Position closed
                    del self.positions[symbol]
    
    def reset(self) -> None:
        """
        Reset broker state (useful for test cleanup).
        
        Example:
            broker.reset()  # Clear all orders and positions
        """
        self.orders.clear()
        self.positions.clear()
        self._order_counter = 1000
    
    def set_fail_mode(self, fail: bool) -> None:
        """
        Enable/disable fail mode for testing error handling.
        
        Args:
            fail: True to enable fail mode
        
        Example:
            broker.set_fail_mode(True)
            with pytest.raises(Exception):
                broker.place_order("RELIANCE", "BUY", 10, "MARKET")
        """
        self.fail_mode = fail


# ============================================================================
# Helper Functions
# ============================================================================

def create_mock_broker_with_positions(positions: List[Dict[str, Any]]) -> MockBrokerClient:
    """
    Create mock broker with initial positions.
    
    Args:
        positions: List of position dictionaries
    
    Returns:
        MockBrokerClient: Configured mock broker
    
    Example:
        positions = [
            {"symbol": "RELIANCE", "quantity": 10, "average_price": 2400.0, 
             "last_price": 2450.0, "pnl": 500.0}
        ]
        broker = create_mock_broker_with_positions(positions)
    """
    return MockBrokerClient(initial_positions=positions)


def create_failing_mock_broker() -> MockBrokerClient:
    """
    Create mock broker that simulates API failures.
    
    Returns:
        MockBrokerClient: Mock broker in fail mode
    
    Example:
        broker = create_failing_mock_broker()
        with pytest.raises(Exception):
            broker.get_positions()
    """
    return MockBrokerClient(fail_mode=True)


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example usage
    broker = MockBrokerClient()
    
    # Place orders
    print("Placing BUY order...")
    order = broker.place_order("RELIANCE", "BUY", 10, "MARKET")
    print(f"Order: {order['order_id']} - Status: {order['status']}")
    
    # Get positions
    print("\nCurrent positions:")
    positions = broker.get_positions()
    for pos in positions:
        print(f"  {pos['symbol']}: {pos['quantity']} @ {pos['average_price']} (P&L: {pos['pnl']})")
    
    # Get quote
    print("\nCurrent quote for RELIANCE:")
    quote = broker.get_quote("RELIANCE")
    print(f"  Last: {quote['last_price']}, Bid: {quote['bid']}, Ask: {quote['ask']}")
    
    # Get historical data
    print("\nHistorical data (last 5 days):")
    hist_data = broker.get_historical_data(
        "RELIANCE",
        datetime.now() - timedelta(days=5),
        datetime.now()
    )
    for candle in hist_data[-5:]:
        print(f"  {candle['timestamp'].date()}: Close={candle['close']}, Volume={candle['volume']}")
