# workers/celeryconfig.py
"""
Celery configuration module for StockJarvis.
Defines comprehensive settings for task execution, scheduling, and monitoring.
"""

from typing import Dict, Any
from datetime import timedelta
from celery.schedules import crontab
from kombu import serialization

# Timezone configuration
timezone = "UTC"
enable_utc = True

# Broker and Result Backend Configuration
broker_connection_retry_on_startup = True
broker_connection_retry = True
broker_connection_max_retries = 10
broker_pool_limit = 10
broker_heartbeat = 30
broker_transport_options = {
    "visibility_timeout": 3600,  # 1 hour
    "max_connections": 50,
    "socket_keepalive": True,
    "socket_timeout": 30,
    "socket_connect_timeout": 30,
}

# Result Backend Configuration
result_backend_transport_options = {
    "master_name": "mymaster",
    "socket_keepalive": True,
    "socket_timeout": 30,
    "retry_on_timeout": True,
    "max_connections": 50,
}
result_expires = 86400  # 24 hours in seconds
result_persistent = True
result_compression = "gzip"
result_extended = True

# Serialization Configuration
task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]
serialization.register_json()

# Task Execution Configuration
task_acks_late = True  # Acknowledge after task completion
task_reject_on_worker_lost = True  # Requeue if worker dies
task_track_started = True  # Track when task starts
task_time_limit = 3600  # 1 hour hard limit
task_soft_time_limit = 3300  # 55 minutes soft limit
task_max_retries = 3  # Default max retries
task_default_retry_delay = 180  # 3 minutes between retries
task_retry_backoff = True  # Exponential backoff
task_retry_backoff_max = 600  # Max 10 minutes backoff
task_retry_jitter = True  # Add jitter to backoff

# Worker Configuration
worker_prefetch_multiplier = 4  # Number of tasks to prefetch
worker_max_tasks_per_child = 1000  # Restart worker after N tasks
worker_disable_rate_limits = False
worker_send_task_events = True  # Enable task events for monitoring
worker_pool_restarts = True  # Enable pool restarts

# Beat Configuration (Task Scheduler)
beat_schedule: Dict[str, Dict[str, Any]] = {
    # Data Collection Tasks
    "collect-daily-data": {
        "task": "workers.tasks.data_collection.collect_daily_data",
        "schedule": crontab(hour=9, minute=0),  # 9:00 AM daily
        "options": {
            "queue": "low_priority",
            "priority": 1,
            "expires": 3600,  # Expire after 1 hour if not executed
        },
    },
    "collect-intraday-data": {
        "task": "workers.tasks.data_collection.collect_intraday_data",
        "schedule": crontab(
            hour="9-15",  # 9 AM to 3 PM
            minute="*/5",  # Every 5 minutes
            day_of_week="mon-fri",  # Weekdays only
        ),
        "options": {
            "queue": "default",
            "priority": 5,
            "expires": 300,  # Expire after 5 minutes
        },
    },
    "update-symbol-list": {
        "task": "workers.tasks.data_collection.update_symbol_list",
        "schedule": crontab(
            hour=8,
            minute=0,
            day_of_week=0,  # Sunday (0 = Sunday, 6 = Saturday)
        ),
        "options": {
            "queue": "low_priority",
            "priority": 1,
            "expires": 7200,  # Expire after 2 hours
        },
    },
    # Signal Generation Tasks
    "generate-eod-signals": {
        "task": "workers.tasks.signal_generation.generate_eod_signals",
        "schedule": crontab(
            hour=15,  # 3 PM
            minute=35,  # 3:35 PM
            day_of_week="mon-fri",
        ),
        "options": {
            "queue": "default",
            "priority": 5,
            "expires": 1800,  # Expire after 30 minutes
        },
    },
    "generate-intraday-signals": {
        "task": "workers.tasks.signal_generation.generate_intraday_signals",
        "schedule": crontab(
            hour="9-15",
            minute="*/5",
            day_of_week="mon-fri",
        ),
        "options": {
            "queue": "high_priority",
            "priority": 10,
            "expires": 300,  # Expire after 5 minutes
        },
    },
    # Position Monitoring Tasks
    "monitor-positions": {
        "task": "workers.tasks.position_monitoring.monitor_positions",
        "schedule": crontab(
            hour="9-15",
            minute="*/2",  # Every 2 minutes
            day_of_week="mon-fri",
        ),
        "options": {
            "queue": "high_priority",
            "priority": 10,
            "expires": 120,  # Expire after 2 minutes
        },
    },
    "reconcile-broker": {
        "task": "workers.tasks.position_monitoring.reconcile_broker_positions",
        "schedule": crontab(
            hour="*/1",  # Every hour
            minute=0,
        ),
        "options": {
            "queue": "default",
            "priority": 5,
            "expires": 3600,  # Expire after 1 hour
        },
    },
    # Risk Management Tasks
    "check-risk-limits": {
        "task": "workers.tasks.risk_management.check_risk_limits",
        "schedule": crontab(
            hour="9-15",
            minute="*/10",  # Every 10 minutes
            day_of_week="mon-fri",
        ),
        "options": {
            "queue": "high_priority",
            "priority": 10,
            "expires": 600,  # Expire after 10 minutes
        },
    },
    # System Maintenance Tasks
    "health-check": {
        "task": "workers.tasks.system_maintenance.health_check",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {
            "queue": "default",
            "priority": 5,
            "expires": 900,  # Expire after 15 minutes
        },
    },
    "cleanup-old-signals": {
        "task": "workers.tasks.signal_generation.cleanup_old_signals",
        "schedule": crontab(hour=2, minute=0),  # 2:00 AM daily
        "options": {
            "queue": "low_priority",
            "priority": 1,
            "expires": 7200,  # Expire after 2 hours
        },
    },
    "backup-database": {
        "task": "workers.tasks.system_maintenance.backup_database",
        "schedule": crontab(hour=1, minute=0),  # 1:00 AM daily
        "options": {
            "queue": "low_priority",
            "priority": 1,
            "expires": 7200,  # Expire after 2 hours
        },
    },
}

