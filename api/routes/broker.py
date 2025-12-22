# api/routes/broker.py
"""
Broker integration endpoints for StockJarvis API.
Handles broker authentication, connection status, and operations.
"""

import threading
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from api.dependencies import require_active_user
from config.settings import settings
from core.logger import get_logger
from BrokerModules.base_broker import (
    OrderRequest,
    OrderType,
    TransactionType,
    ProductType,
    ExchangeType,
    AuthenticationError,
    OrderError,
)

logger = get_logger(__name__)

router = APIRouter()

# Thread-safe broker client singleton
_broker_client = None
_broker_client_lock = threading.Lock()


def get_broker_client():
    """Get or create the broker client instance (thread-safe)."""
    global _broker_client
    if _broker_client is None:
        with _broker_client_lock:
            # Double-check inside lock
            if _broker_client is None:
                from BrokerModules.Zerodha.kite_client import KiteClient
                _broker_client = KiteClient()
    return _broker_client


def get_authenticated_broker():
    """Get authenticated broker client or raise error."""
    client = get_broker_client()
    if not client.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Broker not authenticated. Please login first."
        )
    return client


# =============================================================================
# Pydantic Models
# =============================================================================

class BrokerStatusResponse(BaseModel):
    """Broker connection status response."""
    broker: str
    is_authenticated: bool
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    email: Optional[str] = None
    broker_name: Optional[str] = None
    exchanges: Optional[List[str]] = None
    products: Optional[List[str]] = None


class BrokerLoginResponse(BaseModel):
    """Broker login initiation response."""
    login_url: str
    message: str


class BrokerCallbackResponse(BaseModel):
    """Broker callback response."""
    success: bool
    message: str
    user_id: Optional[str] = None


class PlaceOrderRequest(BaseModel):
    """Order placement request."""
    symbol: str = Field(..., description="Trading symbol")
    exchange: str = Field(..., description="Exchange (NSE, BSE, NFO)")
    transaction_type: str = Field(..., description="BUY or SELL")
    quantity: int = Field(..., gt=0, description="Order quantity")
    order_type: str = Field(..., description="MARKET, LIMIT, SL, SL-M")
    product: str = Field("CNC", description="Product type (CNC, MIS, NRML)")
    price: Optional[float] = Field(None, gt=0, description="Limit price")
    trigger_price: Optional[float] = Field(None, gt=0, description="Trigger price")
    tag: Optional[str] = Field(None, description="Order tag")


class OrderResponse(BaseModel):
    """Order response."""
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
    message: str


class PositionResponse(BaseModel):
    """Position response."""
    symbol: str
    exchange: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    day_pnl: float
    product: str


class QuoteResponse(BaseModel):
    """Quote response."""
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


class MarginResponse(BaseModel):
    """Margin response."""
    available_cash: float
    used_margin: float
    total_margin: float
    available_margin: float


# =============================================================================
# Authentication Endpoints
# =============================================================================

@router.get("/login", response_model=BrokerLoginResponse)
async def initiate_broker_login(
    current_user=Depends(require_active_user)
):
    """
    Initiate Zerodha broker login.
    
    Returns a URL to redirect the user for Zerodha OAuth authentication.
    
    **Example Response:**
    ```json
    {
        "login_url": "https://kite.zerodha.com/connect/login?api_key=...",
        "message": "Redirect user to login_url for authentication"
    }
    ```
    """
    try:
        client = get_broker_client()
        login_url = client.get_login_url()
        
        logger.info(f"Broker login initiated by user: {current_user.username}")
        
        return BrokerLoginResponse(
            login_url=login_url,
            message="Redirect user to login_url for authentication"
        )
        
    except Exception as e:
        logger.error(f"Error initiating broker login: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate broker login: {str(e)}"
        )


@router.get("/callback")
async def broker_callback(
    request_token: str = Query(..., description="OAuth request token"),
    status_code: Optional[str] = Query(None, alias="status"),
    current_user=Depends(require_active_user)
):
    """
    OAuth callback endpoint for Zerodha.
    
    This endpoint receives the request_token after successful Zerodha login.
    Requires authenticated user to prevent session hijacking.
    
    **Query Parameters:**
    - request_token: OAuth request token from Zerodha
    - status: Optional status code
    
    **Example Response:**
    ```json
    {
        "success": true,
        "message": "Authentication successful",
        "user_id": "AB1234"
    }
    ```
    """
    try:
        if status_code and status_code != "success":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Zerodha login failed with status: {status_code}"
            )
        
        client = get_broker_client()
        success = client.authenticate(request_token)
        
        if success:
            # Get user profile
            profile = client.get_profile()
            user_id = profile.get("user_id", "Unknown")
            
            logger.info(f"Broker authenticated successfully. User: {user_id}")
            
            return BrokerCallbackResponse(
                success=True,
                message="Authentication successful",
                user_id=user_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed"
            )
        
    except AuthenticationError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.message}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in broker callback: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Callback processing failed: {str(e)}"
        )


