# tests/integration/test_api.py
"""
Integration tests for FastAPI endpoints.
Tests authentication, strategies, positions, signals, and orders endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import patch, Mock

from api.main import app
from data.models import (
    Symbol,
    Strategy,
    Signal,
    Position,
    Order,
    OrderAction,
    OrderStatus,
    Exchange,
    TradingMode
)
from data.repository import repository
from core.strategy_engine import registry as strategy_registry
from strategies.eod_strategies import SMAGoldenCrossStrategy


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def test_client():
    """
    Create TestClient for FastAPI application.
    
    Returns:
        TestClient: FastAPI test client
    
    Example:
        def test_endpoint(test_client):
            response = test_client.get("/api/strategies")
            assert response.status_code == 200
    """
    # Override database for testing
    with TestClient(app) as client:
        yield client


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """
    Get authentication headers for API requests.
    
    Returns:
        Dict: Headers with authorization token
    
    Note:
        In production, you'd generate a real JWT token.
        For now, using a mock token.
    """
    return {
        "Authorization": "Bearer test_token_12345",
        "Content-Type": "application/json"
    }


@pytest.fixture
def setup_test_data(test_db_session):
    """
    Setup test data in database before tests.
    
    Args:
        test_db_session: Database session fixture
    
    Yields:
        Dict: Dictionary of created test objects
    """
    # Create symbol
    symbol = Symbol(
        symbol="RELIANCE",
        company_name="Reliance Industries Ltd.",
        exchange=Exchange.NSE,
        is_active=True,
        is_nifty50=True
    )
    test_db_session.add(symbol)
    
    # Create strategy
    strategy = Strategy(
        name="RSI_MACD_Combo",
        description="RSI and MACD combination",
        parameters='{"rsi_period": 14}',
        backtest_accuracy=0.68,
        is_active=True,
        is_validated=True
    )
    test_db_session.add(strategy)
    
    test_db_session.commit()
    test_db_session.refresh(symbol)
    test_db_session.refresh(strategy)
    
    # Create signal
    signal = Signal(
        strategy_id=strategy.id,
        symbol_id=symbol.id,
        action=OrderAction.BUY,
        price=2450.50,
        stop_loss=2400.00,
        target=2550.00,
        confidence=0.75,
        reason="RSI oversold + MACD crossover"
    )
    test_db_session.add(signal)
    
    # Create position
    position = Position(
        symbol_id=symbol.id,
        quantity=10,
        entry_price=2450.50,
        current_price=2475.00,
        stop_loss=2400.00,
        target=2550.00,
        unrealized_pnl=245.0,
        is_open=True,
        trading_mode=TradingMode.PAPER
    )
    test_db_session.add(position)
    
    test_db_session.commit()
    test_db_session.refresh(signal)
    test_db_session.refresh(position)
    
    yield {
        "symbol": symbol,
        "strategy": strategy,
        "signal": signal,
        "position": position
    }


# ============================================================================
# Test Root Endpoints
# ============================================================================

class TestRootEndpoints:
    """Test root and health check endpoints."""
    
    def test_root_endpoint(self, test_client):
        """Test root endpoint returns API information."""
        response = test_client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "StockJarvis API"
        assert data["version"] == "2.0.0"
        assert data["status"] == "running"
    
    def test_health_check(self, test_client):
        """Test health check endpoint."""
        response = test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data
        assert data["components"]["api"] == "healthy"
    
    def test_metrics_endpoint(self, test_client):
        """Test metrics endpoint returns trading statistics."""
        response = test_client.get("/metrics")
        
        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "trading" in data
        assert "mode" in data["trading"]


# ============================================================================
# Test Authentication
# ============================================================================

class TestAuthentication:
    """Test authentication endpoints and middleware."""
    
    @pytest.mark.skip(reason="Auth not fully implemented yet")
    def test_login_success(self, test_client):
        """Test successful login."""
        credentials = {
            "username": "test_user",
            "password": "test_password"
        }
        
        response = test_client.post("/api/auth/login", json=credentials)
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"
    
    @pytest.mark.skip(reason="Auth not fully implemented yet")
    def test_login_invalid_credentials(self, test_client):
        """Test login with invalid credentials."""
        credentials = {
            "username": "invalid_user",
            "password": "wrong_password"
        }
        
        response = test_client.post("/api/auth/login", json=credentials)
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    @pytest.mark.skip(reason="Auth not fully implemented yet")
    def test_protected_endpoint_without_auth(self, test_client):
        """Test accessing protected endpoint without authentication."""
        response = test_client.get("/api/strategies")
        
        assert response.status_code == 401


# ============================================================================
# Test Strategies Endpoints
# ============================================================================

class TestStrategiesEndpoints:
    """Test strategy-related API endpoints."""
    
    def test_list_strategies(self, test_client, setup_test_data):
        """Test listing all strategies."""
        response = test_client.get("/api/strategies")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            strategy = data[0]
            assert "id" in strategy
            assert "name" in strategy
            assert "description" in strategy
    
    def test_get_strategy_by_id(self, test_client, setup_test_data):
        """Test getting a specific strategy by ID."""
        strategy_id = setup_test_data["strategy"].id
        
        response = test_client.get(f"/api/strategies/{strategy_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == strategy_id
        assert data["name"] == "RSI_MACD_Combo"
    
    def test_get_strategy_not_found(self, test_client):
        """Test getting non-existent strategy."""
        response = test_client.get("/api/strategies/99999")
        
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
    
    def test_create_strategy(self, test_client):
        """Test creating a new strategy."""
        new_strategy = {
            "name": "New_Test_Strategy",
            "description": "Test strategy for API",
            "parameters": {"test": "value"},
            "is_active": True
        }
        
        response = test_client.post("/api/strategies", json=new_strategy)
        
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["name"] == "New_Test_Strategy"
        assert "id" in data
    
    def test_update_strategy(self, test_client, setup_test_data):
        """Test updating an existing strategy."""
        strategy_id = setup_test_data["strategy"].id
        
        updates = {
            "description": "Updated description",
            "is_active": False
        }
        
        response = test_client.put(f"/api/strategies/{strategy_id}", json=updates)
        
        # Might be 200 or 204
        assert response.status_code in [200, 204]
        
        # Verify update
        response = test_client.get(f"/api/strategies/{strategy_id}")
        data = response.json()
        assert data["description"] == "Updated description"
    
    def test_delete_strategy(self, test_client, test_db_session):
        """Test deleting a strategy."""
        # Create a strategy to delete
        strategy = Strategy(
            name="To_Delete",
            description="Will be deleted",
            is_active=True
        )
        test_db_session.add(strategy)
        test_db_session.commit()
        test_db_session.refresh(strategy)
        
        strategy_id = strategy.id
        
        response = test_client.delete(f"/api/strategies/{strategy_id}")
        
        assert response.status_code in [200, 204]
        
        # Verify deletion
        response = test_client.get(f"/api/strategies/{strategy_id}")
        assert response.status_code == 404


# ============================================================================
# Test Signals Endpoints
# ============================================================================

class TestSignalsEndpoints:
    """Test signal-related API endpoints."""
    
    def test_list_signals(self, test_client, setup_test_data):
        """Test listing all signals."""
        response = test_client.get("/api/signals")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            signal = data[0]
            assert "id" in signal
            assert "action" in signal
            assert "symbol_id" in signal
    
    def test_get_signal_by_id(self, test_client, setup_test_data):
        """Test getting a specific signal by ID."""
        signal_id = setup_test_data["signal"].id
        
        response = test_client.get(f"/api/signals/{signal_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == signal_id
        assert data["action"] == "BUY"
        assert data["confidence"] == 0.75
    
    def test_filter_signals_by_symbol(self, test_client, setup_test_data):
        """Test filtering signals by symbol."""
        symbol_id = setup_test_data["symbol"].id
        
        response = test_client.get(f"/api/signals?symbol_id={symbol_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All signals should be for the requested symbol
        for signal in data:
            assert signal["symbol_id"] == symbol_id
    
    def test_filter_signals_by_date(self, test_client):
        """Test filtering signals by date range."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        response = test_client.get(f"/api/signals?start_date={today}")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_create_signal(self, test_client, setup_test_data):
        """Test creating a new signal."""
        new_signal = {
            "strategy_id": setup_test_data["strategy"].id,
            "symbol_id": setup_test_data["symbol"].id,
            "action": "BUY",
            "price": 2500.00,
            "stop_loss": 2450.00,
            "target": 2600.00,
            "confidence": 0.80,
            "reason": "Test signal creation"
        }
        
        response = test_client.post("/api/signals", json=new_signal)
        
        assert response.status_code in [200, 201]
        data = response.json()
        assert data["action"] == "BUY"
        assert data["price"] == 2500.00


