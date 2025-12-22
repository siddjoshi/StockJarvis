# tests/integration/test_zerodha.py
"""
Integration tests for Zerodha broker integration.
These tests require a mock Kite API or test environment.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from BrokerModules.base_broker import (
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
    AuthenticationError,
    OrderError,
)
from BrokerModules.Zerodha.kite_client import KiteClient
from BrokerModules.Zerodha.order_manager import OrderManager
from BrokerModules.Zerodha.position_manager import PositionManager
from BrokerModules.Zerodha.market_data import MarketDataManager


# =============================================================================
# Mock Data
# =============================================================================

MOCK_PROFILE = {
    "user_id": "AB1234",
    "user_name": "Test User",
    "email": "test@example.com",
    "broker": "ZERODHA",
    "exchanges": ["NSE", "BSE", "NFO"],
    "products": ["CNC", "MIS", "NRML"]
}

MOCK_ORDER = {
    "order_id": "220101000123456",
    "status": "COMPLETE",
    "tradingsymbol": "RELIANCE",
    "transaction_type": "BUY",
    "quantity": 10,
    "order_type": "MARKET",
    "price": None,
    "average_price": 2450.50,
    "filled_quantity": 10,
    "pending_quantity": 0,
    "order_timestamp": datetime.now(),
    "exchange_order_id": "NSE123456",
    "status_message": "Order executed"
}

MOCK_POSITION = {
    "tradingsymbol": "RELIANCE",
    "exchange": "NSE",
    "quantity": 10,
    "average_price": 2450.00,
    "last_price": 2475.50,
    "pnl": 255.00,
    "day_m2m": 100.00,
    "product": "CNC",
    "overnight_quantity": 10,
    "multiplier": 1.0
}

MOCK_HOLDING = {
    "tradingsymbol": "RELIANCE",
    "exchange": "NSE",
    "isin": "INE002A01018",
    "quantity": 50,
    "average_price": 2300.00,
    "last_price": 2450.00,
    "pnl": 7500.00,
    "day_change": 25.50,
    "day_change_percentage": 1.05
}

MOCK_QUOTE = {
    "last_price": 2450.50,
    "ohlc": {
        "open": 2440.00,
        "high": 2465.00,
        "low": 2435.00,
        "close": 2445.00
    },
    "volume": 1234567,
    "depth": {
        "buy": [{"price": 2450.00, "quantity": 500}],
        "sell": [{"price": 2451.00, "quantity": 300}]
    },
    "timestamp": datetime.now()
}

MOCK_MARGINS = {
    "equity": {
        "available": {"cash": 100000.00, "live_balance": 75000.00},
        "utilised": {"debits": 25000.00},
        "net": 125000.00
    }
}


# =============================================================================
# KiteClient Tests
# =============================================================================

@pytest.mark.integration
class TestKiteClient:
    """Test KiteClient functionality."""
    
    @pytest.fixture
    def mock_kite(self):
        """Create a mock KiteConnect instance."""
        with patch('BrokerModules.Zerodha.kite_client.KiteConnect') as mock:
            mock_instance = MagicMock()
            mock.return_value = mock_instance
            yield mock_instance
    
    @pytest.fixture
    def client(self, mock_kite):
        """Create KiteClient with mocked KiteConnect."""
        return KiteClient(
            api_key="test_key",
            api_secret="test_secret"
        )
    
    def test_client_initialization(self, mock_kite):
        """Test client initialization."""
        client = KiteClient(
            api_key="test_key",
            api_secret="test_secret"
        )
        
        assert client.name == "Zerodha"
        assert not client.is_authenticated
    
    def test_client_with_access_token(self, mock_kite):
        """Test client initialization with access token."""
        client = KiteClient(
            api_key="test_key",
            api_secret="test_secret",
            access_token="test_token"
        )
        
        assert client.is_authenticated
        mock_kite.set_access_token.assert_called_with("test_token")
    
    def test_get_login_url(self, client, mock_kite):
        """Test getting login URL."""
        mock_kite.login_url.return_value = "https://kite.zerodha.com/connect/login?api_key=test"
        
        url = client.get_login_url()
        
        assert "kite.zerodha.com" in url
        mock_kite.login_url.assert_called_once()
    
    def test_authenticate_success(self, client, mock_kite):
        """Test successful authentication."""
        mock_kite.generate_session.return_value = {
            "access_token": "generated_token",
            "user_id": "AB1234"
        }
        
        result = client.authenticate("request_token")
        
        assert result is True
        assert client.is_authenticated
        mock_kite.generate_session.assert_called_once()
        mock_kite.set_access_token.assert_called_with("generated_token")
    
    def test_authenticate_failure(self, client, mock_kite):
        """Test authentication failure."""
        from kiteconnect.exceptions import TokenException
        mock_kite.generate_session.side_effect = TokenException("Invalid token")
        
        with pytest.raises(AuthenticationError):
            client.authenticate("invalid_token")
        
        assert not client.is_authenticated
    
    def test_logout(self, client, mock_kite):
        """Test logout."""
        client.set_access_token("test_token")
        assert client.is_authenticated
        
        result = client.logout()
        
        assert result is True
        assert not client.is_authenticated
    
    def test_place_order(self, client, mock_kite):
        """Test placing an order."""
        client.set_access_token("test_token")
        mock_kite.place_order.return_value = "220101000123456"
        mock_kite.orders.return_value = [MOCK_ORDER]
        
        order_request = OrderRequest(
            symbol="RELIANCE",
            exchange=ExchangeType.NSE,
            transaction_type=TransactionType.BUY,
            quantity=10,
            order_type=OrderType.MARKET,
            product=ProductType.CNC
        )
        
        response = client.place_order(order_request)
        
        assert response.order_id == "220101000123456"
        assert response.status == "COMPLETE"
        mock_kite.place_order.assert_called_once()
    
    def test_place_order_not_authenticated(self, client):
        """Test placing order without authentication."""
        order_request = OrderRequest(
            symbol="RELIANCE",
            exchange=ExchangeType.NSE,
            transaction_type=TransactionType.BUY,
            quantity=10,
            order_type=OrderType.MARKET
        )
        
        with pytest.raises(AuthenticationError):
            client.place_order(order_request)
    
    def test_get_orders(self, client, mock_kite):
        """Test getting orders."""
        client.set_access_token("test_token")
        mock_kite.orders.return_value = [MOCK_ORDER]
        
        orders = client.get_orders()
        
        assert len(orders) == 1
        assert orders[0].order_id == "220101000123456"
    
    def test_cancel_order(self, client, mock_kite):
        """Test cancelling an order."""
        client.set_access_token("test_token")
        mock_kite.cancel_order.return_value = None
        
        result = client.cancel_order("220101000123456")
        
        assert result is True
        mock_kite.cancel_order.assert_called_once()
    
    def test_get_positions(self, client, mock_kite):
        """Test getting positions."""
        client.set_access_token("test_token")
        mock_kite.positions.return_value = {
            "net": [MOCK_POSITION],
            "day": []
        }
        
        positions = client.get_positions()
        
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
        assert positions[0].quantity == 10
    
    def test_get_holdings(self, client, mock_kite):
        """Test getting holdings."""
        client.set_access_token("test_token")
        mock_kite.holdings.return_value = [MOCK_HOLDING]
        
        holdings = client.get_holdings()
        
        assert len(holdings) == 1
        assert holdings[0].symbol == "RELIANCE"
        assert holdings[0].quantity == 50
    
    def test_get_quote(self, client, mock_kite):
        """Test getting quote."""
        client.set_access_token("test_token")
        mock_kite.quote.return_value = {"NSE:RELIANCE": MOCK_QUOTE}
        
        quote = client.get_quote("RELIANCE", ExchangeType.NSE)
        
        assert quote.symbol == "RELIANCE"
        assert quote.last_price == 2450.50
    
    def test_get_ltp(self, client, mock_kite):
        """Test getting LTP."""
        client.set_access_token("test_token")
        mock_kite.ltp.return_value = {
            "NSE:RELIANCE": {"last_price": 2450.50},
            "NSE:TCS": {"last_price": 3500.00}
        }
        
        ltp = client.get_ltp([
            ("RELIANCE", ExchangeType.NSE),
            ("TCS", ExchangeType.NSE)
        ])
        
        assert ltp["RELIANCE"] == 2450.50
        assert ltp["TCS"] == 3500.00
    
    def test_get_margins(self, client, mock_kite):
        """Test getting margins."""
        client.set_access_token("test_token")
        mock_kite.margins.return_value = MOCK_MARGINS
        
        margins = client.get_margins()
        
        assert margins.available_cash == 100000.00
        assert margins.used_margin == 25000.00
    
    def test_get_profile(self, client, mock_kite):
        """Test getting profile."""
        client.set_access_token("test_token")
        mock_kite.profile.return_value = MOCK_PROFILE
        
        profile = client.get_profile()
        
        assert profile["user_id"] == "AB1234"
        assert profile["user_name"] == "Test User"


# =============================================================================
# OrderManager Tests
# =============================================================================

@pytest.mark.integration
class TestOrderManager:
    """Test OrderManager functionality."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock KiteClient."""
        client = MagicMock(spec=KiteClient)
        client.is_authenticated = True
        return client
    
    @pytest.fixture
    def order_manager(self, mock_client):
        """Create OrderManager with mock client."""
        return OrderManager(mock_client)
    
    def test_place_market_order(self, order_manager, mock_client):
        """Test placing a market order."""
        mock_client.place_order.return_value = OrderResponse(
            order_id="123456",
            status="COMPLETE",
            symbol="RELIANCE",
            transaction_type="BUY",
            quantity=10,
            order_type="MARKET",
            price=None,
            average_price=2450.50,
            filled_quantity=10,
            pending_quantity=0,
            placed_at=datetime.now(),
            message="Order executed"
        )
        
        response = order_manager.place_market_order(
            symbol="RELIANCE",
            exchange=ExchangeType.NSE,
            transaction_type=TransactionType.BUY,
            quantity=10
        )
        
        assert response.order_id == "123456"
        assert response.status == "COMPLETE"
        mock_client.place_order.assert_called_once()
    
    def test_place_limit_order(self, order_manager, mock_client):
        """Test placing a limit order."""
        mock_client.place_order.return_value = OrderResponse(
            order_id="123457",
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
            message="Order placed"
        )
        
        response = order_manager.place_limit_order(
            symbol="TCS",
            exchange=ExchangeType.NSE,
            transaction_type=TransactionType.BUY,
            quantity=5,
            price=3500.00
        )
        
        assert response.status == "PENDING"
        assert response.price == 3500.00
    
    def test_place_stop_loss_order(self, order_manager, mock_client):
        """Test placing a stop loss order."""
        mock_client.place_order.return_value = OrderResponse(
            order_id="123458",
            status="TRIGGER PENDING",
            symbol="INFY",
            transaction_type="SELL",
            quantity=10,
            order_type="SL-M",
            price=None,
            average_price=0.0,
            filled_quantity=0,
            pending_quantity=10,
            placed_at=datetime.now(),
            message="Stop loss order placed"
        )
        
        response = order_manager.place_stop_loss_order(
            symbol="INFY",
            exchange=ExchangeType.NSE,
            transaction_type=TransactionType.SELL,
            quantity=10,
            trigger_price=1450.00
        )
        
        assert response.status == "TRIGGER PENDING"
    
    def test_cancel_order(self, order_manager, mock_client):
        """Test cancelling an order."""
        mock_client.cancel_order.return_value = True
        
        result = order_manager.cancel_order("123456")
        
        assert result is True
        mock_client.cancel_order.assert_called_with("123456")
    
    def test_invalid_quantity_validation(self, order_manager):
        """Test validation for invalid quantity."""
        with pytest.raises(OrderError) as exc_info:
            order_manager.place_market_order(
                symbol="RELIANCE",
                exchange=ExchangeType.NSE,
                transaction_type=TransactionType.BUY,
                quantity=-10
            )
        
        assert "positive" in str(exc_info.value).lower()
    
    def test_invalid_symbol_validation(self, order_manager):
        """Test validation for invalid symbol."""
        with pytest.raises(OrderError) as exc_info:
            order_manager.place_market_order(
                symbol="",
                exchange=ExchangeType.NSE,
                transaction_type=TransactionType.BUY,
                quantity=10
            )
        
        assert "symbol" in str(exc_info.value).lower()


