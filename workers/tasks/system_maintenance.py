# workers/tasks/system_maintenance.py
"""
Celery tasks for system maintenance.
Handles database cleanup, backups, health checks, and daily reporting.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import subprocess
import shutil
import psutil
import os
from pathlib import Path

from workers.celery_app import celery_app
from core.logger import get_logger
from data.repository import repository
from data.models import TradingMode, OrderAction, OrderStatus
from config import settings

logger = get_logger(__name__)


@celery_app.task(bind=True, name="workers.tasks.system_maintenance.cleanup_old_data")
def cleanup_old_data(self, table: str, days: int = 365) -> Dict[str, Any]:
    """
    Archive or delete old records from specified database tables.
    Helps maintain database performance by removing historical data older than specified days.
    
    Args:
        table: Table name to clean (prices, signals, trades, orders, alerts)
        days: Number of days to retain (default: 365)
    
    Returns:
        Dictionary with task results and cleanup statistics
    
    Example:
        >>> from workers.tasks.system_maintenance import cleanup_old_data
        >>> # Clean signals older than 90 days
        >>> result = cleanup_old_data.delay(table='signals', days=90)
        >>> # Clean old prices (keep 2 years)
        >>> result = cleanup_old_data.delay(table='prices', days=730)
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting data cleanup task for table: {table}, days: {days}")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'table': table,
        'retention_days': days,
        'records_deleted': 0,
        'records_archived': 0,
        'space_freed_mb': 0.0,
        'errors': [],
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 0,
                'status': f'Cleaning up old data from {table}...'
            }
        )
        
        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        logger.info(f"Cleaning records older than {cutoff_date.date()}")
        
        # Valid tables for cleanup
        valid_tables = ['prices', 'signals', 'trades', 'orders', 'alerts']
        
        if table not in valid_tables:
            logger.error(f"Invalid table name: {table}. Valid options: {valid_tables}")
            stats['status'] = 'failed'
            stats['error'] = f"Invalid table name. Valid options: {valid_tables}"
            return stats
        
        with repository.get_session() as session:
            # Import models
            from data.models import Price, Signal, Trade, Order, Alert
            
            # Map table names to models
            table_models = {
                'prices': Price,
                'signals': Signal,
                'trades': Trade,
                'orders': Order,
                'alerts': Alert
            }
            
            model = table_models[table]
            
            # Count records to delete
            logger.info(f"Counting old records in {table}...")
            
            if table == 'prices':
                old_records = session.query(model).filter(
                    model.timestamp < cutoff_date
                ).count()
            elif table == 'alerts':
                old_records = session.query(model).filter(
                    model.created_at < cutoff_date
                ).count()
            else:
                # signals, trades, orders have created_at
                old_records = session.query(model).filter(
                    model.created_at < cutoff_date
                ).count()
            
            logger.info(f"Found {old_records} old records to delete")
            
            if old_records == 0:
                logger.info("No old records to delete")
                stats['status'] = 'completed'
                stats['end_time'] = datetime.utcnow().isoformat()
                return stats
            
            # Optional: Archive before deleting (for critical tables)
            if table in ['trades', 'orders'] and settings.db.archive_before_delete:
                logger.info(f"Archiving {old_records} records before deletion...")
                
                # TODO: Implement archiving to separate archive table or file
                # Example:
                """
                archive_table = f"{table}_archive"
                
                if table == 'prices':
                    archive_records = session.query(model).filter(
                        model.timestamp < cutoff_date
                    ).all()
                else:
                    archive_records = session.query(model).filter(
                        model.created_at < cutoff_date
                    ).all()
                
                # Insert into archive table
                # This is a placeholder - implement based on your archiving strategy
                stats['records_archived'] = len(archive_records)
                """
                
                logger.warning(
                    f"Archiving not fully implemented for {table}. "
                    f"Configure archive strategy in settings if needed."
                )
            
            # Delete old records in batches
            batch_size = 1000
            deleted_count = 0
            
            logger.info(f"Deleting old records in batches of {batch_size}...")
            
            while True:
                # Delete batch
                if table == 'prices':
                    batch = session.query(model).filter(
                        model.timestamp < cutoff_date
                    ).limit(batch_size).all()
                elif table == 'alerts':
                    batch = session.query(model).filter(
                        model.created_at < cutoff_date
                    ).limit(batch_size).all()
                else:
                    batch = session.query(model).filter(
                        model.created_at < cutoff_date
                    ).limit(batch_size).all()
                
                if not batch:
                    break
                
                for record in batch:
                    session.delete(record)
                
                session.commit()
                deleted_count += len(batch)
                
                # Update progress
                progress_pct = (deleted_count / old_records) * 100
                self.update_state(
                    state='PROGRESS',
                    meta={
                        'current': deleted_count,
                        'total': old_records,
                        'status': f'Deleted {deleted_count}/{old_records} records...',
                        'progress_pct': progress_pct
                    }
                )
                
                logger.info(f"Deleted {deleted_count}/{old_records} records ({progress_pct:.1f}%)")
                
                if deleted_count >= old_records:
                    break
            
            stats['records_deleted'] = deleted_count
            
            # Optimize table after deletion
            logger.info(f"Optimizing {table} table...")
            
            try:
                # MySQL OPTIMIZE TABLE
                session.execute(f"OPTIMIZE TABLE {table}")
                session.commit()
                logger.info(f"Table {table} optimized successfully")
            except Exception as e:
                logger.warning(f"Table optimization failed: {e}")
                stats['errors'].append(f"Optimization failed: {str(e)}")
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Data cleanup completed: "
            f"Deleted {stats['records_deleted']} records from {table}"
        )
        
        # Create alert if significant cleanup
        if stats['records_deleted'] > 1000:
            repository.add_alert(
                alert_type='maintenance',
                title=f'Data Cleanup Completed - {table}',
                message=f"Deleted {stats['records_deleted']} records older than {days} days",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in cleanup_old_data task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='maintenance_failed',
            title='Data Cleanup Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.system_maintenance.backup_database")
def backup_database(self) -> Dict[str, Any]:
    """
    Create MySQL database backup using mysqldump.
    Saves backup to configured backup directory with timestamp.
    
    Returns:
        Dictionary with task results and backup information
    
    Example:
        >>> from workers.tasks.system_maintenance import backup_database
        >>> result = backup_database.delay()
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting database backup task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'backup_file': None,
        'backup_size_mb': 0.0,
        'duration_seconds': 0.0,
        'compression_used': False,
        'errors': [],
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 0,
                'status': 'Creating database backup...'
            }
        )
        
        # Create backup directory if it doesn't exist
        backup_dir = Path(settings.app.backup_dir) if hasattr(settings.app, 'backup_dir') else Path("./backups")
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"stockjarvis_backup_{timestamp}.sql"
        backup_path = backup_dir / backup_filename
        
        logger.info(f"Backup file: {backup_path}")
        
        # Parse database URL
        # Format: mysql+mysqlconnector://user:password@host:port/database
        db_url = settings.db.url
        
        # Extract database credentials
        # This is a simplified parser - use proper URL parsing in production
        if "mysql" not in db_url:
            logger.error(f"Unsupported database type. Only MySQL is supported for mysqldump.")
            stats['status'] = 'failed'
            stats['error'] = 'Unsupported database type'
            return stats
        
        # Parse URL components
        import urllib.parse
        parsed = urllib.parse.urlparse(db_url)
        
        db_user = parsed.username or "root"
        db_password = parsed.password or ""
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 3306
        db_name = parsed.path.strip("/")
        
        if not db_name:
            logger.error("Database name not found in connection URL")
            stats['status'] = 'failed'
            stats['error'] = 'Database name not found'
            return stats
        
        logger.info(f"Backing up database: {db_name} from {db_host}:{db_port}")
        
        # Build mysqldump command
        mysqldump_cmd = [
            "mysqldump",
            f"--host={db_host}",
            f"--port={db_port}",
            f"--user={db_user}",
            "--single-transaction",  # For InnoDB consistency
            "--routines",  # Include stored procedures
            "--triggers",  # Include triggers
            "--events",  # Include events
            "--quick",  # Fast export
            "--result-file=" + str(backup_path),
            db_name
        ]
        
        # Add password if provided
        if db_password:
            mysqldump_cmd.insert(4, f"--password={db_password}")
        
        logger.info("Executing mysqldump...")
        
        # Execute mysqldump
        start_time = datetime.utcnow()
        
        try:
            result = subprocess.run(
                mysqldump_cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                logger.error(f"mysqldump failed: {result.stderr}")
                stats['status'] = 'failed'
                stats['error'] = f"mysqldump error: {result.stderr}"
                return stats
            
        except subprocess.TimeoutExpired:
            logger.error("mysqldump timeout (1 hour)")
            stats['status'] = 'failed'
            stats['error'] = 'Backup timeout'
            return stats
        
        except FileNotFoundError:
            logger.error("mysqldump command not found. Ensure MySQL client is installed.")
            stats['status'] = 'failed'
            stats['error'] = 'mysqldump not found - install MySQL client'
            return stats
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        # Check if backup file was created
        if not backup_path.exists():
            logger.error("Backup file was not created")
            stats['status'] = 'failed'
            stats['error'] = 'Backup file not created'
            return stats
        
        # Get backup file size
        backup_size = backup_path.stat().st_size
        backup_size_mb = backup_size / (1024 * 1024)
        
        stats['backup_file'] = str(backup_path)
        stats['backup_size_mb'] = round(backup_size_mb, 2)
        stats['duration_seconds'] = round(duration, 2)
        
        logger.info(
            f"Backup created successfully: {backup_size_mb:.2f} MB in {duration:.1f}s"
        )
        
        # Optional: Compress backup
        compress_backups = getattr(settings.db, 'compress_backups', True)
        
        if compress_backups:
            logger.info("Compressing backup file...")
            
            try:
                import gzip
                
                compressed_path = backup_path.with_suffix('.sql.gz')
                
                with open(backup_path, 'rb') as f_in:
                    with gzip.open(compressed_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                
                # Remove uncompressed file
                backup_path.unlink()
                
                compressed_size = compressed_path.stat().st_size
                compressed_size_mb = compressed_size / (1024 * 1024)
                
                compression_ratio = (1 - compressed_size / backup_size) * 100
                
                stats['backup_file'] = str(compressed_path)
                stats['backup_size_mb'] = round(compressed_size_mb, 2)
                stats['compression_used'] = True
                stats['compression_ratio_pct'] = round(compression_ratio, 2)
                
                logger.info(
                    f"Backup compressed: {compressed_size_mb:.2f} MB "
                    f"({compression_ratio:.1f}% reduction)"
                )
                
            except Exception as e:
                logger.warning(f"Compression failed: {e}")
                stats['errors'].append(f"Compression failed: {str(e)}")
        
        # Clean up old backups (keep last N backups)
        max_backups = getattr(settings.db, 'max_backups', 7)
        
        logger.info(f"Cleaning up old backups (keeping last {max_backups})...")
        
        try:
            # Get all backup files sorted by modification time
            backup_files = sorted(
                backup_dir.glob("stockjarvis_backup_*.sql*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            
            # Delete old backups
            deleted_backups = 0
            for old_backup in backup_files[max_backups:]:
                old_backup.unlink()
                deleted_backups += 1
                logger.info(f"Deleted old backup: {old_backup.name}")
            
            if deleted_backups > 0:
                stats['old_backups_deleted'] = deleted_backups
                logger.info(f"Deleted {deleted_backups} old backups")
        
        except Exception as e:
            logger.warning(f"Old backup cleanup failed: {e}")
            stats['errors'].append(f"Old backup cleanup failed: {str(e)}")
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Database backup completed: {stats['backup_file']} ({stats['backup_size_mb']} MB)"
        )
        
        # Create alert
        repository.add_alert(
            alert_type='maintenance',
            title='Database Backup Completed',
            message=f"Backup created: {backup_filename} ({stats['backup_size_mb']} MB)",
            metadata=stats
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in backup_database task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='backup_failed',
            title='Database Backup Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.system_maintenance.health_check")
def health_check(self) -> Dict[str, Any]:
    """
    Check system health including database connection, Redis, disk space, and memory.
    
    Returns:
        Dictionary with health check results
    
    Example:
        >>> from workers.tasks.system_maintenance import health_check
        >>> result = health_check.delay()
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting system health check task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'overall_health': 'healthy',
        'checks_passed': 0,
        'checks_failed': 0,
        'checks': {},
        'warnings': [],
        'errors': [],
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 4,
                'status': 'Running health checks...'
            }
        )
        
        # Check 1: Database connection
        logger.info("Checking database connection...")
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 1,
                'total': 4,
                'status': 'Checking database...',
                'progress_pct': 25
            }
        )
        
        try:
            with repository.get_session() as session:
                # Test query
                result = session.execute("SELECT 1").fetchone()
                
                if result and result[0] == 1:
                    stats['checks']['database'] = {
                        'status': 'healthy',
                        'message': 'Database connection OK'
                    }
                    stats['checks_passed'] += 1
                    logger.info("Database check: PASSED")
                else:
                    raise Exception("Test query returned unexpected result")
        
        except Exception as e:
            stats['checks']['database'] = {
                'status': 'unhealthy',
                'message': f'Database connection failed: {str(e)}'
            }
            stats['checks_failed'] += 1
            stats['errors'].append(f"Database: {str(e)}")
            logger.error(f"Database check: FAILED - {e}")
        
        # Check 2: Redis connection (for Celery broker/backend)
        logger.info("Checking Redis connection...")
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 2,
                'total': 4,
                'status': 'Checking Redis...',
                'progress_pct': 50
            }
        )
        
        try:
            import redis
            
            # Parse Redis URL from Celery config
            redis_url = settings.redis.url if hasattr(settings, 'redis') else "redis://localhost:6379/0"
            
            r = redis.from_url(redis_url, socket_connect_timeout=5)
            r.ping()
            
            # Get Redis info
            redis_info = r.info()
            used_memory_mb = redis_info.get('used_memory', 0) / (1024 * 1024)
            
            stats['checks']['redis'] = {
                'status': 'healthy',
                'message': 'Redis connection OK',
                'used_memory_mb': round(used_memory_mb, 2),
                'connected_clients': redis_info.get('connected_clients', 0)
            }
            stats['checks_passed'] += 1
            logger.info(f"Redis check: PASSED (Memory: {used_memory_mb:.1f} MB)")
        
        except Exception as e:
            stats['checks']['redis'] = {
                'status': 'unhealthy',
                'message': f'Redis connection failed: {str(e)}'
            }
            stats['checks_failed'] += 1
            stats['errors'].append(f"Redis: {str(e)}")
            logger.error(f"Redis check: FAILED - {e}")
        
        # Check 3: Disk space
        logger.info("Checking disk space...")
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 3,
                'total': 4,
                'status': 'Checking disk space...',
                'progress_pct': 75
            }
        )
        
        try:
            # Get disk usage for current drive
            disk_usage = psutil.disk_usage('/')
            
            free_gb = disk_usage.free / (1024 ** 3)
            used_pct = disk_usage.percent
            
            # Warning threshold: 90% used
            # Critical threshold: 95% used
            
            if used_pct >= 95:
                disk_status = 'critical'
                disk_message = f'Disk space critical: {used_pct:.1f}% used, {free_gb:.1f} GB free'
                stats['errors'].append(disk_message)
                stats['checks_failed'] += 1
            elif used_pct >= 90:
                disk_status = 'warning'
                disk_message = f'Disk space low: {used_pct:.1f}% used, {free_gb:.1f} GB free'
                stats['warnings'].append(disk_message)
                stats['checks_passed'] += 1
            else:
                disk_status = 'healthy'
                disk_message = f'Disk space OK: {used_pct:.1f}% used, {free_gb:.1f} GB free'
                stats['checks_passed'] += 1
            
            stats['checks']['disk_space'] = {
                'status': disk_status,
                'message': disk_message,
                'used_pct': round(used_pct, 2),
                'free_gb': round(free_gb, 2),
                'total_gb': round(disk_usage.total / (1024 ** 3), 2)
            }
            
            logger.info(f"Disk space check: {disk_status.upper()} ({used_pct:.1f}% used)")
        
        except Exception as e:
            stats['checks']['disk_space'] = {
                'status': 'unknown',
                'message': f'Disk space check failed: {str(e)}'
            }
            stats['errors'].append(f"Disk: {str(e)}")
            logger.error(f"Disk space check: FAILED - {e}")
        
        # Check 4: Memory usage
        logger.info("Checking memory usage...")
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 4,
                'total': 4,
                'status': 'Checking memory...',
                'progress_pct': 100
            }
        )
        
        try:
            # Get memory usage
            memory = psutil.virtual_memory()
            
            used_pct = memory.percent
            available_gb = memory.available / (1024 ** 3)
            
            # Warning threshold: 85% used
            # Critical threshold: 95% used
            
            if used_pct >= 95:
                memory_status = 'critical'
                memory_message = f'Memory critical: {used_pct:.1f}% used, {available_gb:.1f} GB available'
                stats['errors'].append(memory_message)
                stats['checks_failed'] += 1
            elif used_pct >= 85:
                memory_status = 'warning'
                memory_message = f'Memory high: {used_pct:.1f}% used, {available_gb:.1f} GB available'
                stats['warnings'].append(memory_message)
                stats['checks_passed'] += 1
            else:
                memory_status = 'healthy'
                memory_message = f'Memory OK: {used_pct:.1f}% used, {available_gb:.1f} GB available'
                stats['checks_passed'] += 1
            
            stats['checks']['memory'] = {
                'status': memory_status,
                'message': memory_message,
                'used_pct': round(used_pct, 2),
                'available_gb': round(available_gb, 2),
                'total_gb': round(memory.total / (1024 ** 3), 2)
            }
            
            logger.info(f"Memory check: {memory_status.upper()} ({used_pct:.1f}% used)")
        
        except Exception as e:
            stats['checks']['memory'] = {
                'status': 'unknown',
                'message': f'Memory check failed: {str(e)}'
            }
            stats['errors'].append(f"Memory: {str(e)}")
            logger.error(f"Memory check: FAILED - {e}")
        
        # Determine overall health
        if stats['checks_failed'] > 0:
            stats['overall_health'] = 'unhealthy'
        elif stats['warnings']:
            stats['overall_health'] = 'degraded'
        else:
            stats['overall_health'] = 'healthy'
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Health check completed: {stats['overall_health'].upper()} - "
            f"{stats['checks_passed']} passed, {stats['checks_failed']} failed"
        )
        
        # Create alert if unhealthy
        if stats['overall_health'] == 'unhealthy':
            repository.add_alert(
                alert_type='health_check',
                title='System Health Check - Issues Found',
                message=f"System health: {stats['overall_health']} - {stats['checks_failed']} checks failed",
                metadata=stats
            )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in health_check task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['overall_health'] = 'unknown'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        return stats