@router.get("/status", response_model=BrokerStatusResponse)
async def get_broker_status(
    current_user=Depends(require_active_user)
):
    """
    Get broker connection status.
    
    Returns the current authentication status and user details if authenticated.
    
    **Example Response (Authenticated):**
    ```json
    {
        "broker": "Zerodha",
        "is_authenticated": true,
        "user_id": "AB1234",
        "user_name": "John Doe",
        "email": "john@example.com",
        "broker_name": "Zerodha",
        "exchanges": ["NSE", "BSE", "NFO"],
        "products": ["CNC", "MIS", "NRML"]
    }
    ```
    
    **Example Response (Not Authenticated):**
    ```json
    {
        "broker": "Zerodha",
        "is_authenticated": false
    }
    ```
    """
    try:
        client = get_broker_client()
        
        response = BrokerStatusResponse(
            broker=client.name,
            is_authenticated=client.is_authenticated
        )
        
        if client.is_authenticated:
            try:
                profile = client.get_profile()
                response.user_id = profile.get("user_id")
                response.user_name = profile.get("user_name")
                response.email = profile.get("email")
                response.broker_name = profile.get("broker")
                response.exchanges = profile.get("exchanges", [])
                response.products = profile.get("products", [])
            except Exception as e:
                logger.warning(f"Failed to get profile: {e}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting broker status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get broker status: {str(e)}"
        )


@router.post("/disconnect")
async def disconnect_broker(
    current_user=Depends(require_active_user)
):
    """
    Disconnect from broker.
    
    Logs out from the broker and invalidates the session.
    
    **Example Response:**
    ```json
    {
        "success": true,
        "message": "Disconnected from broker"
    }
    ```
    """
    try:
        client = get_broker_client()
        
        if not client.is_authenticated:
            return {
                "success": True,
                "message": "Already disconnected"
            }
        
        success = client.logout()
        
        logger.info(f"Broker disconnected by user: {current_user.username}")
        
        return {
            "success": success,
            "message": "Disconnected from broker" if success else "Disconnect failed"
        }
        
    except Exception as e:
        logger.error(f"Error disconnecting broker: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect: {str(e)}"
        )


# =============================================================================
# Order Endpoints
# =============================================================================

@router.post("/orders", response_model=OrderResponse)
async def place_order(
    order: PlaceOrderRequest,
    current_user=Depends(require_active_user)
):
    """
    Place a new order.
    
    **Request Body:**
    ```json
    {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "transaction_type": "BUY",
        "quantity": 10,
        "order_type": "MARKET",
        "product": "CNC"
    }
    ```
    """
    try:
        client = get_authenticated_broker()
        
        # Map string values to enums using explicit mappings
        ORDER_TYPE_MAPPING = {
            "MARKET": OrderType.MARKET,
            "LIMIT": OrderType.LIMIT,
            "SL": OrderType.STOP_LOSS,
            "SL-M": OrderType.STOP_LOSS_MARKET,
            "STOP_LOSS": OrderType.STOP_LOSS,
            "STOP_LOSS_MARKET": OrderType.STOP_LOSS_MARKET,
        }
        
        try:
            exchange = ExchangeType[order.exchange.upper()]
            transaction_type = TransactionType[order.transaction_type.upper()]
            order_type_upper = order.order_type.upper()
            if order_type_upper not in ORDER_TYPE_MAPPING:
                raise KeyError(f"Invalid order type: {order.order_type}")
            order_type = ORDER_TYPE_MAPPING[order_type_upper]
            product = ProductType[order.product.upper()]
        except KeyError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid parameter value: {e}"
            )
        
        # Create order request
        order_request = OrderRequest(
            symbol=order.symbol.upper(),
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=order.quantity,
            order_type=order_type,
            product=product,
            price=order.price,
            trigger_price=order.trigger_price,
            tag=order.tag
        )
        
        # Place order
        response = client.place_order(order_request)
        
        logger.info(
            f"Order placed by {current_user.username}: "
            f"{order.transaction_type} {order.quantity} {order.symbol} - "
            f"Order ID: {response.order_id}"
        )
        
        return OrderResponse(
            order_id=response.order_id,
            status=response.status,
            symbol=response.symbol,
            transaction_type=response.transaction_type,
            quantity=response.quantity,
            order_type=response.order_type,
            price=response.price,
            average_price=response.average_price,
            filled_quantity=response.filled_quantity,
            pending_quantity=response.pending_quantity,
            message=response.message
        )
        
    except OrderError as e:
        logger.error(f"Order error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order failed: {e.message}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Order placement failed: {str(e)}"
        )


@router.get("/orders", response_model=List[OrderResponse])
async def get_orders(
    current_user=Depends(require_active_user)
):
    """
    Get all orders for the day.
    """
    try:
        client = get_authenticated_broker()
        orders = client.get_orders()
        
        return [
            OrderResponse(
                order_id=o.order_id,
                status=o.status,
                symbol=o.symbol,
                transaction_type=o.transaction_type,
                quantity=o.quantity,
                order_type=o.order_type,
                price=o.price,
                average_price=o.average_price,
                filled_quantity=o.filled_quantity,
                pending_quantity=o.pending_quantity,
                message=o.message
            )
            for o in orders
        ]
        
    except Exception as e:
        logger.error(f"Error getting orders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get orders: {str(e)}"
        )