# =============================================================================
# PositionManager Tests
# =============================================================================

@pytest.mark.integration
class TestPositionManager:
    """Test PositionManager functionality."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock KiteClient."""
        client = MagicMock(spec=KiteClient)
        client.is_authenticated = True
        client.EXCHANGE_MAP = {
            ExchangeType.NSE: "NSE",
            ExchangeType.BSE: "BSE"
        }
        return client
    
    @pytest.fixture
    def position_manager(self, mock_client):
        """Create PositionManager with mock client."""
        return PositionManager(mock_client)
    
    def test_get_positions(self, position_manager, mock_client):
        """Test getting positions."""
        mock_client.get_positions.return_value = [
            PositionData(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                average_price=2450.00,
                last_price=2475.50,
                pnl=255.00,
                day_pnl=100.00,
                product="CNC"
            )
        ]
        
        positions = position_manager.get_positions()
        
        assert len(positions) == 1
        assert positions[0].symbol == "RELIANCE"
    
    def test_get_position_by_symbol(self, position_manager, mock_client):
        """Test getting position by symbol."""
        mock_client.get_positions.return_value = [
            PositionData(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                average_price=2450.00,
                last_price=2475.50,
                pnl=255.00,
                day_pnl=100.00,
                product="CNC"
            ),
            PositionData(
                symbol="TCS",
                exchange="NSE",
                quantity=5,
                average_price=3500.00,
                last_price=3550.00,
                pnl=250.00,
                day_pnl=50.00,
                product="MIS"
            )
        ]
        
        position = position_manager.get_position_by_symbol("TCS")
        
        assert position is not None
        assert position.symbol == "TCS"
    
    def test_get_position_summary(self, position_manager, mock_client):
        """Test getting position summary."""
        mock_client.get_positions.return_value = [
            PositionData(
                symbol="RELIANCE",
                exchange="NSE",
                quantity=10,
                average_price=2450.00,
                last_price=2475.50,
                pnl=255.00,
                day_pnl=100.00,
                product="CNC"
            ),
            PositionData(
                symbol="TCS",
                exchange="NSE",
                quantity=-5,
                average_price=3500.00,
                last_price=3450.00,
                pnl=250.00,
                day_pnl=50.00,
                product="MIS"
            )
        ]
        
        summary = position_manager.get_position_summary()
        
        assert summary.total_positions == 2
        assert summary.long_positions == 1
        assert summary.short_positions == 1
        assert summary.total_pnl == 505.00
    
    def test_get_holdings(self, position_manager, mock_client):
        """Test getting holdings."""
        mock_client.get_holdings.return_value = [
            HoldingData(
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
        ]
        
        holdings = position_manager.get_holdings()
        
        assert len(holdings) == 1
        assert holdings[0].symbol == "RELIANCE"


# =============================================================================
# MarketDataManager Tests
# =============================================================================

@pytest.mark.integration
class TestMarketDataManager:
    """Test MarketDataManager functionality."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock KiteClient."""
        client = MagicMock(spec=KiteClient)
        client.is_authenticated = True
        return client
    
    @pytest.fixture
    def market_data(self, mock_client):
        """Create MarketDataManager with mock client."""
        return MarketDataManager(mock_client, cache_ttl=1)
    
    def test_get_quote(self, market_data, mock_client):
        """Test getting quote."""
        mock_client.get_quote.return_value = QuoteData(
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
        
        quote = market_data.get_quote("RELIANCE", ExchangeType.NSE)
        
        assert quote.symbol == "RELIANCE"
        assert quote.last_price == 2450.50
    
    def test_get_quote_with_cache(self, market_data, mock_client):
        """Test quote caching."""
        mock_client.get_quote.return_value = QuoteData(
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
        
        # First call - fetches from API
        quote1 = market_data.get_quote("RELIANCE", ExchangeType.NSE)
        # Second call - should use cache
        quote2 = market_data.get_quote("RELIANCE", ExchangeType.NSE)
        
        # Should only call API once due to caching
        assert mock_client.get_quote.call_count == 1
        assert quote1.last_price == quote2.last_price
    
    def test_get_ltp(self, market_data, mock_client):
        """Test getting LTP."""
        mock_client.get_ltp.return_value = {"RELIANCE": 2450.50}
        
        ltp = market_data.get_ltp("RELIANCE", ExchangeType.NSE)
        
        assert ltp == 2450.50
    
    def test_get_historical_data(self, market_data, mock_client):
        """Test getting historical data."""
        mock_client.get_historical_data.return_value = [
            {
                "date": datetime(2024, 1, 1),
                "open": 2400.00,
                "high": 2450.00,
                "low": 2380.00,
                "close": 2440.00,
                "volume": 1000000
            },
            {
                "date": datetime(2024, 1, 2),
                "open": 2440.00,
                "high": 2470.00,
                "low": 2420.00,
                "close": 2460.00,
                "volume": 1200000
            }
        ]
        
        data = market_data.get_historical_data(
            symbol="RELIANCE",
            exchange=ExchangeType.NSE,
            days_back=2
        )
        
        assert len(data) == 2
        mock_client.get_historical_data.assert_called_once()
    
    def test_is_market_open(self, market_data):
        """Test market open check."""
        # This is a simple time-based check
        result = market_data.is_market_open()
        
        assert isinstance(result, bool)
    
    def test_get_market_status(self, market_data):
        """Test getting market status."""
        status = market_data.get_market_status()
        
        assert "status" in status
        assert "is_open" in status
        assert "current_time" in status
        assert "market_open_time" in status
        assert "market_close_time" in status
    
    def test_clear_cache(self, market_data, mock_client):
        """Test clearing cache."""
        # Add something to cache
        mock_client.get_quote.return_value = QuoteData(
            symbol="TEST",
            exchange="NSE",
            last_price=100.0,
            open_price=100.0,
            high_price=100.0,
            low_price=100.0,
            close_price=100.0,
            volume=1000,
            bid_price=99.0,
            ask_price=101.0,
            bid_quantity=100,
            ask_quantity=100,
            timestamp=datetime.now()
        )
        market_data.get_quote("TEST", ExchangeType.NSE)
        
        # Clear cache
        market_data.clear_quote_cache()
        
        # Next call should fetch from API again
        market_data.get_quote("TEST", ExchangeType.NSE)
        
        assert mock_client.get_quote.call_count == 2
