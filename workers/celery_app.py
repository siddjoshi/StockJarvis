# workers/celery_app.py
"""
Celery application configuration for StockJarvis.
Manages distributed task queue with Redis broker and result backend.
"""

from typing import Any, Dict, List, Optional
import logging
from celery import Celery, Task
from celery.signals import task_failure, task_success, task_retry, worker_ready
from kombu import Queue, Exchange

from config.settings import settings
from core.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

# Create Celery application instance
celery_app = Celery(
    "stockjarvis",
    broker=settings.redis.url,
    backend=settings.redis.url,
    include=[
        "workers.tasks.data_collection",
        "workers.tasks.signal_generation",
        "workers.tasks.position_monitoring",
        "workers.tasks.risk_management",
        "workers.tasks.system_maintenance",
    ],
)

# Load configuration from celeryconfig module
celery_app.config_from_object("workers.celeryconfig")

# Define task queues with priority routing
default_exchange = Exchange("default", type="direct")

celery_app.conf.task_queues = (
    Queue(
        "high_priority",
        exchange=default_exchange,
        routing_key="high",
        priority=10,
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "default",
        exchange=default_exchange,
        routing_key="default",
        priority=5,
        queue_arguments={"x-max-priority": 10},
    ),
    Queue(
        "low_priority",
        exchange=default_exchange,
        routing_key="low",
        priority=1,
        queue_arguments={"x-max-priority": 10},
    ),
)

# Task routing configuration
celery_app.conf.task_routes = {
    # High priority tasks - real-time monitoring and trading
    "workers.tasks.position_monitoring.monitor_positions": {
        "queue": "high_priority",
        "routing_key": "high",
    },
    "workers.tasks.risk_management.check_risk_limits": {
        "queue": "high_priority",
        "routing_key": "high",
    },
    "workers.tasks.signal_generation.generate_intraday_signals": {
        "queue": "high_priority",
        "routing_key": "high",
    },
    # Default priority tasks - regular operations
    "workers.tasks.data_collection.collect_intraday_data": {
        "queue": "default",
        "routing_key": "default",
    },
    "workers.tasks.signal_generation.generate_eod_signals": {
        "queue": "default",
        "routing_key": "default",
    },
    "workers.tasks.position_monitoring.reconcile_broker_positions": {
        "queue": "default",
        "routing_key": "default",
    },
    "workers.tasks.system_maintenance.health_check": {
        "queue": "default",
        "routing_key": "default",
    },
    # Low priority tasks - maintenance and batch operations
    "workers.tasks.data_collection.collect_daily_data": {
        "queue": "low_priority",
        "routing_key": "low",
    },
    "workers.tasks.data_collection.update_symbol_list": {
        "queue": "low_priority",
        "routing_key": "low",
    },
    "workers.tasks.signal_generation.cleanup_old_signals": {
        "queue": "low_priority",
        "routing_key": "low",
    },
    "workers.tasks.system_maintenance.backup_database": {
        "queue": "low_priority",
        "routing_key": "low",
    },
}


class CallbackTask(Task):
    """
    Base task class with custom error handling and callbacks.
    """

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: Dict[str, Any],
        einfo: Any,
    ) -> None:
        """
        Handle task failure with detailed logging.
        
        Args:
            exc: The exception raised by the task
            task_id: Unique identifier of the failed task
            args: Positional arguments of the task
            kwargs: Keyword arguments of the task
            einfo: Exception info object
        """
        logger.error(
            f"Task {self.name} [{task_id}] failed",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "exception": str(exc),
                "args": args,
                "kwargs": kwargs,
                "traceback": str(einfo),
            },
        )

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: Dict[str, Any],
        einfo: Any,
    ) -> None:
        """
        Handle task retry with logging.
        
        Args:
            exc: The exception that triggered the retry
            task_id: Unique identifier of the task
            args: Positional arguments of the task
            kwargs: Keyword arguments of the task
            einfo: Exception info object
        """
        logger.warning(
            f"Task {self.name} [{task_id}] retry",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "exception": str(exc),
                "args": args,
                "kwargs": kwargs,
            },
        )

    def on_success(
        self, retval: Any, task_id: str, args: tuple, kwargs: Dict[str, Any]
    ) -> None:
        """
        Handle successful task completion.
        
        Args:
            retval: Return value of the task
            task_id: Unique identifier of the task
            args: Positional arguments of the task
            kwargs: Keyword arguments of the task
        """
        logger.info(
            f"Task {self.name} [{task_id}] succeeded",
            extra={
                "task_id": task_id,
                "task_name": self.name,
                "result": str(retval)[:200],  # Truncate long results
            },
        )


