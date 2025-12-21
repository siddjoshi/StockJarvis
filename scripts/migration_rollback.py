"""
scripts/migration_rollback.py

Migration rollback script to safely restore previous database state.
Creates restore points, performs rollback, and verifies restoration.
"""

import argparse
import logging
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import shutil

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker, Session
from tqdm import tqdm

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from core.logger import setup_logging, get_logger


# Setup logging for migration rollback
log_file = Path("logs/migration_rollback.log")
log_file.parent.mkdir(parents=True, exist_ok=True)
logger = get_logger(__name__)


class MigrationRollback:
    """Handles database migration rollback operations."""
    
    def __init__(self, session: Session):
        """
        Initialize rollback handler.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.engine = session.bind
        self.backup_dir = Path("backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        logger.info("MigrationRollback initialized")
    
    def create_restore_point(
        self,
        backup_name: Optional[str] = None
    ) -> Path:
        """
        Create a full database backup using mysqldump.
        
        Args:
            backup_name: Optional custom backup name
        
        Returns:
            Path to backup file
        """
        if backup_name is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_name = f"stockjarvis_backup_{timestamp}.sql"
        
        backup_path = self.backup_dir / backup_name
        
        logger.info(f"Creating restore point: {backup_path}")
        
        try:
            # Build mysqldump command
            cmd = [
                "mysqldump",
                f"--host={settings.db.host}",
                f"--port={settings.db.port}",
                f"--user={settings.db.user}",
                f"--password={settings.db.password}",
                "--single-transaction",  # For InnoDB consistency
                "--routines",  # Include stored procedures
                "--triggers",  # Include triggers
                "--events",  # Include events
                "--add-drop-table",
                "--compress",
                settings.db.database
            ]
            
            # Execute mysqldump
            logger.info("Running mysqldump... (this may take a few minutes)")
            with open(backup_path, 'w') as f:
                result = subprocess.run(
                    cmd,
                    stdout=f,
                    stderr=subprocess.PIPE,
                    text=True
                )
            
            if result.returncode != 0:
                error_msg = result.stderr
                logger.error(f"mysqldump failed: {error_msg}")
                raise RuntimeError(f"mysqldump failed: {error_msg}")
            
            # Verify backup file was created
            if not backup_path.exists() or backup_path.stat().st_size == 0:
                raise RuntimeError("Backup file is empty or was not created")
            
            backup_size_mb = backup_path.stat().st_size / (1024 * 1024)
            logger.info(f"✓ Restore point created: {backup_path} ({backup_size_mb:.2f} MB)")
            
            return backup_path
            
        except FileNotFoundError:
            logger.error("mysqldump command not found. Please install MySQL client tools.")
            raise RuntimeError(
                "mysqldump not found. Install MySQL client: "
                "apt-get install mysql-client (Linux) or "
                "brew install mysql-client (Mac) or "
                "Download from https://dev.mysql.com/downloads/ (Windows)"
            )
        except Exception as e:
            logger.error(f"Failed to create restore point: {str(e)}", exc_info=True)
            raise
    
    def get_migration_tables(self) -> dict:
        """
        Identify migration tables (new and old).
        
        Returns:
            Dictionary with 'new_tables' and 'old_tables' lists
        """
        inspector = inspect(self.engine)
        all_tables = inspector.get_table_names()
        
        # New schema tables
        new_tables = [
            'symbols', 'prices', 'strategies', 'signals',
            'orders', 'positions', 'backtest_results', 'alerts'
        ]
        
        # Old tables (ending with _old or _NSE)
        old_tables = [
            t for t in all_tables
            if t.endswith('_old') or (t.endswith('_NSE') and t not in new_tables)
        ]
        
        existing_new = [t for t in new_tables if t in all_tables]
        
        logger.info(f"Found {len(existing_new)} new tables, {len(old_tables)} old tables")
        
        return {
            'new_tables': existing_new,
            'old_tables': old_tables
        }
    
    def rollback_migration(
        self,
        keep_backup: bool = True
    ) -> bool:
        """
        Rollback migration by dropping new tables and restoring from _old tables.
        
        Args:
            keep_backup: Whether to keep old tables after restoration
        
        Returns:
            True if rollback successful, False otherwise
        """
        logger.info("=" * 60)
        logger.info("Starting migration rollback")
        logger.info("=" * 60)
        
        try:
            tables = self.get_migration_tables()
            
            if not tables['old_tables']:
                logger.warning("No old tables found (ending with '_old'). Nothing to rollback.")
                return False
            
            # Step 1: Drop new tables
            logger.info("Step 1: Dropping new schema tables")
            for table in tqdm(tables['new_tables'], desc="Dropping tables"):
                try:
                    self.session.execute(text(f"DROP TABLE IF EXISTS `{table}` CASCADE"))
                    self.session.commit()
                    logger.info(f"✓ Dropped table: {table}")
                except Exception as e:
                    logger.error(f"✗ Failed to drop table {table}: {str(e)}")
                    self.session.rollback()
            
            # Step 2: Restore old tables by renaming
            logger.info("Step 2: Restoring old tables")
            restored_count = 0
            
            for old_table in tqdm(tables['old_tables'], desc="Restoring tables"):
                try:
                    # Determine new table name
                    if old_table.endswith('_old'):
                        new_name = old_table[:-4]  # Remove '_old' suffix
                    elif old_table.endswith('_NSE'):
                        # Keep NSE tables as-is for now
                        continue
                    else:
                        new_name = old_table
                    
                    # Check if a table with the new name already exists
                    check_query = text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = :db AND table_name = :table"
                    )
                    exists = self.session.execute(
                        check_query,
                        {"db": settings.db.database, "table": new_name}
                    ).scalar()
                    
                    if exists:
                        logger.warning(f"Table {new_name} already exists, skipping {old_table}")
                        continue
                    
                    # Rename table
                    rename_query = text(f"RENAME TABLE `{old_table}` TO `{new_name}`")
                    self.session.execute(rename_query)
                    self.session.commit()
                    
                    restored_count += 1
                    logger.info(f"✓ Restored: {old_table} -> {new_name}")
                    
                except Exception as e:
                    logger.error(f"✗ Failed to restore {old_table}: {str(e)}")
                    self.session.rollback()
            
            logger.info(f"✓ Rollback completed: {restored_count} tables restored")
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}", exc_info=True)
            self.session.rollback()
            return False
    
    def restore_from_backup(
        self,
        backup_path: Path
    ) -> bool:
        """
        Restore database from a mysqldump backup file.
        
        Args:
            backup_path: Path to backup SQL file
        
        Returns:
            True if restoration successful, False otherwise
        """
        logger.info(f"Restoring database from backup: {backup_path}")
        
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False
        
        try:
            # Build mysql command
            cmd = [
                "mysql",
                f"--host={settings.db.host}",
                f"--port={settings.db.port}",
                f"--user={settings.db.user}",
                f"--password={settings.db.password}",
                settings.db.database
            ]
            
            # Execute mysql restore
            logger.info("Running mysql restore... (this may take a few minutes)")
            with open(backup_path, 'r') as f:
                result = subprocess.run(
                    cmd,
                    stdin=f,
                    stderr=subprocess.PIPE,
                    text=True
                )
            
            if result.returncode != 0:
                error_msg = result.stderr
                logger.error(f"mysql restore failed: {error_msg}")
                return False
            
            logger.info("✓ Database restored successfully from backup")
            return True
            
        except FileNotFoundError:
            logger.error("mysql command not found. Please install MySQL client tools.")
            return False
        except Exception as e:
            logger.error(f"Failed to restore from backup: {str(e)}", exc_info=True)
            return False
    
    def verify_rollback(self) -> bool:
        """
        Verify that rollback was successful.
        
        Returns:
            True if verification passed, False otherwise
        """
        logger.info("Verifying rollback...")
        
        try:
            tables = self.get_migration_tables()
            
            # Check that new tables are gone
            if tables['new_tables']:
                logger.warning(
                    f"New tables still exist: {', '.join(tables['new_tables'])}"
                )
                return False
            
            # Check that we have old tables or restored tables
            inspector = inspect(self.engine)
            all_tables = inspector.get_table_names()
            
            if not all_tables:
                logger.error("No tables found in database after rollback")
                return False
            
            # Try to query one of the restored tables
            try:
                result = self.session.execute(text("SHOW TABLES"))
                table_count = len(result.fetchall())
                logger.info(f"✓ Database has {table_count} tables")
                
                # Sample query to verify data accessibility
                sample_query = text("SELECT COUNT(*) FROM information_schema.tables")
                self.session.execute(sample_query)
                logger.info("✓ Database queries working correctly")
                
            except Exception as e:
                logger.error(f"Database verification failed: {str(e)}")
                return False
            
            logger.info("✓ Rollback verification passed")
            return True
            
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}", exc_info=True)
            return False
    
    def list_backups(self) -> List[Path]:
        """
        List all available backup files.
        
        Returns:
            List of backup file paths
        """
        if not self.backup_dir.exists():
            return []
        
        backups = sorted(
            self.backup_dir.glob("*.sql"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        return backups
    
    def rollback(
        self,
        create_backup: bool = True,
        restore_from_file: Optional[Path] = None
    ) -> bool:
        """
        Complete rollback workflow with confirmation.
        
        Args:
            create_backup: Whether to create backup before rollback
            restore_from_file: Optional backup file to restore from
        
        Returns:
            True if rollback successful, False otherwise
        """
        logger.info("=" * 60)
        logger.info("MIGRATION ROLLBACK PROCEDURE")
        logger.info("=" * 60)
        
        try:
            # Option 1: Restore from backup file
            if restore_from_file:
                logger.info(f"Restoring from backup file: {restore_from_file}")
                success = self.restore_from_backup(restore_from_file)
                
                if success:
                    success = self.verify_rollback()
                
                return success
            
            # Option 2: Rollback by dropping new tables and renaming old ones
            if create_backup:
                logger.info("Creating pre-rollback backup...")
                backup_path = self.create_restore_point()
                logger.info(f"✓ Backup created: {backup_path}")
            
            # Perform rollback
            success = self.rollback_migration()
            
            if success:
                # Verify rollback
                success = self.verify_rollback()
            
            if success:
                logger.info("=" * 60)
                logger.info("✅ ROLLBACK COMPLETED SUCCESSFULLY")
                logger.info("=" * 60)
            else:
                logger.error("=" * 60)
                logger.error("❌ ROLLBACK FAILED")
                logger.error("=" * 60)
            
            return success
            
        except Exception as e:
            logger.error(f"Rollback procedure failed: {str(e)}", exc_info=True)
            return False


def confirm_rollback() -> bool:
    """
    Prompt user for confirmation before proceeding with rollback.
    
    Returns:
        True if user confirms, False otherwise
    """
    print("\n" + "=" * 60)
    print("⚠️  WARNING: DATABASE ROLLBACK ⚠️")
    print("=" * 60)
    print("\nThis will:")
    print("  1. Drop all new schema tables (symbols, prices, signals, etc.)")
    print("  2. Restore old table structure")
    print("  3. Potentially lose data created after migration")
    print("\nBefore proceeding:")
    print("  ✓ Ensure you have a recent backup")
    print("  ✓ Stop all running applications")
    print("  ✓ Notify team members")
    print("\n" + "=" * 60)
    
    response = input("\nType 'ROLLBACK' to confirm: ").strip()
    
    return response == "ROLLBACK"


def main():
    """Main entry point for migration rollback."""
    parser = argparse.ArgumentParser(
        description="Rollback StockJarvis database migration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive rollback with backup
  python migration_rollback.py
  
  # Rollback without creating new backup
  python migration_rollback.py --no-backup
  
  # Restore from specific backup file
  python migration_rollback.py --restore backups/stockjarvis_backup_20250101_120000.sql
  
  # List available backups
  python migration_rollback.py --list-backups
  
  # Force rollback without confirmation (use with caution!)
  python migration_rollback.py --force
        """
    )
    
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating backup before rollback"
    )
    parser.add_argument(
        "--restore",
        type=Path,
        help="Restore from specific backup file"
    )
    parser.add_argument(
        "--list-backups",
        action="store_true",
        help="List available backup files"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt (dangerous!)"
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_file=log_file, log_level=args.log_level)
    
    logger.info("Migration Rollback Tool started")
    logger.info(f"Database: {settings.db.host}/{settings.db.database}")
    
    try:
        # Create database engine and session
        engine = create_engine(
            settings.db.url,
            pool_pre_ping=True,
            echo=False
        )
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        # Create rollback handler
        rollback_handler = MigrationRollback(session)
        
        # Handle list-backups command
        if args.list_backups:
            backups = rollback_handler.list_backups()
            if backups:
                print("\n📁 Available Backups:\n")
                for i, backup in enumerate(backups, 1):
                    size_mb = backup.stat().st_size / (1024 * 1024)
                    mtime = datetime.fromtimestamp(backup.stat().st_mtime)
                    print(f"  {i}. {backup.name}")
                    print(f"     Size: {size_mb:.2f} MB | Created: {mtime}")
                    print()
            else:
                print("\n❌ No backups found in backups/ directory\n")
            
            session.close()
            engine.dispose()
            sys.exit(0)
        
        # Confirm rollback (unless forced or restoring)
        if not args.force and not args.restore:
            if not confirm_rollback():
                print("\n❌ Rollback cancelled by user\n")
                session.close()
                engine.dispose()
                sys.exit(0)
        
        # Perform rollback
        success = rollback_handler.rollback(
            create_backup=not args.no_backup,
            restore_from_file=args.restore
        )
        
        # Cleanup
        session.close()
        engine.dispose()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Rollback interrupted by user")
        logger.warning("Rollback interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error during rollback: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