# ============================================================================
# Test Positions Endpoints
# ============================================================================

class TestPositionsEndpoints:
    """Test position-related API endpoints."""
    
    def test_list_positions(self, test_client, setup_test_data):
        """Test listing all positions."""
        response = test_client.get("/api/positions")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        if len(data) > 0:
            position = data[0]
            assert "id" in position
            assert "symbol_id" in position
            assert "quantity" in position
    
    def test_get_position_by_id(self, test_client, setup_test_data):
        """Test getting a specific position by ID."""
        position_id = setup_test_data["position"].id
        
        response = test_client.get(f"/api/positions/{position_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == position_id
        assert data["quantity"] == 10
        assert data["entry_price"] == 2450.50
    
    def test_get_open_positions(self, test_client):
        """Test filtering open positions only."""
        response = test_client.get("/api/positions?is_open=true")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # All returned positions should be open
        for position in data:
            assert position["is_open"] is True
    
    def test_update_position(self, test_client, setup_test_data):
        """Test updating a position."""
        position_id = setup_test_data["position"].id
        
        updates = {
            "current_price": 2500.00,
            "unrealized_pnl": 495.00  # (2500 - 2450.50) * 10
        }
        
        response = test_client.put(f"/api/positions/{position_id}", json=updates)
        
        assert response.status_code in [200, 204]
        
        # Verify update
        response = test_client.get(f"/api/positions/{position_id}")
        data = response.json()
        assert data["current_price"] == 2500.00
    
    def test_close_position(self, test_client, setup_test_data):
        """Test closing a position."""
        position_id = setup_test_data["position"].id
        
        close_data = {
            "exit_price": 2480.00,
            "exit_reason": "Target reached"
        }
        
        response = test_client.post(
            f"/api/positions/{position_id}/close",
            json=close_data
        )
        
        assert response.status_code in [200, 201]
        
        # Verify position is closed
        response = test_client.get(f"/api/positions/{position_id}")
        data = response.json()
        assert data["is_open"] is False


# ============================================================================
# Test Orders Endpoints
# ============================================================================

class TestOrdersEndpoints:
    """Test order-related API endpoints."""
    
    @patch('api.routes.orders.broker_client')
    def test_place_order(self, mock_broker, test_client, setup_test_data):
        """Test placing a new order."""
        mock_broker.place_order.return_value = {
            "order_id": "MOCK12345",
            "status": "COMPLETE"
        }
        
        new_order = {
            "symbol_id": setup_test_data["symbol"].id,
            "action": "BUY",
            "quantity": 5,
            "order_type": "MARKET",
            "price": None
        }
        
        response = test_client.post("/api/orders", json=new_order)
        
        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        assert data["action"] == "BUY"
        assert data["quantity"] == 5
    
    def test_list_orders(self, test_client):
        """Test listing all orders."""
        response = test_client.get("/api/orders")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @patch('api.routes.orders.broker_client')
    def test_cancel_order(self, mock_broker, test_client, test_db_session, setup_test_data):
        """Test canceling an order."""
        mock_broker.cancel_order.return_value = {"status": "CANCELLED"}
        
        # Create a test order
        order = Order(
            symbol_id=setup_test_data["symbol"].id,
            action=OrderAction.BUY,
            quantity=5,
            order_type="LIMIT",
            price=2400.00,
            status=OrderStatus.PENDING,
            broker_order_id="MOCK12345"
        )
        test_db_session.add(order)
        test_db_session.commit()
        test_db_session.refresh(order)
        
        response = test_client.post(f"/api/orders/{order.id}/cancel")
        
        assert response.status_code in [200, 201]


# ============================================================================
# Test Symbols Endpoints
# ============================================================================

class TestSymbolsEndpoints:
    """Test symbol-related API endpoints."""
    
    def test_list_symbols(self, test_client, setup_test_data):
        """Test listing all symbols."""
        response = test_client.get("/api/symbols")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
    
    def test_get_symbol_by_id(self, test_client, setup_test_data):
        """Test getting a specific symbol by ID."""
        symbol_id = setup_test_data["symbol"].id
        
        response = test_client.get(f"/api/symbols/{symbol_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == symbol_id
        assert data["symbol"] == "RELIANCE"
    
    def test_search_symbols(self, test_client):
        """Test searching symbols by name or code."""
        response = test_client.get("/api/symbols/search?q=RELI")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# ============================================================================
# Test Error Handling
# ============================================================================

class TestErrorHandling:
    """Test API error handling."""
    
    def test_404_not_found(self, test_client):
        """Test 404 error for non-existent endpoint."""
        response = test_client.get("/api/nonexistent")
        
        assert response.status_code == 404
    
    def test_validation_error(self, test_client):
        """Test validation error with invalid data."""
        invalid_signal = {
            "strategy_id": "invalid",  # Should be int
            "action": "INVALID_ACTION",  # Invalid enum
            "price": "not_a_number"  # Should be float
        }
        
        response = test_client.post("/api/signals", json=invalid_signal)
        
        assert response.status_code == 422  # Unprocessable Entity
        data = response.json()
        assert "detail" in data


# ============================================================================
# Test Response Headers
# ============================================================================

class TestResponseHeaders:
    """Test API response headers."""
    
    def test_cors_headers(self, test_client):
        """Test CORS headers are present."""
        response = test_client.options("/api/strategies")
        
        # CORS headers should be present
        assert "access-control-allow-origin" in response.headers
    
    def test_process_time_header(self, test_client):
        """Test X-Process-Time header is added."""
        response = test_client.get("/health")
        
        assert "x-process-time" in response.headers
        assert "x-request-id" in response.headers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
