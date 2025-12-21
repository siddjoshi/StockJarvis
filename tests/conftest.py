# tests/conftest.py - Core test fixtures and configuration
"""
Core test fixtures for StockJarvis testing framework.
Provides database sessions, sample data, and mocked services.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock, patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.pool import StaticPool

from data.models import (
    Base,
    Symbol,
    Strategy,
    Signal,
    Position,
    Order,
    Price,
    Exchange,
    Timeframe,
    OrderAction,
    OrderStatus,
    TradingMode,
)
from config.settings import Settings, DatabaseSettings, TradingSettings
from core.logger import get_logger


logger = get_logger(__name__)


# ============================================================================
# Pytest Configuration
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """
    Create event loop for async tests.
    Session-scoped to reuse across all tests.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Test Settings
# ============================================================================

@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """
    Test settings with overrides for testing environment.
    
    Returns:
        Settings: Test configuration
    """
    return Settings(
        db=DatabaseSettings(
            host="localhost",
            port=3306,
            user="test",
            password="test",
            database="test_stockjarvis",
            pool_size=1,
        ),
        trading=TradingSettings(
            mode="paper",
            max_positions=5,
            risk_per_trade=0.02,
            capital=100000.0,
        ),
    )


# ============================================================================
# Database Fixtures - Synchronous
# ============================================================================

@pytest.fixture(scope="function")
def test_db_engine():
    """
    Create in-memory SQLite database engine for testing.
    Function-scoped for isolation between tests.
    
    Returns:
        Engine: SQLAlchemy engine
    """
    # Use in-memory SQLite for fast testing
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    yield engine
    
    # Cleanup
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_db_engine) -> Generator[Session, None, None]:
    """
    Create database session for testing.
    Rolls back all changes after test completes.
    
    Args:
        test_db_engine: Test database engine
    
    Yields:
        Session: SQLAlchemy session
    
    Example:
        def test_something(test_db_session):
            symbol = Symbol(symbol="TEST", company_name="Test Corp")
            test_db_session.add(symbol)
            test_db_session.commit()
            assert symbol.id is not None
    """
    connection = test_db_engine.connect()
    transaction = connection.begin()
    
    # Create session bound to transaction
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()
    
    yield session
    
    # Rollback and cleanup
    session.close()
    transaction.rollback()
    connection.close()


# ============================================================================
# Database Fixtures - Asynchronous
# ============================================================================

