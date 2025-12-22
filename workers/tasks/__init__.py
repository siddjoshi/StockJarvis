# workers/tasks/__init__.py
"""
Celery tasks for StockJarvis.
Contains task modules for data collection, signal generation, position monitoring,
risk management, and system maintenance.
"""

from workers.tasks.data_collection import (
    collect_daily_data,
    collect_intraday_data,
    update_symbol_list,
)
from workers.tasks.signal_generation import (
    generate_eod_signals,
    generate_intraday_signals,
    cleanup_old_signals,
)
from workers.tasks.position_monitoring import (
    monitor_positions,
    reconcile_broker_positions,
    update_position_pnl,
)
from workers.tasks.risk_management import (
    check_risk_limits,
    update_circuit_breaker,
    calculate_position_sizes,
)
from workers.tasks.system_maintenance import (
    cleanup_old_data,
    backup_database,
    health_check,
    generate_daily_report,
)

__all__ = [
    # Data collection tasks
    "collect_daily_data",
    "collect_intraday_data",
    "update_symbol_list",
    # Signal generation tasks
    "generate_eod_signals",
    "generate_intraday_signals",
    "cleanup_old_signals",
    # Position monitoring tasks
    "monitor_positions",
    "reconcile_broker_positions",
    "update_position_pnl",
    # Risk management tasks
    "check_risk_limits",
    "update_circuit_breaker",
    "calculate_position_sizes",
    # System maintenance tasks
    "cleanup_old_data",
    "backup_database",
    "health_check",
    "generate_daily_report",
]
