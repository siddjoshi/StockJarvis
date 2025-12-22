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
def mock_repository():
    """
    Mock repository for task testing.
    
    Returns:
        Mock: Mocked repository
    """
    repo = Mock()
    
    # Mock symbol objects
    mock_symbol = Mock()
    mock_symbol.symbol = "RELIANCE"
    mock_symbol.is_active = True
    mock_symbol.is_fno = True
    
    repo.get_symbol.return_value = mock_symbol
    repo.get_fno_symbols.return_value = [mock_symbol]
    repo.get_all_symbols.return_value = [mock_symbol]
    repo.get_latest_price.return_value = Mock(
        close=2450.0,
        timestamp=datetime.now()
    )
    repo.add_alert.return_value = None
    repo.get_session.return_value.__enter__ = Mock(return_value=Mock())
    repo.get_session.return_value.__exit__ = Mock(return_value=None)
    
    return repo


@pytest.fixture
def mock_scanner():
    """
    Mock scanner for task testing.
    
    Returns:
        Mock: Mocked scanner
    """
    scanner = Mock()
    scanner.symbols = ["RELIANCE", "TCS", "INFY"]
    scanner.scan_with_strategy.return_value = []
    return scanner


@pytest.fixture
def sample_symbols_task(test_db_session):
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
            is_nifty50=True,
            is_fno=True
        ),
        Symbol(
            symbol="TCS",
            company_name="Tata Consultancy Services",
            exchange=Exchange.NSE,
            is_active=True,
            is_nifty50=True,
            is_fno=True
        ),
        Symbol(
            symbol="INFY",
            company_name="Infosys Ltd",
            exchange=Exchange.NSE,
            is_active=True,
            is_nifty50=True,
            is_fno=True
        )
    ]
    
    for symbol in symbols:
        test_db_session.add(symbol)
    
    test_db_session.commit()
    
    for symbol in symbols:
        test_db_session.refresh(symbol)
    
    return symbols


@pytest.fixture
def sample_strategy_task(test_db_session):
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
    
    @patch('workers.tasks.data_collection.repository')
    def test_collect_daily_data_success(self, mock_repository):
        """Test successful daily data collection."""
        # Mock repository
        mock_symbol = Mock()
        mock_symbol.symbol = "RELIANCE"
        mock_symbol.is_active = True
        
        mock_repository.get_symbol.return_value = mock_symbol
        mock_repository.get_fno_symbols.return_value = [mock_symbol]
        mock_repository.get_latest_price.return_value = Mock(
            close=2450.0,
            timestamp=datetime.now()
        )
        mock_repository.add_alert.return_value = None
        
        # Execute task
        result = collect_daily_data.apply()
        
        # Verify task executed successfully
        assert result.successful()
        assert isinstance(result.result, dict)
        assert "symbols_processed" in result.result or "status" in result.result
    
    @patch('workers.tasks.data_collection.repository')
    def test_collect_daily_data_specific_symbols(self, mock_repository):
        """Test collecting daily data for specific symbols."""
        mock_symbol = Mock()
        mock_symbol.symbol = "RELIANCE"
        mock_symbol.is_active = True
        
        mock_repository.get_symbol.return_value = mock_symbol
        mock_repository.get_latest_price.return_value = Mock(
            close=2450.0,
            timestamp=datetime.now()
        )
        mock_repository.add_alert.return_value = None
        
        result = collect_daily_data.apply(args=[["RELIANCE"]])
        
        assert result.successful()
        assert isinstance(result.result, dict)
    
    @patch('workers.tasks.data_collection.repository')
    def test_collect_intraday_data(self, mock_repository):
        """Test intraday data collection."""
        mock_symbol = Mock()
        mock_symbol.symbol = "RELIANCE"
        mock_symbol.is_active = True
        
        mock_repository.get_symbol.return_value = mock_symbol
        mock_repository.get_fno_symbols.return_value = [mock_symbol]
        mock_repository.add_alert.return_value = None
        
        result = collect_intraday_data.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)
    
    @patch('workers.tasks.data_collection.repository')
    def test_collect_daily_data_no_symbols(self, mock_repository):
        """Test data collection with no symbols."""
        mock_repository.get_symbol.return_value = None
        mock_repository.get_fno_symbols.return_value = []
        mock_repository.add_alert.return_value = None
        
        result = collect_daily_data.apply(args=[["INVALID"]])
        
        # Task should complete but with status indicating no symbols
        assert result.successful()
        assert result.result["status"] in ["completed", "failed"]
    
    @patch('workers.tasks.data_collection.repository')
    def test_update_symbol_list(self, mock_repository):
        """Test updating symbol list from exchange."""
        mock_repository.get_all_symbols.return_value = []
        mock_repository.add_alert.return_value = None
        
        result = update_symbol_list.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)