@router.delete("/orders/{order_id}")
async def cancel_order(
    order_id: str,
    current_user=Depends(require_active_user)
):
    """
    Cancel an existing order.
    """
    try:
        client = get_authenticated_broker()
        success = client.cancel_order(order_id)
        
        logger.info(f"Order {order_id} cancelled by {current_user.username}")
        
        return {
            "success": success,
            "message": f"Order {order_id} cancelled" if success else "Cancel failed"
        }
        
    except OrderError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cancel failed: {e.message}"
        )
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel order: {str(e)}"
        )


# =============================================================================
# Position Endpoints
# =============================================================================

@router.get("/positions", response_model=List[PositionResponse])
async def get_positions(
    current_user=Depends(require_active_user)
):
    """
    Get all current positions.
    """
    try:
        client = get_authenticated_broker()
        positions = client.get_positions()
        
        return [
            PositionResponse(
                symbol=p.symbol,
                exchange=p.exchange,
                quantity=p.quantity,
                average_price=p.average_price,
                last_price=p.last_price,
                pnl=p.pnl,
                day_pnl=p.day_pnl,
                product=p.product
            )
            for p in positions
        ]
        
    except Exception as e:
        logger.error(f"Error getting positions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get positions: {str(e)}"
        )


@router.get("/holdings")
async def get_holdings(
    current_user=Depends(require_active_user)
):
    """
    Get all holdings (delivery positions).
    """
    try:
        client = get_authenticated_broker()
        holdings = client.get_holdings()
        
        return [
            {
                "symbol": h.symbol,
                "exchange": h.exchange,
                "isin": h.isin,
                "quantity": h.quantity,
                "average_price": h.average_price,
                "last_price": h.last_price,
                "pnl": h.pnl,
                "day_change": h.day_change,
                "day_change_pct": h.day_change_pct
            }
            for h in holdings
        ]
        
    except Exception as e:
        logger.error(f"Error getting holdings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get holdings: {str(e)}"
        )


# =============================================================================
# Market Data Endpoints
# =============================================================================

@router.get("/quote/{exchange}/{symbol}", response_model=QuoteResponse)
async def get_quote(
    exchange: str,
    symbol: str,
    current_user=Depends(require_active_user)
):
    """
    Get current market quote for a symbol.
    """
    try:
        client = get_authenticated_broker()
        
        try:
            exchange_type = ExchangeType[exchange.upper()]
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid exchange: {exchange}"
            )
        
        quote = client.get_quote(symbol.upper(), exchange_type)
        
        return QuoteResponse(
            symbol=quote.symbol,
            exchange=quote.exchange,
            last_price=quote.last_price,
            open_price=quote.open_price,
            high_price=quote.high_price,
            low_price=quote.low_price,
            close_price=quote.close_price,
            volume=quote.volume,
            bid_price=quote.bid_price,
            ask_price=quote.ask_price
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting quote: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get quote: {str(e)}"
        )


@router.get("/ltp")
async def get_ltp(
    symbols: str = Query(..., description="Comma-separated list of EXCHANGE:SYMBOL"),
    current_user=Depends(require_active_user)
):
    """
    Get Last Traded Price for multiple symbols.
    
    **Query Parameters:**
    - symbols: Comma-separated list in format "NSE:RELIANCE,NSE:TCS"
    """
    try:
        client = get_authenticated_broker()
        
        # Parse symbols
        symbol_list = []
        for item in symbols.split(","):
            parts = item.strip().split(":")
            if len(parts) != 2:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid format: {item}. Use EXCHANGE:SYMBOL"
                )
            try:
                exchange = ExchangeType[parts[0].upper()]
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid exchange: {parts[0]}"
                )
            symbol_list.append((parts[1].upper(), exchange))
        
        ltp_data = client.get_ltp(symbol_list)
        
        return ltp_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting LTP: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get LTP: {str(e)}"
        )


# =============================================================================
# Account Endpoints
# =============================================================================

@router.get("/margins", response_model=MarginResponse)
async def get_margins(
    current_user=Depends(require_active_user)
):
    """
    Get account margins.
    """
    try:
        client = get_authenticated_broker()
        margins = client.get_margins()
        
        return MarginResponse(
            available_cash=margins.available_cash,
            used_margin=margins.used_margin,
            total_margin=margins.total_margin,
            available_margin=margins.available_margin
        )
        
    except Exception as e:
        logger.error(f"Error getting margins: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get margins: {str(e)}"
        )


@router.get("/profile")
async def get_profile(
    current_user=Depends(require_active_user)
):
    """
    Get broker user profile.
    """
    try:
        client = get_authenticated_broker()
        profile = client.get_profile()
        
        return profile
        
    except Exception as e:
        logger.error(f"Error getting profile: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get profile: {str(e)}"
        )
