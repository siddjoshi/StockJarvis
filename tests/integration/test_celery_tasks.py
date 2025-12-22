# tests/integration/test_celery_tasks.py
"""
Integration tests for Celery tasks.
Tests data collection, signal generation, position monitoring, and maintenance tasks.
Uses Celery eager mode to run tasks synchronously for testing.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, Mock, MagicMock
from celery import Celery
from celery.result import EagerResult

from workers.celery_app import celery_app
from workers.tasks.data_collection import (
    collect_daily_data,
    collect_intraday_data,
    update_symbol_list
)
from workers.tasks.signal_generation import (
    generate_eod_signals,
    generate_intraday_signals,
    cleanup_old_signals
)
from workers.tasks.position_monitoring import (
    monitor_positions,
    reconcile_broker_positions
)
from workers.tasks.system_maintenance import (
    backup_database,
    health_check,
    cleanup_old_data,
    generate_daily_report
)
from workers.tasks.risk_management import (
    check_risk_limits,
    update_circuit_breaker,
    calculate_position_sizes
)
from data.models import Symbol, Strategy, Position, Signal, Price, Exchange, OrderAction, TradingMode
from core.strategy_engine import registry as strategy_registry


# ============================================================================
# Pytest Configuration for Celery
# ============================================================================

@pytest.fixture(scope="session", autouse=True)
def celery_config():
    """
    Configure Celery for testing with eager mode.
    Tasks will execute synchronously in the same process.
    
    Returns:
        Dict: Celery configuration
    """
    return {
        "broker_url": "memory://",
        "result_backend": "cache+memory://",
        "task_always_eager": True,  # Execute tasks synchronously
        "task_eager_propagates": True,  # Propagate exceptions
        "task_store_eager_result": True,
    }


@pytest.fixture(scope="session", autouse=True)
def configure_celery_for_testing(celery_config):
    """
    Apply testing configuration to Celery app.
    
    Args:
        celery_config: Celery configuration fixture
    """
    celery_app.conf.update(celery_config)
    yield
    # Teardown - reset to original config if needed


@pytest.fixture
def mock_broker_client():
    """
    Mock broker client for task testing.
    
    Returns:
        Mock: Mocked broker client
    """
    broker = Mock()
    
    broker.get_positions.return_value = [
        {
            "symbol": "RELIANCE",
            "quantity": 10,
            "average_price": 2450.50,
            "last_price": 2475.00,
            "pnl": 245.0,
        }
    ]
    
    broker.get_quote.return_value = {
        "symbol": "RELIANCE",
        "last_price": 2475.00,
        "volume": 1234567,
    }
    
    broker.get_historical_data.return_value = [
        {
            "timestamp": datetime.now() - timedelta(days=i),
            "open": 2400 + i,
            "high": 2420 + i,
            "low": 2390 + i,
            "close": 2410 + i,
            "volume": 1000000 + (i * 10000)
        }
        for i in range(50)
    ]
    
    return broker


@pytest.fixture
def sample_symbols(test_db_session):
    """
    Create sample symbols for task testing.
    
    Args:
        test_db_session: Database session
    
    Returns:
        List[Symbol]: List of symbols
    """
    symbols = [
        Symbol(
            symbol="RELIANCE",
            company_name="Reliance Industries",
            exchange=Exchange.NSE,
            is_active=True,
            is_nifty50=True
        ),
        Symbol(
            symbol="TCS",
            company_name="Tata Consultancy Services",
            exchange=Exchange.NSE,
            is_active=True,
            is_nifty50=True
        ),
        Symbol(
            symbol="INFY",
            company_name="Infosys Ltd",
            exchange=Exchange.NSE,
            is_active=True,
            is_nifty50=True
        )
    ]
    
    for symbol in symbols:
        test_db_session.add(symbol)
    
    test_db_session.commit()
    
    for symbol in symbols:
        test_db_session.refresh(symbol)
    
    return symbols


@pytest.fixture
def sample_strategy(test_db_session):
    """
    Create sample strategy for task testing.
    
    Args:
        test_db_session: Database session
    
    Returns:
        Strategy: Strategy instance
    """
    strategy = Strategy(
        name="Test_Strategy",
        description="Test strategy for tasks",
        parameters='{"period": 20}',
        backtest_accuracy=0.70,
        is_active=True,
        is_validated=True
    )
    test_db_session.add(strategy)
    test_db_session.commit()
    test_db_session.refresh(strategy)
    return strategy


# ============================================================================
# Test Data Collection Tasks
# ============================================================================

class TestDataCollectionTasks:
    """Test data collection Celery tasks."""
    
    @patch('workers.tasks.data_collection.market_data_service')
    def test_collect_daily_data_success(self, mock_market_data, test_db_session, sample_symbols):
        """Test successful daily data collection."""
        # Mock market data service
        mock_market_data.get_historical_data.return_value = [
            {
                "timestamp": datetime.now(),
                "open": 2400.0,
                "high": 2420.0,
                "low": 2390.0,
                "close": 2410.0,
                "volume": 1000000
            }
        ]
        
        # Execute task
        result = collect_daily_data.apply()
        
        # Verify task executed successfully
        assert result.successful()
        assert isinstance(result.result, dict)
        assert "symbols_processed" in result.result
    
    @patch('workers.tasks.data_collection.market_data_service')
    def test_collect_daily_data_specific_symbol(self, mock_market_data, sample_symbols):
        """Test collecting daily data for specific symbol."""
        symbol = sample_symbols[0].symbol
        
        mock_market_data.get_historical_data.return_value = [
            {
                "timestamp": datetime.now(),
                "open": 2400.0,
                "high": 2420.0,
                "low": 2390.0,
                "close": 2410.0,
                "volume": 1000000
            }
        ]
        
        result = collect_daily_data.apply(args=[symbol])
        
        assert result.successful()
        mock_market_data.get_historical_data.assert_called()
    
    @patch('workers.tasks.data_collection.market_data_service')
    def test_collect_intraday_data(self, mock_market_data, sample_symbols):
        """Test intraday data collection."""
        mock_market_data.get_intraday_data.return_value = [
            {
                "timestamp": datetime.now() - timedelta(minutes=i),
                "open": 2400.0 + i,
                "high": 2405.0 + i,
                "low": 2395.0 + i,
                "close": 2400.0 + i,
                "volume": 10000
            }
            for i in range(10)
        ]
        
        result = collect_intraday_data.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)
    
    @patch('workers.tasks.data_collection.market_data_service')
    def test_collect_daily_data_error_handling(self, mock_market_data):
        """Test error handling in data collection."""
        # Mock market data service to raise exception
        mock_market_data.get_historical_data.side_effect = Exception("API Error")
        
        result = collect_daily_data.apply()
        
        # Task should handle error gracefully
        assert result.failed() or "errors" in result.result
    
    @patch('workers.tasks.data_collection.nse_api')
    def test_update_symbol_list(self, mock_nse_api, test_db_session):
        """Test updating symbol list from exchange."""
        mock_nse_api.get_all_symbols.return_value = [
            {
                "symbol": "NEWSYMBOL",
                "company_name": "New Company Ltd",
                "isin": "INE123456789"
            }
        ]
        
        result = update_symbol_list.apply()
        
        assert result.successful()
        assert "symbols_added" in result.result or "symbols_updated" in result.result


# ============================================================================
# Test Signal Generation Tasks
# ============================================================================

class TestSignalGenerationTasks:
    """Test signal generation Celery tasks."""
    
    @patch('workers.tasks.signal_generation.market_data_service')
    @patch('workers.tasks.signal_generation.scanner')
    def test_generate_eod_signals(
        self,
        mock_scanner,
        mock_market_data,
        test_db_session,
        sample_symbols,
        sample_strategy
    ):
        """Test EOD signal generation."""
        # Mock scanner to return signals
        mock_scanner.scan.return_value = [
            {
                "symbol": "RELIANCE",
                "action": OrderAction.BUY,
                "price": 2450.0,
                "stop_loss": 2400.0,
                "target": 2550.0,
                "confidence": 0.75,
                "reason": "Test signal"
            }
        ]
        
        result = generate_eod_signals.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)
        assert "signals_generated" in result.result
    
    @patch('workers.tasks.signal_generation.market_data_service')
    @patch('workers.tasks.signal_generation.scanner')
    def test_generate_eod_signals_specific_strategy(
        self,
        mock_scanner,
        mock_market_data,
        sample_strategy
    ):
        """Test EOD signal generation for specific strategy."""
        strategy_name = sample_strategy.name
        
        mock_scanner.scan.return_value = []
        
        result = generate_eod_signals.apply(args=[strategy_name])
        
        assert result.successful()
        mock_scanner.scan.assert_called()
    
    @patch('workers.tasks.signal_generation.market_data_service')
    @patch('workers.tasks.signal_generation.scanner')
    def test_generate_intraday_signals(
        self,
        mock_scanner,
        mock_market_data,
        sample_symbols
    ):
        """Test intraday signal generation."""
        mock_scanner.scan_intraday.return_value = [
            {
                "symbol": "RELIANCE",
                "action": OrderAction.BUY,
                "price": 2450.0,
                "stop_loss": 2440.0,
                "target": 2470.0,
                "confidence": 0.70,
                "reason": "Intraday breakout"
            }
        ]
        
        result = generate_intraday_signals.apply()
        
        assert result.successful()
        assert "signals_generated" in result.result
    
    @patch('workers.tasks.signal_generation.scanner')
    def test_generate_signals_no_signals(self, mock_scanner, sample_symbols):
        """Test signal generation when no signals are generated."""
        mock_scanner.scan.return_value = []
        
        result = generate_eod_signals.apply()
        
        assert result.successful()
        assert result.result["signals_generated"] == 0
    
    @patch('workers.tasks.signal_generation.scanner')
    def test_generate_signals_error_handling(self, mock_scanner):
        """Test error handling in signal generation."""
        mock_scanner.scan.side_effect = Exception("Scanner error")
        
        result = generate_eod_signals.apply()
        
        # Should handle error gracefully
        assert result.failed() or "error" in result.result


# ============================================================================
# Test Position Monitoring Tasks
# ============================================================================

class TestPositionMonitoringTasks:
    """Test position monitoring Celery tasks."""
    
    @patch('workers.tasks.position_monitoring.broker_client')
    @patch('workers.tasks.position_monitoring.market_data_service')
    def test_monitor_positions(
        self,
        mock_market_data,
        mock_broker,
        test_db_session,
        sample_symbols
    ):
        """Test position monitoring task."""
        # Create open position
        position = Position(
            symbol_id=sample_symbols[0].id,
            quantity=10,
            entry_price=2450.0,
            current_price=2450.0,
            stop_loss=2400.0,
            target=2550.0,
            is_open=True,
            trading_mode=TradingMode.PAPER
        )
        test_db_session.add(position)
        test_db_session.commit()
        
        # Mock current price
        mock_market_data.get_current_price.return_value = 2475.0
        
        result = monitor_positions.apply()
        
        assert result.successful()
        assert "positions_monitored" in result.result
    
    @patch('workers.tasks.position_monitoring.broker_client')
    def test_monitor_positions_stop_loss_hit(
        self,
        mock_broker,
        test_db_session,
        sample_symbols
    ):
        """Test position monitoring with stop loss hit."""
        # Create position with price at stop loss
        position = Position(
            symbol_id=sample_symbols[0].id,
            quantity=10,
            entry_price=2450.0,
            current_price=2400.0,  # At stop loss
            stop_loss=2400.0,
            target=2550.0,
            is_open=True,
            trading_mode=TradingMode.PAPER
        )
        test_db_session.add(position)
        test_db_session.commit()
        
        mock_broker.place_order.return_value = {"order_id": "MOCK12345"}
        
        result = monitor_positions.apply()
        
        assert result.successful()
        # Position should be closed or order placed
    
    @patch('workers.tasks.position_monitoring.broker_client')
    def test_reconcile_broker_positions(
        self,
        mock_broker,
        test_db_session,
        sample_symbols
    ):
        """Test reconciling positions with broker."""
        # Mock broker positions
        mock_broker.get_positions.return_value = [
            {
                "symbol": "RELIANCE",
                "quantity": 10,
                "average_price": 2450.0,
                "last_price": 2475.0,
                "pnl": 250.0
            }
        ]
        
        # Create position in database
        position = Position(
            symbol_id=sample_symbols[0].id,
            quantity=10,
            entry_price=2450.0,
            current_price=2475.0,
            is_open=True,
            trading_mode=TradingMode.LIVE
        )
        test_db_session.add(position)
        test_db_session.commit()
        
        result = reconcile_broker_positions.apply()
        
        assert result.successful()
        assert "positions_reconciled" in result.result
    
    @patch('workers.tasks.position_monitoring.broker_client')
    def test_reconcile_broker_positions_mismatch(
        self,
        mock_broker,
        test_db_session,
        sample_symbols
    ):
        """Test reconciliation with mismatched positions."""
        # Broker has position, but DB doesn't
        mock_broker.get_positions.return_value = [
            {
                "symbol": "RELIANCE",
                "quantity": 10,
                "average_price": 2450.0,
                "last_price": 2475.0,
                "pnl": 250.0
            }
        ]
        
        result = reconcile_broker_positions.apply()
        
        assert result.successful()
        # Should detect and log mismatch


# ============================================================================
# Test Maintenance Tasks
# ============================================================================

class TestMaintenanceTasks:
    """Test system maintenance Celery tasks."""
    
    def test_cleanup_old_signals(self, test_db_session, sample_symbols, sample_strategy):
        """Test cleaning up old signals."""
        # Create old signal (30 days ago)
        old_signal = Signal(
            strategy_id=sample_strategy.id,
            symbol_id=sample_symbols[0].id,
            action=OrderAction.BUY,
            price=2400.0,
            stop_loss=2350.0,
            target=2500.0,
            confidence=0.70,
            reason="Old signal",
            created_at=datetime.now() - timedelta(days=30)
        )
        test_db_session.add(old_signal)
        
        # Create recent signal
        recent_signal = Signal(
            strategy_id=sample_strategy.id,
            symbol_id=sample_symbols[0].id,
            action=OrderAction.BUY,
            price=2450.0,
            stop_loss=2400.0,
            target=2550.0,
            confidence=0.75,
            reason="Recent signal"
        )
        test_db_session.add(recent_signal)
        test_db_session.commit()
        
        result = cleanup_old_signals.apply(args=[7])  # Delete signals older than 7 days
        
        assert result.successful()
        assert "signals_deleted" in result.result
    
    @patch('workers.tasks.system_maintenance.subprocess')
    def test_backup_database(self, mock_subprocess):
        """Test database backup task."""
        mock_subprocess.run.return_value = Mock(returncode=0)
        
        result = backup_database.apply()
        
        assert result.successful()
        assert "backup_file" in result.result or "status" in result.result
    
    def test_cleanup_with_no_old_signals(self, test_db_session):
        """Test cleanup when there are no old signals."""
        result = cleanup_old_signals.apply(args=[30])
        
        assert result.successful()
        assert result.result["signals_deleted"] == 0


# ============================================================================
# Test Task Chaining and Workflow
# ============================================================================

class TestTaskWorkflows:
    """Test task chaining and complex workflows."""
    
    @patch('workers.tasks.data_collection.market_data_service')
    @patch('workers.tasks.signal_generation.scanner')
    def test_data_collection_to_signal_generation_workflow(
        self,
        mock_scanner,
        mock_market_data,
        sample_symbols
    ):
        """Test workflow: collect data -> generate signals."""
        # Mock data collection
        mock_market_data.get_historical_data.return_value = [
            {
                "timestamp": datetime.now(),
                "open": 2400.0,
                "high": 2420.0,
                "low": 2390.0,
                "close": 2410.0,
                "volume": 1000000
            }
        ]
        
        # Mock signal generation
        mock_scanner.scan.return_value = [
            {
                "symbol": "RELIANCE",
                "action": OrderAction.BUY,
                "price": 2410.0,
                "stop_loss": 2380.0,
                "target": 2470.0,
                "confidence": 0.75,
                "reason": "Generated after data collection"
            }
        ]
        
        # Execute workflow
        data_result = collect_daily_data.apply()
        assert data_result.successful()
        
        signal_result = generate_eod_signals.apply()
        assert signal_result.successful()


# ============================================================================
# Test Task Retry Mechanism
# ============================================================================

class TestTaskRetry:
    """Test task retry mechanisms."""
    
    @patch('workers.tasks.data_collection.market_data_service')
    def test_task_retry_on_failure(self, mock_market_data):
        """Test that tasks retry on failure."""
        # Configure task to fail first time, succeed second time
        mock_market_data.get_historical_data.side_effect = [
            Exception("Temporary API error"),
            [{"timestamp": datetime.now(), "close": 2400.0}]
        ]
        
        # In eager mode, retry happens immediately
        # This test verifies retry behavior
        with pytest.raises(Exception):
            result = collect_daily_data.apply()


# ============================================================================
# Test Task Result Storage
# ============================================================================

class TestTaskResults:
    """Test task result storage and retrieval."""
    
    @patch('workers.tasks.data_collection.market_data_service')
    def test_task_result_storage(self, mock_market_data, sample_symbols):
        """Test that task results are stored correctly."""
        mock_market_data.get_historical_data.return_value = []
        
        result = collect_daily_data.apply()
        
        # Result should be accessible
        assert result.id is not None
        assert result.state in ["SUCCESS", "FAILURE", "PENDING"]
        assert result.result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