# Beat schedule configuration
beat_scheduler = "celery.beat:PersistentScheduler"
beat_schedule_filename = "celerybeat-schedule"  # Database file for beat schedule
beat_sync_every = 0  # Sync immediately
beat_max_loop_interval = 5  # Max seconds between beat wake-ups

# Monitoring and Events
task_send_sent_event = True  # Send task-sent event
worker_send_task_events = True  # Enable task-sent events
task_ignore_result = False  # Store all results

# Error Handling
task_annotations = {
    "*": {
        "rate_limit": "100/m",  # 100 tasks per minute default
        "time_limit": 3600,  # 1 hour
        "soft_time_limit": 3300,  # 55 minutes
        "max_retries": 3,
        "default_retry_delay": 180,  # 3 minutes
    },
    # Override for high-frequency tasks
    "workers.tasks.data_collection.collect_intraday_data": {
        "rate_limit": "12/m",  # Every 5 minutes
        "time_limit": 300,
        "soft_time_limit": 240,
    },
    "workers.tasks.signal_generation.generate_intraday_signals": {
        "rate_limit": "12/m",
        "time_limit": 300,
        "soft_time_limit": 240,
    },
    "workers.tasks.position_monitoring.monitor_positions": {
        "rate_limit": "30/m",  # Every 2 minutes
        "time_limit": 120,
        "soft_time_limit": 90,
    },
    "workers.tasks.risk_management.check_risk_limits": {
        "rate_limit": "6/m",  # Every 10 minutes
        "time_limit": 600,
        "soft_time_limit": 540,
    },
    # Override for long-running tasks
    "workers.tasks.data_collection.collect_daily_data": {
        "rate_limit": "1/m",
        "time_limit": 7200,  # 2 hours
        "soft_time_limit": 6900,
    },
    "workers.tasks.system_maintenance.backup_database": {
        "rate_limit": "1/h",
        "time_limit": 3600,
        "soft_time_limit": 3300,
    },
}

# Task result chord configuration
task_chord_retry_interval = 1  # Seconds between chord header checks

# Task routing
task_create_missing_queues = True  # Auto-create queues
task_default_queue = "default"
task_default_exchange = "default"
task_default_exchange_type = "direct"
task_default_routing_key = "default"

# Redis-specific optimizations
redis_max_connections = 50
redis_socket_timeout = 30
redis_socket_connect_timeout = 30
redis_socket_keepalive = True
redis_socket_keepalive_options = {
    1: 1,  # TCP_KEEPIDLE
    2: 1,  # TCP_KEEPINTVL
    3: 3,  # TCP_KEEPCNT
}

# Security
task_always_eager = False  # Never run tasks synchronously
task_eager_propagates = False  # Don't propagate exceptions when eager

# Database poll interval for beat scheduler
beat_dburi = None  # Use file-based scheduler by default

# Logging
worker_hijack_root_logger = False  # Don't hijack root logger
worker_log_color = True  # Enable colored logs
worker_redirect_stdouts = True  # Redirect stdout/stderr
worker_redirect_stdouts_level = "INFO"

# Performance tuning
worker_pool = "prefork"  # Use prefork pool (multiprocessing)
worker_concurrency = None  # Auto-detect based on CPU count
worker_lost_wait = 10.0  # Seconds to wait for worker to come back

# Task result backend settings
result_chord_join_timeout = 3.0  # Seconds to wait for chord join
result_chord_retry_interval = 1.0  # Seconds between chord retry

# Import task modules
imports = [
    "workers.tasks.data_collection",
    "workers.tasks.signal_generation",
    "workers.tasks.position_monitoring",
    "workers.tasks.risk_management",
    "workers.tasks.system_maintenance",
]