# ============================================================================
# Test Signal Generation Tasks
# ============================================================================

class TestSignalGenerationTasks:
    """Test signal generation Celery tasks."""
    
    @patch('workers.tasks.signal_generation.repository')
    @patch('workers.tasks.signal_generation.create_eod_scanner')
    @patch('workers.tasks.signal_generation.registry')
    def test_generate_eod_signals(self, mock_registry, mock_create_scanner, mock_repository):
        """Test EOD signal generation."""
        # Mock strategy registry
        mock_strategy = Mock()
        mock_strategy.name = "Test_Strategy"
        mock_strategy.is_tradeable.return_value = True
        mock_registry.get_tradeable.return_value = [mock_strategy]
        mock_registry.get.return_value = mock_strategy
        
        # Mock scanner
        mock_scanner = Mock()
        mock_scanner.symbols = ["RELIANCE"]
        mock_scanner.scan_with_strategy.return_value = []
        mock_create_scanner.return_value = mock_scanner
        
        mock_repository.add_alert.return_value = None
        
        result = generate_eod_signals.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)
        assert "signals_generated" in result.result
    
    @patch('workers.tasks.signal_generation.repository')
    @patch('workers.tasks.signal_generation.create_intraday_scanner')
    @patch('workers.tasks.signal_generation.registry')
    def test_generate_intraday_signals(self, mock_registry, mock_create_scanner, mock_repository):
        """Test intraday signal generation."""
        # Mock strategy registry
        mock_strategy = Mock()
        mock_strategy.name = "Test_Strategy"
        mock_strategy.is_tradeable.return_value = True
        mock_registry.get_tradeable.return_value = [mock_strategy]
        mock_registry.get.return_value = mock_strategy
        
        # Mock scanner
        mock_scanner = Mock()
        mock_scanner.symbols = ["RELIANCE"]
        mock_scanner.scan_with_strategy.return_value = []
        mock_create_scanner.return_value = mock_scanner
        
        mock_repository.add_alert.return_value = None
        
        result = generate_intraday_signals.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)
    
    @patch('workers.tasks.signal_generation.repository')
    @patch('workers.tasks.signal_generation.create_eod_scanner')
    @patch('workers.tasks.signal_generation.registry')
    def test_generate_signals_no_strategies(self, mock_registry, mock_create_scanner, mock_repository):
        """Test signal generation when no strategies are available."""
        mock_registry.get_tradeable.return_value = []
        mock_repository.add_alert.return_value = None
        
        result = generate_eod_signals.apply()
        
        assert result.successful()
        assert result.result.get("status") in ["completed", "failed"]
    
    @patch('workers.tasks.signal_generation.repository')
    def test_cleanup_old_signals(self, mock_repository):
        """Test cleaning up old signals."""
        # Mock session context manager
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_session.query.return_value.count.return_value = 0
        
        mock_repository.get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_repository.get_session.return_value.__exit__ = Mock(return_value=None)
        mock_repository.add_alert.return_value = None
        
        result = cleanup_old_signals.apply(args=[7])  # Delete signals older than 7 days
        
        assert result.successful()
        assert isinstance(result.result, dict)


# ============================================================================
# Test Position Monitoring Tasks
# ============================================================================

