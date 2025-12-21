# workers/__init__.py
"""
Celery workers package for StockJarvis.
Handles asynchronous task processing for data collection, signal generation,
position monitoring, and system maintenance.
"""

from workers.celery_app import celery_app

__all__ = ["celery_app"]
