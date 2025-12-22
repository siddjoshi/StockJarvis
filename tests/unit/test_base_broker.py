# tests/unit/test_base_broker.py
"""
Unit tests for the BaseBroker abstract class and related data structures.
"""

import pytest
from datetime import datetime

from BrokerModules.base_broker import (
    OrderType,
    TransactionType,
    ProductType,
    ExchangeType,
    OrderRequest,
    OrderResponse,
    PositionData,
    HoldingData,
    QuoteData,
    MarginData,
    BrokerError,
    AuthenticationError,
    OrderError,
    RateLimitError,
)


# =============================================================================
# Data Structure Tests
# =============================================================================

@pytest.mark.unit
class TestOrderRequest:
    """Test OrderRequest data structure."""
    
    def test_create_market_order_request(self):
        """Test creating a market order request."""
        order = OrderRequest(
            symbol="RELIANCE",
            exchange=ExchangeType.NSE,
            transaction_type=TransactionType.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
            product=ProductType.CNC
        )
        
        assert order.symbol == "RELIANCE"
        assert order.exchange == ExchangeType.NSE
        assert order.transaction_type == TransactionType.BUY
        assert order.quantity == 10
        assert order.order_type == OrderType.MARKET
        assert order.product == ProductType.CNC
        assert order.price is None
        assert order.trigger_price is None
        assert order.validity == "DAY"
    
    def test_create_limit_order_request(self):
        """Test creating a limit order request."""
        order = OrderRequest(
            symbol="TCS",
            exchange=ExchangeType.NSE,
            transaction_type=TransactionType.SELL,
            quantity=5,
            order_type=OrderType.LIMIT,
            product=ProductType.MIS,
            price=3500.50,
            validity="IOC"
        )
        
        assert order.symbol == "TCS"
        assert order.order_type == OrderType.LIMIT
        assert order.price == 3500.50
        assert order.validity == "IOC"
    
    def test_create_stop_loss_order_request(self):
        """Test creating a stop loss order request."""
        order = OrderRequest(
            symbol="INFY",
            exchange=ExchangeType.NSE,
            transaction_type=TransactionType.SELL,
            quantity=15,
            order_type=OrderType.STOP_LOSS,
            product=ProductType.CNC,
            price=1450.00,
            trigger_price=1460.00
        )
        
        assert order.order_type == OrderType.STOP_LOSS
        assert order.price == 1450.00
        assert order.trigger_price == 1460.00
    
    def test_order_request_with_tag(self):
        """Test order request with custom tag."""
        order = OrderRequest(
            symbol="HDFC",
            exchange=ExchangeType.NSE,
            transaction_type=TransactionType.BUY,
            quantity=1,
            order_type=OrderType.MARKET,
            tag="strategy-rsi-macd"
        )
        
        assert order.tag == "strategy-rsi-macd"


@pytest.mark.unit
class TestOrderResponse:
    """Test OrderResponse data structure."""
    
    def test_create_order_response(self):
        """Test creating an order response."""
        response = OrderResponse(
            order_id="220101000123456",
            status="COMPLETE",
            symbol="RELIANCE",
            transaction_type="BUY",
            quantity=10,
            order_type="MARKET",
            price=None,
            average_price=2450.50,
            filled_quantity=10,
            pending_quantity=0,
            placed_at=datetime(2024, 1, 1, 10, 30, 0),
            exchange_order_id="NSE123456",
            message="Order executed successfully"
        )
        
        assert response.order_id == "220101000123456"
        assert response.status == "COMPLETE"
        assert response.average_price == 2450.50
        assert response.filled_quantity == 10
        assert response.pending_quantity == 0
    
    def test_pending_order_response(self):
        """Test pending order response."""
        response = OrderResponse(
            order_id="220101000123457",
            status="PENDING",
            symbol="TCS",
            transaction_type="BUY",
            quantity=5,
            order_type="LIMIT",
            price=3500.00,
            average_price=0.0,
            filled_quantity=0,
            pending_quantity=5,
            placed_at=datetime.now(),
            message="Order pending execution"
        )
        
        assert response.status == "PENDING"
        assert response.filled_quantity == 0
        assert response.pending_quantity == 5


@pytest.mark.unit
class TestPositionData:
    """Test PositionData data structure."""
    
    def test_create_long_position(self):
        """Test creating a long position."""
        position = PositionData(
            symbol="RELIANCE",
            exchange="NSE",
            quantity=100,
            average_price=2450.00,
            last_price=2475.50,
            pnl=2550.00,
            day_pnl=500.00,
            product="CNC",
            overnight_quantity=100,
            multiplier=1.0
        )
        
        assert position.symbol == "RELIANCE"
        assert position.quantity == 100
        assert position.pnl == 2550.00
        assert position.day_pnl == 500.00
    
    def test_create_short_position(self):
        """Test creating a short position."""
        position = PositionData(
            symbol="TCS",
            exchange="NSE",
            quantity=-50,
            average_price=3500.00,
            last_price=3450.00,
            pnl=2500.00,
            day_pnl=1000.00,
            product="MIS"
        )
        
        assert position.quantity == -50  # Short position
        assert position.pnl == 2500.00  # Profitable short