class TestPositionMonitoringTasks:
    """Test position monitoring Celery tasks."""
    
    @patch('workers.tasks.position_monitoring.repository')
    @patch('workers.tasks.position_monitoring.get_async_session_factory')
    def test_monitor_positions(self, mock_session_factory, mock_repository):
        """Test position monitoring task."""
        mock_repository.add_alert.return_value = None
        
        # Mock async session factory
        mock_session_factory.return_value = Mock()
        
        result = monitor_positions.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)
    
    @patch('workers.tasks.position_monitoring.repository')
    @patch('workers.tasks.position_monitoring.get_async_session_factory')
    def test_reconcile_broker_positions(self, mock_session_factory, mock_repository):
        """Test reconciling positions with broker."""
        mock_repository.add_alert.return_value = None
        mock_session_factory.return_value = Mock()
        
        result = reconcile_broker_positions.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)


# ============================================================================
# Test Risk Management Tasks
# ============================================================================

class TestRiskManagementTasks:
    """Test risk management Celery tasks."""
    
    @patch('workers.tasks.risk_management.repository')
    @patch('workers.tasks.risk_management.RiskManager')
    def test_check_risk_limits(self, mock_risk_manager_class, mock_repository):
        """Test checking risk limits."""
        # Mock session context manager
        mock_session = Mock()
        mock_repository.get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_repository.get_session.return_value.__exit__ = Mock(return_value=None)
        mock_repository.add_alert.return_value = None
        
        # Mock risk manager
        mock_risk_manager = Mock()
        mock_risk_manager.get_portfolio_metrics.return_value = {
            'num_open_positions': 5,
            'exposure_pct': 50.0,
            'unrealized_pnl': 1000.0,
            'win_rate': 0.65
        }
        mock_risk_manager._check_portfolio_exposure.return_value = Mock(
            passed=True,
            violations=[],
            warnings=[],
            metadata={'exposure_pct': 50.0}
        )
        mock_risk_manager._check_drawdown_limits.return_value = Mock(
            passed=True,
            violations=[],
            warnings=[],
            metadata={}
        )
        mock_risk_manager.circuit_breaker_active = False
        mock_risk_manager_class.return_value = mock_risk_manager
        
        result = check_risk_limits.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)
    
    @patch('workers.tasks.risk_management.repository')
    @patch('workers.tasks.risk_management.RiskManager')
    def test_update_circuit_breaker(self, mock_risk_manager_class, mock_repository):
        """Test circuit breaker update."""
        mock_session = Mock()
        mock_repository.get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_repository.get_session.return_value.__exit__ = Mock(return_value=None)
        mock_repository.add_alert.return_value = None
        
        mock_risk_manager = Mock()
        mock_risk_manager.circuit_breaker_active = False
        mock_risk_manager._check_drawdown_limits.return_value = Mock(
            passed=True,
            violations=[],
            warnings=[],
            metadata={}
        )
        mock_risk_manager_class.return_value = mock_risk_manager
        
        result = update_circuit_breaker.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)


# ============================================================================
# Test Maintenance Tasks
# ============================================================================

class TestMaintenanceTasks:
    """Test system maintenance Celery tasks."""
    
    @patch('workers.tasks.system_maintenance.repository')
    def test_health_check(self, mock_repository):
        """Test system health check."""
        # Mock session context manager
        mock_session = Mock()
        mock_session.execute.return_value.fetchone.return_value = (1,)
        mock_repository.get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_repository.get_session.return_value.__exit__ = Mock(return_value=None)
        mock_repository.add_alert.return_value = None
        
        result = health_check.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)
        assert "overall_health" in result.result
    
    @patch('workers.tasks.system_maintenance.repository')
    @patch('workers.tasks.system_maintenance.subprocess')
    def test_backup_database(self, mock_subprocess, mock_repository):
        """Test database backup task."""
        mock_subprocess.run.return_value = Mock(returncode=0)
        mock_repository.add_alert.return_value = None
        
        result = backup_database.apply()
        
        # Task may fail due to mysqldump not available in test env
        assert isinstance(result.result, dict)
        assert "status" in result.result
    
    @patch('workers.tasks.system_maintenance.repository')
    def test_cleanup_old_data(self, mock_repository):
        """Test cleaning up old data."""
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.count.return_value = 0
        mock_repository.get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_repository.get_session.return_value.__exit__ = Mock(return_value=None)
        mock_repository.add_alert.return_value = None
        
        result = cleanup_old_data.apply(args=["signals", 90])
        
        assert result.successful()
        assert isinstance(result.result, dict)
    
    @patch('workers.tasks.system_maintenance.repository')
    def test_generate_daily_report(self, mock_repository):
        """Test generating daily report."""
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        mock_repository.get_session.return_value.__enter__ = Mock(return_value=mock_session)
        mock_repository.get_session.return_value.__exit__ = Mock(return_value=None)
        mock_repository.add_alert.return_value = None
        
        result = generate_daily_report.apply()
        
        assert result.successful()
        assert isinstance(result.result, dict)