# Set default task base class
celery_app.Task = CallbackTask


# Signal handlers for application-level events
@task_failure.connect
def handle_task_failure(sender: Any, task_id: str, exception: Exception, **kwargs: Any) -> None:
    """
    Global handler for task failures.
    
    Args:
        sender: Task instance that failed
        task_id: Unique identifier of the failed task
        exception: Exception that caused the failure
        kwargs: Additional context information
    """
    logger.error(
        f"Global task failure handler: {sender.name}",
        extra={
            "task_id": task_id,
            "task_name": sender.name,
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
        },
    )


@task_success.connect
def handle_task_success(sender: Any, result: Any, **kwargs: Any) -> None:
    """
    Global handler for task success.
    
    Args:
        sender: Task instance that succeeded
        result: Return value of the task
        kwargs: Additional context information
    """
    logger.debug(
        f"Task completed successfully: {sender.name}",
        extra={"task_name": sender.name, "result_type": type(result).__name__},
    )


@task_retry.connect
def handle_task_retry(sender: Any, request: Any, reason: str, **kwargs: Any) -> None:
    """
    Global handler for task retries.
    
    Args:
        sender: Task instance being retried
        request: Task request object
        reason: Reason for retry
        kwargs: Additional context information
    """
    logger.warning(
        f"Task retry: {sender.name}",
        extra={
            "task_name": sender.name,
            "task_id": request.id,
            "reason": reason,
            "retries": request.retries,
        },
    )


@worker_ready.connect
def handle_worker_ready(sender: Any, **kwargs: Any) -> None:
    """
    Handler for worker ready signal.
    
    Args:
        sender: Worker instance
        kwargs: Additional context information
    """
    logger.info(
        "Celery worker is ready",
        extra={"hostname": sender.hostname if hasattr(sender, "hostname") else "unknown"},
    )


def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    Get status and result of a task by ID.
    
    Args:
        task_id: Unique identifier of the task
        
    Returns:
        Dictionary containing task status, result, and metadata
    """
    task_result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.successful() else None,
        "traceback": task_result.traceback if task_result.failed() else None,
        "ready": task_result.ready(),
        "successful": task_result.successful(),
        "failed": task_result.failed(),
    }


def revoke_task(task_id: str, terminate: bool = False) -> None:
    """
    Revoke a task by ID.
    
    Args:
        task_id: Unique identifier of the task to revoke
        terminate: If True, terminate the task if it's already running
    """
    celery_app.control.revoke(task_id, terminate=terminate)
    logger.info(f"Task revoked: {task_id}", extra={"terminate": terminate})


def get_active_tasks() -> List[Dict[str, Any]]:
    """
    Get list of currently active tasks across all workers.
    
    Returns:
        List of dictionaries containing active task information
    """
    inspect = celery_app.control.inspect()
    active = inspect.active()
    return active if active else []


def get_scheduled_tasks() -> List[Dict[str, Any]]:
    """
    Get list of scheduled tasks across all workers.
    
    Returns:
        List of dictionaries containing scheduled task information
    """
    inspect = celery_app.control.inspect()
    scheduled = inspect.scheduled()
    return scheduled if scheduled else []


def purge_queue(queue_name: str) -> int:
    """
    Purge all tasks from a specific queue.
    
    Args:
        queue_name: Name of the queue to purge
        
    Returns:
        Number of messages purged
    """
    purged = celery_app.control.purge()
    logger.warning(f"Purged queue: {queue_name}", extra={"messages_purged": purged})
    return purged


# Auto-discover tasks from specified modules
celery_app.autodiscover_tasks(
    [
        "workers.tasks.data_collection",
        "workers.tasks.signal_generation",
        "workers.tasks.position_monitoring",
        "workers.tasks.risk_management",
        "workers.tasks.system_maintenance",
    ],
    force=True,
)

logger.info("Celery application initialized", extra={"app_name": "stockjarvis"})
