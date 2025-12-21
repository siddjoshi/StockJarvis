# workers/tasks/__init__.py
"""
Celery tasks for StockJarvis.
Contains task modules for data collection, signal generation, and position monitoring.
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
]