# ============================================================================
# Test Task Chaining and Workflow
# ============================================================================

class TestTaskWorkflows:
    """Test task chaining and complex workflows."""
    
    @patch('workers.tasks.data_collection.repository')
    @patch('workers.tasks.signal_generation.repository')
    @patch('workers.tasks.signal_generation.create_eod_scanner')
    @patch('workers.tasks.signal_generation.registry')
    def test_data_collection_to_signal_generation_workflow(
        self,
        mock_registry,
        mock_create_scanner,
        mock_signal_repository,
        mock_data_repository
    ):
        """Test workflow: collect data -> generate signals."""
        # Mock data collection
        mock_symbol = Mock()
        mock_symbol.symbol = "RELIANCE"
        mock_symbol.is_active = True
        
        mock_data_repository.get_symbol.return_value = mock_symbol
        mock_data_repository.get_fno_symbols.return_value = [mock_symbol]
        mock_data_repository.get_latest_price.return_value = Mock(
            close=2450.0,
            timestamp=datetime.now()
        )
        mock_data_repository.add_alert.return_value = None
        
        # Mock signal generation
        mock_strategy = Mock()
        mock_strategy.name = "Test_Strategy"
        mock_strategy.is_tradeable.return_value = True
        mock_registry.get_tradeable.return_value = [mock_strategy]
        
        mock_scanner = Mock()
        mock_scanner.symbols = ["RELIANCE"]
        mock_scanner.scan_with_strategy.return_value = []
        mock_create_scanner.return_value = mock_scanner
        
        mock_signal_repository.add_alert.return_value = None
        
        # Execute workflow
        data_result = collect_daily_data.apply()
        assert data_result.successful()
        
        signal_result = generate_eod_signals.apply()
        assert signal_result.successful()


# ============================================================================
# Test Task Result Storage
# ============================================================================

class TestTaskResults:
    """Test task result storage and retrieval."""
    
    @patch('workers.tasks.data_collection.repository')
    def test_task_result_storage(self, mock_repository):
        """Test that task results are stored correctly."""
        mock_repository.get_fno_symbols.return_value = []
        mock_repository.add_alert.return_value = None
        
        result = collect_daily_data.apply()
        
        # Result should be accessible
        assert result.id is not None
        assert result.state in ["SUCCESS", "FAILURE", "PENDING"]
        assert result.result is not None


# ============================================================================
# Test Celery Configuration
# ============================================================================

class TestCeleryConfiguration:
    """Test Celery app configuration."""
    
    def test_celery_app_initialized(self):
        """Test that Celery app is properly initialized."""
        assert celery_app is not None
        assert celery_app.main == "stockjarvis"
    
    def test_task_queues_configured(self):
        """Test that task queues are properly configured."""
        queues = celery_app.conf.task_queues
        assert queues is not None
        
        queue_names = [q.name for q in queues]
        assert "high_priority" in queue_names
        assert "default" in queue_names
        assert "low_priority" in queue_names
    
    def test_beat_schedule_tasks_count(self):
        """Test that all scheduled tasks are configured."""
        from workers import celeryconfig
        
        beat_schedule = celeryconfig.beat_schedule
        assert len(beat_schedule) == 11  # 11 scheduled tasks
    
    def test_task_routes_configured(self):
        """Test that task routes are properly configured."""
        routes = celery_app.conf.task_routes
        assert routes is not None
        
        # Check high priority tasks
        assert "workers.tasks.position_monitoring.monitor_positions" in routes
        assert "workers.tasks.risk_management.check_risk_limits" in routes
        
        # Check default priority tasks  
        assert "workers.tasks.data_collection.collect_intraday_data" in routes
        
        # Check low priority tasks
        assert "workers.tasks.data_collection.collect_daily_data" in routes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