@celery_app.task(bind=True, name="workers.tasks.system_maintenance.generate_daily_report")
def generate_daily_report(self, date: Optional[str] = None) -> Dict[str, Any]:
    """
    Generate daily trading report with P&L, signals, trades, and performance metrics.
    
    Args:
        date: Date to generate report for (YYYY-MM-DD format, default: today)
    
    Returns:
        Dictionary with report data and statistics
    
    Example:
        >>> from workers.tasks.system_maintenance import generate_daily_report
        >>> # Generate report for today
        >>> result = generate_daily_report.delay()
        >>> # Generate report for specific date
        >>> result = generate_daily_report.delay(date='2025-12-19')
        >>> print(result.get())
    """
    task_id = self.request.id
    logger.info(f"[{task_id}] Starting daily report generation task")
    
    # Initialize stats
    stats = {
        'task_id': task_id,
        'start_time': datetime.utcnow().isoformat(),
        'report_date': date,
        'report': {},
        'status': 'in_progress'
    }
    
    try:
        # Update task state
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 0,
                'total': 0,
                'status': 'Generating daily report...'
            }
        )
        
        # Parse report date
        if date:
            try:
                report_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                logger.error(f"Invalid date format: {date}. Use YYYY-MM-DD")
                stats['status'] = 'failed'
                stats['error'] = 'Invalid date format'
                return stats
        else:
            report_date = datetime.utcnow()
        
        # Set date range for report (full day)
        start_of_day = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        
        stats['report_date'] = start_of_day.date().isoformat()
        
        logger.info(f"Generating report for {start_of_day.date()}")
        
        with repository.get_session() as session:
            from data.models import Signal, Trade, Order, Position
            from sqlalchemy import func
            
            report = {
                'date': start_of_day.date().isoformat(),
                'signals': {},
                'trades': {},
                'orders': {},
                'positions': {},
                'pnl': {},
                'performance': {}
            }
            
            # Signals generated today
            logger.info("Analyzing signals...")
            
            signals = session.query(Signal).filter(
                Signal.created_at >= start_of_day,
                Signal.created_at < end_of_day
            ).all()
            
            report['signals'] = {
                'total': len(signals),
                'buy': sum(1 for s in signals if s.action == OrderAction.BUY),
                'sell': sum(1 for s in signals if s.action == OrderAction.SELL),
                'by_strategy': {}
            }
            
            # Group by strategy
            for signal in signals:
                strategy = signal.strategy_name
                if strategy not in report['signals']['by_strategy']:
                    report['signals']['by_strategy'][strategy] = 0
                report['signals']['by_strategy'][strategy] += 1
            
            # Trades executed today
            logger.info("Analyzing trades...")
            
            trades = session.query(Trade).filter(
                Trade.created_at >= start_of_day,
                Trade.created_at < end_of_day,
                Trade.trading_mode == TradingMode.LIVE
            ).all()
            
            report['trades'] = {
                'total': len(trades),
                'buy': sum(1 for t in trades if t.action == OrderAction.BUY),
                'sell': sum(1 for t in trades if t.action == OrderAction.SELL),
                'volume': sum(t.quantity for t in trades),
                'value': sum(t.quantity * t.price for t in trades)
            }
            
            # Orders today
            logger.info("Analyzing orders...")
            
            orders = session.query(Order).filter(
                Order.created_at >= start_of_day,
                Order.created_at < end_of_day,
                Order.trading_mode == TradingMode.LIVE
            ).all()
            
            report['orders'] = {
                'total': len(orders),
                'completed': sum(1 for o in orders if o.status == OrderStatus.COMPLETED),
                'pending': sum(1 for o in orders if o.status == OrderStatus.PENDING),
                'cancelled': sum(1 for o in orders if o.status == OrderStatus.CANCELLED),
                'failed': sum(1 for o in orders if o.status == OrderStatus.FAILED)
            }
            
            # Positions closed today
            logger.info("Analyzing closed positions...")
            
            closed_positions = session.query(Position).filter(
                Position.exit_time >= start_of_day,
                Position.exit_time < end_of_day,
                Position.is_open == False,
                Position.trading_mode == TradingMode.LIVE
            ).all()
            
            # Calculate P&L for closed positions
            total_realized_pnl = sum(p.realized_pnl for p in closed_positions)
            winning_trades = [p for p in closed_positions if p.realized_pnl > 0]
            losing_trades = [p for p in closed_positions if p.realized_pnl < 0]
            
            report['positions'] = {
                'closed': len(closed_positions),
                'winning': len(winning_trades),
                'losing': len(losing_trades),
                'breakeven': len(closed_positions) - len(winning_trades) - len(losing_trades)
            }
            
            report['pnl'] = {
                'realized_pnl': round(total_realized_pnl, 2),
                'avg_win': round(sum(p.realized_pnl for p in winning_trades) / len(winning_trades), 2) if winning_trades else 0,
                'avg_loss': round(sum(p.realized_pnl for p in losing_trades) / len(losing_trades), 2) if losing_trades else 0,
                'largest_win': round(max((p.realized_pnl for p in winning_trades), default=0), 2),
                'largest_loss': round(min((p.realized_pnl for p in losing_trades), default=0), 2)
            }
            
            # Current open positions
            logger.info("Analyzing open positions...")
            
            open_positions = session.query(Position).filter(
                Position.is_open == True,
                Position.trading_mode == TradingMode.LIVE
            ).all()
            
            total_unrealized_pnl = sum(p.unrealized_pnl for p in open_positions)
            
            report['positions']['open'] = len(open_positions)
            report['pnl']['unrealized_pnl'] = round(total_unrealized_pnl, 2)
            report['pnl']['total_pnl'] = round(total_realized_pnl + total_unrealized_pnl, 2)
            
            # Performance metrics
            win_rate = (len(winning_trades) / len(closed_positions)) if closed_positions else 0.0
            
            profit_factor = 0.0
            if losing_trades:
                total_wins = sum(p.realized_pnl for p in winning_trades)
                total_losses = abs(sum(p.realized_pnl for p in losing_trades))
                profit_factor = total_wins / total_losses if total_losses > 0 else 0.0
            
            report['performance'] = {
                'win_rate': round(win_rate * 100, 2),
                'profit_factor': round(profit_factor, 2),
                'avg_trade_pnl': round(total_realized_pnl / len(closed_positions), 2) if closed_positions else 0,
                'total_trades': len(closed_positions)
            }
            
            stats['report'] = report
        
        # Task completed
        stats['status'] = 'completed'
        stats['end_time'] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Daily report generated: {report['trades']['total']} trades, "
            f"{report['positions']['closed']} positions closed, "
            f"P&L: ${report['pnl']['total_pnl']:.2f}"
        )
        
        # Create alert with daily summary
        repository.add_alert(
            alert_type='daily_report',
            title=f"Daily Trading Report - {stats['report_date']}",
            message=f"Trades: {report['trades']['total']}, "
                    f"Closed Positions: {report['positions']['closed']}, "
                    f"P&L: ${report['pnl']['total_pnl']:.2f}, "
                    f"Win Rate: {report['performance']['win_rate']:.1f}%",
            metadata=stats
        )
        
        return stats
        
    except Exception as e:
        logger.error(f"Critical error in generate_daily_report task: {e}", exc_info=True)
        stats['status'] = 'failed'
        stats['error'] = str(e)
        stats['end_time'] = datetime.utcnow().isoformat()
        
        repository.add_alert(
            alert_type='daily_report_failed',
            title='Daily Report Generation Failed',
            message=f"Task failed with error: {str(e)}",
            metadata=stats
        )
        
        return stats
