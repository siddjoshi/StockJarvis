# BrokerModules/Zerodha/order_manager.py
"""
Order management module for Zerodha Kite Connect.
Provides high-level order operations with validation and audit logging.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from BrokerModules.base_broker import (
    OrderRequest,
    OrderResponse,
    OrderType,
    TransactionType,
    ProductType,
    ExchangeType,
    OrderError,
)
from BrokerModules.Zerodha.kite_client import KiteClient
from core.logger import get_logger

logger = get_logger(__name__)


class OrderVariety(Enum):
    """Order varieties supported by Zerodha."""
    REGULAR = "regular"
    AMO = "amo"  # After Market Order
    ICEBERG = "iceberg"
    AUCTION = "auction"


class ValidityType(Enum):
    """Order validity types."""
    DAY = "DAY"
    IOC = "IOC"  # Immediate or Cancel
    TTL = "TTL"  # Time to Live (in minutes)


class OrderManager:
    """
    High-level order management for Zerodha.
    
    Provides order placement, modification, cancellation with:
    - Input validation
    - Pre-trade checks
    - Audit logging
    - Order tracking
    
    Example:
        >>> from BrokerModules.Zerodha.kite_client import KiteClient
        >>> client = KiteClient()
        >>> # ... authenticate client
        >>> 
        >>> order_manager = OrderManager(client)
        >>> 
        >>> # Place market order
        >>> order = order_manager.place_market_order(
        ...     symbol="RELIANCE",
        ...     exchange=ExchangeType.NSE,
        ...     transaction_type=TransactionType.BUY,
        ...     quantity=10
        ... )
        >>> print(f"Order ID: {order.order_id}")
    """
    
    def __init__(self, client: KiteClient):
        """
        Initialize order manager.
        
        Args:
            client: Authenticated KiteClient instance
        """
        self._client = client
        self._order_history: List[Dict[str, Any]] = []
        
        logger.info("OrderManager initialized")
    
    # ==========================================================================
    # Market Orders
    # ==========================================================================
    
    def place_market_order(
        self,
        symbol: str,
        exchange: ExchangeType,
        transaction_type: TransactionType,
        quantity: int,
        product: ProductType = ProductType.CNC,
        tag: Optional[str] = None
    ) -> OrderResponse:
        """
        Place a market order.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            transaction_type: BUY or SELL
            quantity: Order quantity
            product: Product type (CNC/MIS/NRML)
            tag: Optional order tag for tracking
        
        Returns:
            OrderResponse: Order response
        
        Example:
            >>> order = order_manager.place_market_order(
            ...     symbol="RELIANCE",
            ...     exchange=ExchangeType.NSE,
            ...     transaction_type=TransactionType.BUY,
            ...     quantity=10
            ... )
        """
        self._validate_order_params(symbol, quantity)
        
        order_request = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=OrderType.MARKET,
            product=product,
            tag=tag
        )
        
        response = self._client.place_order(order_request)
        self._log_order_activity("PLACE_MARKET", order_request, response)
        
        return response
    
    # ==========================================================================
    # Limit Orders
    # ==========================================================================
    
    def place_limit_order(
        self,
        symbol: str,
        exchange: ExchangeType,
        transaction_type: TransactionType,
        quantity: int,
        price: float,
        product: ProductType = ProductType.CNC,
        validity: str = "DAY",
        tag: Optional[str] = None
    ) -> OrderResponse:
        """
        Place a limit order.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            transaction_type: BUY or SELL
            quantity: Order quantity
            price: Limit price
            product: Product type (CNC/MIS/NRML)
            validity: Order validity (DAY/IOC)
            tag: Optional order tag for tracking
        
        Returns:
            OrderResponse: Order response
        
        Example:
            >>> order = order_manager.place_limit_order(
            ...     symbol="RELIANCE",
            ...     exchange=ExchangeType.NSE,
            ...     transaction_type=TransactionType.BUY,
            ...     quantity=10,
            ...     price=2450.00
            ... )
        """
        self._validate_order_params(symbol, quantity, price=price)
        
        order_request = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            product=product,
            price=price,
            validity=validity,
            tag=tag
        )
        
        response = self._client.place_order(order_request)
        self._log_order_activity("PLACE_LIMIT", order_request, response)
        
        return response
    
    # ==========================================================================
    # Stop Loss Orders
    # ==========================================================================
    
    def place_stop_loss_order(
        self,
        symbol: str,
        exchange: ExchangeType,
        transaction_type: TransactionType,
        quantity: int,
        trigger_price: float,
        price: Optional[float] = None,
        product: ProductType = ProductType.CNC,
        tag: Optional[str] = None
    ) -> OrderResponse:
        """
        Place a stop loss order.
        
        If price is provided, places SL (Stop Loss Limit) order.
        If price is not provided, places SL-M (Stop Loss Market) order.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            transaction_type: BUY or SELL
            quantity: Order quantity
            trigger_price: Stop loss trigger price
            price: Limit price for SL order (optional, if None uses SL-M)
            product: Product type (CNC/MIS/NRML)
            tag: Optional order tag for tracking
        
        Returns:
            OrderResponse: Order response
        
        Example:
            >>> # Stop Loss Market order
            >>> order = order_manager.place_stop_loss_order(
            ...     symbol="RELIANCE",
            ...     exchange=ExchangeType.NSE,
            ...     transaction_type=TransactionType.SELL,
            ...     quantity=10,
            ...     trigger_price=2400.00
            ... )
            >>> 
            >>> # Stop Loss Limit order
            >>> order = order_manager.place_stop_loss_order(
            ...     symbol="RELIANCE",
            ...     exchange=ExchangeType.NSE,
            ...     transaction_type=TransactionType.SELL,
            ...     quantity=10,
            ...     trigger_price=2400.00,
            ...     price=2395.00
            ... )
        """
        self._validate_order_params(symbol, quantity, trigger_price=trigger_price)
        
        order_type = OrderType.STOP_LOSS if price else OrderType.STOP_LOSS_MARKET
        
        order_request = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=order_type,
            product=product,
            price=price,
            trigger_price=trigger_price,
            tag=tag
        )
        
        response = self._client.place_order(order_request)
        self._log_order_activity("PLACE_SL", order_request, response)
        
        return response
    
    # ==========================================================================
    # Order Modification
    # ==========================================================================
    
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
            quantity: New quantity
            price: New price
            trigger_price: New trigger price
            order_type: New order type
        
        Returns:
            OrderResponse: Updated order response
        
        Example:
            >>> modified = order_manager.modify_order(
            ...     order_id="123456",
            ...     quantity=15,
            ...     price=2460.00
            ... )
        """
        if quantity is not None and quantity <= 0:
            raise OrderError(
                message="Quantity must be positive",
                code="INVALID_QUANTITY"
            )
        
        if price is not None and price <= 0:
            raise OrderError(
                message="Price must be positive",
                code="INVALID_PRICE"
            )
        
        response = self._client.modify_order(
            order_id=order_id,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            order_type=order_type
        )
        
        self._log_order_activity(
            "MODIFY",
            None,
            response,
            extra={"order_id": order_id, "modifications": {
                "quantity": quantity,
                "price": price,
                "trigger_price": trigger_price,
                "order_type": order_type.value if order_type else None
            }}
        )
        
        return response
    
    # ==========================================================================
    # Order Cancellation
    # ==========================================================================
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            order_id: Order ID to cancel
        
        Returns:
            bool: True if cancelled successfully
        
        Example:
            >>> success = order_manager.cancel_order("123456")
            >>> if success:
            ...     print("Order cancelled")
        """
        result = self._client.cancel_order(order_id)
        
        self._log_order_activity(
            "CANCEL",
            None,
            None,
            extra={"order_id": order_id, "success": result}
        )
        
        return result
    
    def cancel_all_orders(self) -> Dict[str, bool]:
        """
        Cancel all pending orders.
        
        Returns:
            Dict[str, bool]: Order ID -> cancellation success mapping
        
        Example:
            >>> results = order_manager.cancel_all_orders()
            >>> for order_id, success in results.items():
            ...     print(f"{order_id}: {'cancelled' if success else 'failed'}")
        """
        results = {}
        orders = self.get_pending_orders()
        
        for order in orders:
            try:
                success = self.cancel_order(order.order_id)
                results[order.order_id] = success
            except Exception as e:
                logger.error(f"Failed to cancel order {order.order_id}: {e}")
                results[order.order_id] = False
        
        logger.info(f"Cancel all orders: {sum(results.values())}/{len(results)} successful")
        
        return results
    
    # ==========================================================================
    # Order Queries
    # ==========================================================================
    
    def get_order_status(self, order_id: str) -> OrderResponse:
        """
        Get status of a specific order.
        
        Args:
            order_id: Order ID to query
        
        Returns:
            OrderResponse: Current order status
        """
        return self._client.get_order_status(order_id)
    
    def get_all_orders(self) -> List[OrderResponse]:
        """
        Get all orders for the day.
        
        Returns:
            List[OrderResponse]: List of all orders
        """
        return self._client.get_orders()
    
    def get_pending_orders(self) -> List[OrderResponse]:
        """
        Get all pending (open) orders.
        
        Returns:
            List[OrderResponse]: List of pending orders
        """
        orders = self._client.get_orders()
        return [
            order for order in orders
            if order.status in ["PENDING", "OPEN", "TRIGGER PENDING"]
        ]
    
    def get_completed_orders(self) -> List[OrderResponse]:
        """
        Get all completed orders for the day.
        
        Returns:
            List[OrderResponse]: List of completed orders
        """
        orders = self._client.get_orders()
        return [
            order for order in orders
            if order.status == "COMPLETE"
        ]
    
    def get_rejected_orders(self) -> List[OrderResponse]:
        """
        Get all rejected orders for the day.
        
        Returns:
            List[OrderResponse]: List of rejected orders
        """
        orders = self._client.get_orders()
        return [
            order for order in orders
            if order.status == "REJECTED"
        ]
    
    def get_orders_by_symbol(self, symbol: str) -> List[OrderResponse]:
        """
        Get all orders for a specific symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            List[OrderResponse]: List of orders for the symbol
        """
        orders = self._client.get_orders()
        return [
            order for order in orders
            if order.symbol == symbol.upper()
        ]
    
    # ==========================================================================
    # Validation Methods
    # ==========================================================================
    
    def _validate_order_params(
        self,
        symbol: str,
        quantity: int,
        price: Optional[float] = None,
        trigger_price: Optional[float] = None
    ) -> None:
        """
        Validate order parameters.
        
        Args:
            symbol: Trading symbol
            quantity: Order quantity
            price: Limit price
            trigger_price: Trigger price
        
        Raises:
            OrderError: If validation fails
        """
        if not symbol or not symbol.strip():
            raise OrderError(
                message="Symbol is required",
                code="INVALID_SYMBOL"
            )
        
        if quantity <= 0:
            raise OrderError(
                message="Quantity must be positive",
                code="INVALID_QUANTITY"
            )
        
        if price is not None and price <= 0:
            raise OrderError(
                message="Price must be positive",
                code="INVALID_PRICE"
            )
        
        if trigger_price is not None and trigger_price <= 0:
            raise OrderError(
                message="Trigger price must be positive",
                code="INVALID_TRIGGER_PRICE"
            )
    
    # ==========================================================================
    # Logging Methods
    # ==========================================================================
    
    def _log_order_activity(
        self,
        action: str,
        request: Optional[OrderRequest],
        response: Optional[OrderResponse],
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log order activity for audit trail.
        
        Args:
            action: Action type (PLACE, MODIFY, CANCEL)
            request: Order request
            response: Order response
            extra: Additional data to log
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "request": None,
            "response": None,
            "extra": extra
        }
        
        if request:
            log_entry["request"] = {
                "symbol": request.symbol,
                "exchange": request.exchange.value,
                "transaction_type": request.transaction_type.value,
                "quantity": request.quantity,
                "order_type": request.order_type.value,
                "price": request.price,
                "trigger_price": request.trigger_price,
                "product": request.product.value
            }
        
        if response:
            log_entry["response"] = {
                "order_id": response.order_id,
                "status": response.status,
                "symbol": response.symbol,
                "average_price": response.average_price,
                "filled_quantity": response.filled_quantity,
                "message": response.message
            }
        
        self._order_history.append(log_entry)
        
        logger.info(
            f"Order activity: {action} - "
            f"{response.order_id if response else 'N/A'} - "
            f"{response.status if response else 'N/A'}"
        )
    
    def get_order_history(self) -> List[Dict[str, Any]]:
        """
        Get order activity history (local log).
        
        Returns:
            List[Dict]: List of order activity entries
        """
        return self._order_history.copy()
    
    def clear_order_history(self) -> None:
        """Clear the local order history log."""
        self._order_history.clear()
        logger.info("Order history cleared")