@pytest.fixture(scope="function")
async def test_async_db_engine():
    """
    Create async in-memory database engine for async tests.
    
    Returns:
        AsyncEngine: Async SQLAlchemy engine
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def test_async_db_session(test_async_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Create async database session for testing.
    
    Args:
        test_async_db_engine: Test async database engine
    
    Yields:
        AsyncSession: Async SQLAlchemy session
    
    Example:
        async def test_something(test_async_db_session):
            symbol = Symbol(symbol="TEST", company_name="Test Corp")
            test_async_db_session.add(symbol)
            await test_async_db_session.commit()
    """
    async_session_factory = async_sessionmaker(
        test_async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session_factory() as session:
        yield session
        await session.rollback()


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_symbol(test_db_session: Session) -> Symbol:
    """
    Create and return a sample Symbol for testing.
    
    Args:
        test_db_session: Database session
    
    Returns:
        Symbol: Sample symbol object
    
    Example:
        def test_something(sample_symbol):
            assert sample_symbol.symbol == "RELIANCE"
    """
    symbol = Symbol(
        symbol="RELIANCE",
        company_name="Reliance Industries Ltd.",
        exchange=Exchange.NSE,
        is_nifty50=True,
        is_fno=True,
        is_active=True,
        sector="Energy",
        industry="Oil & Gas",
        isin="INE002A01018",
    )
    test_db_session.add(symbol)
    test_db_session.commit()
    test_db_session.refresh(symbol)
    return symbol


@pytest.fixture
def sample_strategy(test_db_session: Session) -> Strategy:
    """
    Create and return a sample Strategy for testing.
    
    Args:
        test_db_session: Database session
    
    Returns:
        Strategy: Sample strategy object
    
    Example:
        def test_something(sample_strategy):
            assert sample_strategy.name == "RSI_MACD_Combo"
    """
    strategy = Strategy(
        name="RSI_MACD_Combo",
        description="Combined RSI and MACD momentum strategy",
        parameters='{"rsi_period": 14, "rsi_oversold": 30, "rsi_overbought": 70}',
        backtest_accuracy=0.68,
        backtest_sharpe=1.8,
        backtest_max_drawdown=0.12,
        is_active=True,
        is_validated=True,
    )
    test_db_session.add(strategy)
    test_db_session.commit()
    test_db_session.refresh(strategy)
    return strategy


@pytest.fixture
def sample_signal(
    test_db_session: Session,
    sample_symbol: Symbol,
    sample_strategy: Strategy
) -> Signal:
    """
    Create and return a sample Signal for testing.
    
    Args:
        test_db_session: Database session
        sample_symbol: Sample symbol
        sample_strategy: Sample strategy
    
    Returns:
        Signal: Sample signal object
    """
    signal = Signal(
        strategy_id=sample_strategy.id,
        symbol_id=sample_symbol.id,
        action=OrderAction.BUY,
        price=2450.50,
        stop_loss=2400.00,
        target=2550.00,
        confidence=0.75,
        reason="RSI oversold + MACD bullish crossover",
        is_executed=False,
    )
    test_db_session.add(signal)
    test_db_session.commit()
    test_db_session.refresh(signal)
    return signal


@pytest.fixture
def sample_position(
    test_db_session: Session,
    sample_symbol: Symbol
) -> Position:
    """
    Create and return a sample Position for testing.
    
    Args:
        test_db_session: Database session
        sample_symbol: Sample symbol
    
    Returns:
        Position: Sample position object
    
    Example:
        def test_something(sample_position):
            assert sample_position.quantity == 10
            assert sample_position.is_open is True
    """
    position = Position(
        symbol_id=sample_symbol.id,
        quantity=10,
        entry_price=2450.50,
        current_price=2475.00,
        stop_loss=2400.00,
        target=2550.00,
        realized_pnl=0.0,
        unrealized_pnl=245.0,  # (2475 - 2450.50) * 10
        is_open=True,
        trading_mode=TradingMode.PAPER,
        entry_time=datetime.utcnow(),
    )
    test_db_session.add(position)
    test_db_session.commit()
    test_db_session.refresh(position)
    return position


@pytest.fixture
def sample_prices(
    test_db_session: Session,
    sample_symbol: Symbol
) -> list[Price]:
    """
    Create sample price history for testing.
    
    Args:
        test_db_session: Database session
        sample_symbol: Sample symbol
    
    Returns:
        List[Price]: List of price records
    """
    prices = []
    base_date = datetime.utcnow() - timedelta(days=30)
    
    for i in range(30):
        price = Price(
            symbol_id=sample_symbol.id,
            timestamp=base_date + timedelta(days=i),
            open=2400.0 + (i * 5),
            high=2420.0 + (i * 5),
            low=2390.0 + (i * 5),
            close=2410.0 + (i * 5),
            volume=1000000 + (i * 10000),
            timeframe=Timeframe.DAILY,
        )
        prices.append(price)
        test_db_session.add(price)
    
    test_db_session.commit()
    return prices


# ============================================================================
# Mock Services
# ============================================================================

@pytest.fixture
def mock_broker_client():
    """
    Mock broker client for testing without actual API calls.
    
    Returns:
        Mock: Mocked broker client
    
    Example:
        def test_order_placement(mock_broker_client):
            mock_broker_client.place_order.return_value = {"order_id": "123456"}
            result = place_order(...)
            assert result["order_id"] == "123456"
    """
    broker = Mock()
    
    # Configure common broker methods
    broker.place_order = Mock(return_value={
        "order_id": "MOCK123456",
        "status": "COMPLETE",
        "average_price": 2450.50,
        "filled_quantity": 10,
    })
    
    broker.get_positions = Mock(return_value=[
        {
            "symbol": "RELIANCE",
            "quantity": 10,
            "average_price": 2450.50,
            "last_price": 2475.00,
            "pnl": 245.0,
        }
    ])
    
    broker.get_quote = Mock(return_value={
        "symbol": "RELIANCE",
        "last_price": 2475.00,
        "bid": 2474.50,
        "ask": 2475.50,
        "volume": 1234567,
    })
    
    broker.cancel_order = Mock(return_value={"status": "CANCELLED"})
    
    broker.get_order_status = Mock(return_value={
        "order_id": "MOCK123456",
        "status": "COMPLETE",
        "filled_quantity": 10,
    })
    
    return broker


@pytest.fixture
def mock_market_data():
    """
    Mock market data service for testing.
    
    Returns:
        Mock: Mocked market data service
    """
    market_data = Mock()
    
    market_data.get_current_price = Mock(return_value=2475.00)
    market_data.get_historical_data = Mock(return_value=[
        {"date": "2024-01-01", "open": 2400, "high": 2420, "low": 2390, "close": 2410, "volume": 1000000}
        for i in range(30)
    ])
    market_data.get_intraday_data = Mock(return_value=[])
    
    return market_data


# ============================================================================
# Async Mock Services
# ============================================================================

@pytest.fixture
def mock_async_broker_client():
    """
    Mock async broker client for testing async operations.
    
    Returns:
        AsyncMock: Async mocked broker client
    """
    broker = AsyncMock()
    
    broker.place_order = AsyncMock(return_value={
        "order_id": "MOCK123456",
        "status": "COMPLETE",
        "average_price": 2450.50,
        "filled_quantity": 10,
    })
    
    broker.get_positions = AsyncMock(return_value=[
        {
            "symbol": "RELIANCE",
            "quantity": 10,
            "average_price": 2450.50,
            "last_price": 2475.00,
            "pnl": 245.0,
        }
    ])
    
    return broker


# ============================================================================
# Cleanup Helpers
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_database_after_test(test_db_session: Session):
    """
    Automatically cleanup database after each test.
    Runs after every test function.
    
    Args:
        test_db_session: Database session
    """
    yield  # Test runs here
    
    # Cleanup after test
    try:
        # Delete all records in reverse order of dependencies
        test_db_session.query(Position).delete()
        test_db_session.query(Order).delete()
        test_db_session.query(Signal).delete()
        test_db_session.query(Price).delete()
        test_db_session.query(Strategy).delete()
        test_db_session.query(Symbol).delete()
        test_db_session.commit()
    except Exception as e:
        logger.error(f"Error during test cleanup: {e}")
        test_db_session.rollback()


# ============================================================================
# Parametrized Fixtures
# ============================================================================

@pytest.fixture(params=[
    OrderAction.BUY,
    OrderAction.SELL,
])
def order_action(request):
    """
    Parametrized fixture for testing both BUY and SELL actions.
    
    Usage:
        def test_order_action(order_action):
            # This test will run twice, once for BUY and once for SELL
            assert order_action in [OrderAction.BUY, OrderAction.SELL]
    """
    return request.param


@pytest.fixture(params=[
    TradingMode.PAPER,
    TradingMode.LIVE,
])
def trading_mode(request):
    """
    Parametrized fixture for testing both PAPER and LIVE modes.
    """
    return request.param


# ============================================================================
# Helper Functions
# ============================================================================

def create_test_symbol(
    session: Session,
    symbol: str = "TEST",
    company_name: str = "Test Corp",
    **kwargs
) -> Symbol:
    """
    Helper to create custom test symbols.
    
    Args:
        session: Database session
        symbol: Symbol code
        company_name: Company name
        **kwargs: Additional symbol attributes
    
    Returns:
        Symbol: Created symbol
    """
    sym = Symbol(
        symbol=symbol,
        company_name=company_name,
        exchange=kwargs.get("exchange", Exchange.NSE),
        is_active=kwargs.get("is_active", True),
        **{k: v for k, v in kwargs.items() if k not in ["exchange", "is_active"]}
    )
    session.add(sym)
    session.commit()
    session.refresh(sym)
    return sym


def create_test_position(
    session: Session,
    symbol_id: int,
    quantity: int = 10,
    entry_price: float = 100.0,
    **kwargs
) -> Position:
    """
    Helper to create custom test positions.
    
    Args:
        session: Database session
        symbol_id: Symbol ID
        quantity: Position quantity
        entry_price: Entry price
        **kwargs: Additional position attributes
    
    Returns:
        Position: Created position
    """
    pos = Position(
        symbol_id=symbol_id,
        quantity=quantity,
        entry_price=entry_price,
        current_price=kwargs.get("current_price", entry_price),
        is_open=kwargs.get("is_open", True),
        trading_mode=kwargs.get("trading_mode", TradingMode.PAPER),
        **{k: v for k, v in kwargs.items() 
           if k not in ["current_price", "is_open", "trading_mode"]}
    )
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return pos