@pytest.mark.unit
class TestHoldingData:
    """Test HoldingData data structure."""
    
    def test_create_holding(self):
        """Test creating a holding."""
        holding = HoldingData(
            symbol="RELIANCE",
            exchange="NSE",
            isin="INE002A01018",
            quantity=50,
            average_price=2300.00,
            last_price=2450.00,
            pnl=7500.00,
            day_change=25.50,
            day_change_pct=1.05
        )
        
        assert holding.symbol == "RELIANCE"
        assert holding.isin == "INE002A01018"
        assert holding.quantity == 50
        assert holding.pnl == 7500.00
        assert holding.day_change_pct == 1.05


@pytest.mark.unit
class TestQuoteData:
    """Test QuoteData data structure."""
    
    def test_create_quote(self):
        """Test creating a quote."""
        quote = QuoteData(
            symbol="RELIANCE",
            exchange="NSE",
            last_price=2450.50,
            open_price=2440.00,
            high_price=2465.00,
            low_price=2435.00,
            close_price=2445.00,
            volume=1234567,
            bid_price=2450.00,
            ask_price=2451.00,
            bid_quantity=500,
            ask_quantity=300,
            timestamp=datetime.now()
        )
        
        assert quote.symbol == "RELIANCE"
        assert quote.last_price == 2450.50
        assert quote.bid_price == 2450.00
        assert quote.ask_price == 2451.00
        assert quote.volume == 1234567


@pytest.mark.unit
class TestMarginData:
    """Test MarginData data structure."""
    
    def test_create_margin_data(self):
        """Test creating margin data."""
        margin = MarginData(
            available_cash=100000.00,
            used_margin=25000.00,
            total_margin=125000.00,
            available_margin=75000.00
        )
        
        assert margin.available_cash == 100000.00
        assert margin.used_margin == 25000.00
        assert margin.total_margin == 125000.00
        assert margin.available_margin == 75000.00


# =============================================================================
# Enum Tests
# =============================================================================

@pytest.mark.unit
class TestEnums:
    """Test enum values."""
    
    def test_order_types(self):
        """Test OrderType enum values."""
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.STOP_LOSS.value == "SL"
        assert OrderType.STOP_LOSS_MARKET.value == "SL-M"
    
    def test_transaction_types(self):
        """Test TransactionType enum values."""
        assert TransactionType.BUY.value == "BUY"
        assert TransactionType.SELL.value == "SELL"
    
    def test_product_types(self):
        """Test ProductType enum values."""
        assert ProductType.CNC.value == "CNC"
        assert ProductType.MIS.value == "MIS"
        assert ProductType.NRML.value == "NRML"
    
    def test_exchange_types(self):
        """Test ExchangeType enum values."""
        assert ExchangeType.NSE.value == "NSE"
        assert ExchangeType.BSE.value == "BSE"
        assert ExchangeType.NFO.value == "NFO"
        assert ExchangeType.BFO.value == "BFO"


# =============================================================================
# Exception Tests
# =============================================================================

@pytest.mark.unit
class TestExceptions:
    """Test custom exceptions."""
    
    def test_broker_error(self):
        """Test BrokerError exception."""
        error = BrokerError(
            message="Test error message",
            code="TEST_CODE",
            original_error=ValueError("Original error")
        )
        
        assert error.message == "Test error message"
        assert error.code == "TEST_CODE"
        assert isinstance(error.original_error, ValueError)
        assert str(error) == "Test error message"
    
    def test_authentication_error(self):
        """Test AuthenticationError exception."""
        error = AuthenticationError(
            message="Token expired",
            code="TOKEN_EXPIRED"
        )
        
        assert isinstance(error, BrokerError)
        assert error.message == "Token expired"
        assert error.code == "TOKEN_EXPIRED"
    
    def test_order_error(self):
        """Test OrderError exception."""
        error = OrderError(
            message="Insufficient margin",
            code="MARGIN_ERROR"
        )
        
        assert isinstance(error, BrokerError)
        assert error.message == "Insufficient margin"
        assert error.code == "MARGIN_ERROR"
    
    def test_rate_limit_error(self):
        """Test RateLimitError exception."""
        error = RateLimitError(
            message="Rate limit exceeded",
            code="RATE_LIMIT"
        )
        
        assert isinstance(error, BrokerError)
        assert error.message == "Rate limit exceeded"
        assert error.code == "RATE_LIMIT"
    
    def test_exception_without_optional_params(self):
        """Test exception without optional parameters."""
        error = BrokerError(message="Simple error")
        
        assert error.message == "Simple error"
        assert error.code is None
        assert error.original_error is None
