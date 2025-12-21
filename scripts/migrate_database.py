# scripts/migrate_database.py
"""
Database migration script to migrate from legacy per-stock tables to normalized schema.

This script performs a 5-phase migration:
1. Analyze old schema (discover tables, count records)
2. Map tables (old→new table mappings)
3. Migrate data (batch transfer with progress tracking)
4. Validate migration (integrity checks)
5. Archive old tables (rename with _old suffix)
"""

import sys
import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from datetime import datetime
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import (
    create_engine, MetaData, Table, text, inspect,
    Integer, String, Float, DateTime, Date, Boolean
)
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError
from tqdm import tqdm

from config.settings import get_settings
from core.logger import get_logger

# Constants
BATCH_SIZE = 10000
LOG_FILE = "migration.log"

# Setup logging
logger = get_logger(__name__)
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger.addHandler(file_handler)


@dataclass
class TableMapping:
    """Mapping configuration for old table to new schema."""
    old_table: str
    new_table: str
    symbol: Optional[str] = None
    column_mappings: Dict[str, str] = field(default_factory=dict)
    record_count: int = 0


@dataclass
class MigrationStats:
    """Statistics for migration process."""
    total_tables: int = 0
    processed_tables: int = 0
    total_records: int = 0
    migrated_records: int = 0
    failed_records: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class DatabaseMigrator:
    """Main database migration orchestrator."""

    def __init__(self, dry_run: bool = False, parallel: bool = False):
        """
        Initialize the database migrator.

        Args:
            dry_run: If True, perform analysis only without actual migration
            parallel: If True, use parallel processing for migration
        """
        self.settings = get_settings()
        self.dry_run = dry_run
        self.parallel = parallel
        self.stats = MigrationStats()
        
        # Create database engines
        self.engine = create_engine(
            self.settings.database_url,
            pool_pre_ping=True,
            pool_size=20 if parallel else 5,
            max_overflow=40 if parallel else 10
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.metadata = MetaData()
        
        # Storage for mappings
        self.table_mappings: List[TableMapping] = []
        self.symbol_ids: Dict[str, int] = {}
        
        logger.info(f"DatabaseMigrator initialized (dry_run={dry_run}, parallel={parallel})")

    def _get_all_tables(self) -> List[str]:
        """Get list of all tables in database."""
        inspector = inspect(self.engine)
        return inspector.get_table_names()

    def _is_per_stock_table(self, table_name: str) -> bool:
        """
        Check if table is a per-stock table.

        Args:
            table_name: Name of the table

        Returns:
            True if table follows per-stock naming pattern
        """
        # Common patterns: SYMBOL_daily, SYMBOL_intraday, SYMBOL_1min, etc.
        patterns = [
            r'^[A-Z0-9]+_(daily|intraday|1min|5min|15min|hourly)$',
            r'^[A-Z0-9]+_(prices|ohlc|candles)$',
            r'^[A-Z0-9]+_(signals|indicators)$'
        ]
        return any(re.match(pattern, table_name) for pattern in patterns)

    def _extract_symbol_from_table(self, table_name: str) -> Optional[str]:
        """
        Extract symbol name from per-stock table name.

        Args:
            table_name: Name of the table

        Returns:
            Symbol name or None if not a per-stock table
        """
        match = re.match(r'^([A-Z0-9]+)_(.+)$', table_name)
        if match:
            return match.group(1)
        return None

    def _count_table_records(self, table_name: str) -> int:
        """
        Count records in a table.

        Args:
            table_name: Name of the table

        Returns:
            Number of records
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM `{table_name}`"))
                return result.scalar() or 0
        except Exception as e:
            logger.warning(f"Failed to count records in {table_name}: {e}")
            return 0

    def phase1_analyze_old_schema(self) -> Dict[str, any]:
        """
        Phase 1: Analyze old database schema.

        Returns:
            Dictionary with analysis results
        """
        logger.info("=" * 80)
        logger.info("PHASE 1: Analyzing Old Schema")
        logger.info("=" * 80)
        
        all_tables = self._get_all_tables()
        logger.info(f"Found {len(all_tables)} total tables")
        
        # Categorize tables
        per_stock_tables = []
        system_tables = []
        
        for table in tqdm(all_tables, desc="Analyzing tables"):
            if self._is_per_stock_table(table):
                symbol = self._extract_symbol_from_table(table)
                record_count = self._count_table_records(table)
                per_stock_tables.append({
                    'table': table,
                    'symbol': symbol,
                    'records': record_count
                })
            else:
                system_tables.append(table)
        
        # Extract unique symbols
        symbols = set(item['symbol'] for item in per_stock_tables if item['symbol'])
        
        # Calculate statistics
        total_records = sum(item['records'] for item in per_stock_tables)
        
        analysis = {
            'total_tables': len(all_tables),
            'per_stock_tables': len(per_stock_tables),
            'system_tables': len(system_tables),
            'unique_symbols': len(symbols),
            'total_records': total_records,
            'symbols': sorted(symbols),
            'table_details': per_stock_tables
        }
        
        # Log summary
        logger.info(f"Per-stock tables: {analysis['per_stock_tables']}")
        logger.info(f"System tables: {analysis['system_tables']}")
        logger.info(f"Unique symbols: {analysis['unique_symbols']}")
        logger.info(f"Total records: {analysis['total_records']:,}")
        logger.info(f"Symbols: {', '.join(list(symbols)[:10])}{'...' if len(symbols) > 10 else ''}")
        
        self.stats.total_tables = analysis['per_stock_tables']
        self.stats.total_records = analysis['total_records']
        
        return analysis

    def phase2_map_tables(self, analysis: Dict[str, any]) -> None:
        """
        Phase 2: Create mappings from old tables to new schema.

        Args:
            analysis: Results from phase 1
        """
        logger.info("=" * 80)
        logger.info("PHASE 2: Mapping Tables")
        logger.info("=" * 80)
        
        # First, ensure symbols exist in new schema
        self._ensure_symbols_exist(analysis['symbols'])
        
        # Create table mappings
        for table_detail in tqdm(analysis['table_details'], desc="Creating mappings"):
            table_name = table_detail['table']
            symbol = table_detail['symbol']
            record_count = table_detail['records']
            
            if not symbol:
                continue
            
            # Determine target table and column mappings
            mapping = self._create_table_mapping(table_name, symbol, record_count)
            if mapping:
                self.table_mappings.append(mapping)
        
        logger.info(f"Created {len(self.table_mappings)} table mappings")
        
        # Log sample mappings
        for mapping in self.table_mappings[:5]:
            logger.info(f"  {mapping.old_table} → {mapping.new_table} ({mapping.record_count:,} records)")

    def _ensure_symbols_exist(self, symbols: Set[str]) -> None:
        """
        Ensure all symbols exist in the symbols table.

        Args:
            symbols: Set of symbol names
        """
        logger.info(f"Ensuring {len(symbols)} symbols exist in database")
        
        with self.SessionLocal() as session:
            try:
                for symbol in tqdm(symbols, desc="Checking symbols"):
                    # Check if symbol exists
                    result = session.execute(
                        text("SELECT id FROM symbols WHERE symbol = :symbol"),
                        {"symbol": symbol}
                    ).fetchone()
                    
                    if result:
                        self.symbol_ids[symbol] = result[0]
                    else:
                        # Insert symbol
                        if not self.dry_run:
                            result = session.execute(
                                text("""
                                    INSERT INTO symbols (symbol, name, exchange, is_active)
                                    VALUES (:symbol, :name, 'NSE', TRUE)
                                """),
                                {"symbol": symbol, "name": symbol}
                            )
                            session.commit()
                            
                            # Get the inserted ID
                            result = session.execute(
                                text("SELECT id FROM symbols WHERE symbol = :symbol"),
                                {"symbol": symbol}
                            ).fetchone()
                            self.symbol_ids[symbol] = result[0]
                            logger.debug(f"Created symbol {symbol} with ID {result[0]}")
                        else:
                            # In dry-run, assign temporary ID
                            self.symbol_ids[symbol] = -1
                
                logger.info(f"Symbol IDs cached: {len(self.symbol_ids)}")
                
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to ensure symbols exist: {e}")
                raise

    def _create_table_mapping(
        self, 
        old_table: str, 
        symbol: str, 
        record_count: int
    ) -> Optional[TableMapping]:
        """
        Create mapping configuration for a table.

        Args:
            old_table: Old table name
            symbol: Symbol name
            record_count: Number of records

        Returns:
            TableMapping object or None
        """
        # Determine table type and target
        if '_daily' in old_table or '_1d' in old_table:
            return TableMapping(
                old_table=old_table,
                new_table='prices',
                symbol=symbol,
                record_count=record_count,
                column_mappings={
                    'date': 'date',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume',
                    'adj_close': 'adj_close'
                }
            )
        elif '_intraday' in old_table or '_1min' in old_table or '_5min' in old_table:
            return TableMapping(
                old_table=old_table,
                new_table='prices',
                symbol=symbol,
                record_count=record_count,
                column_mappings={
                    'timestamp': 'timestamp',
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume'
                }
            )
        elif '_signals' in old_table:
            return TableMapping(
                old_table=old_table,
                new_table='signals',
                symbol=symbol,
                record_count=record_count,
                column_mappings={
                    'date': 'generated_at',
                    'signal_type': 'signal_type',
                    'strategy': 'strategy_name',
                    'price': 'price',
                    'confidence': 'confidence'
                }
            )
        
        return None

    def phase3_migrate_data(self) -> None:
        """Phase 3: Migrate data from old tables to new schema."""
        logger.info("=" * 80)
        logger.info("PHASE 3: Migrating Data")
        logger.info("=" * 80)
        
        if self.dry_run:
            logger.info("DRY RUN: Skipping actual data migration")
            return
        
        self.stats.start_time = datetime.now()
        
        if self.parallel:
            self._migrate_data_parallel()
        else:
            self._migrate_data_sequential()
        
        self.stats.end_time = datetime.now()
        duration = (self.stats.end_time - self.stats.start_time).total_seconds()
        
        logger.info(f"Migration completed in {duration:.2f} seconds")
        logger.info(f"Migrated: {self.stats.migrated_records:,} records")
        logger.info(f"Failed: {self.stats.failed_records:,} records")

    def _migrate_data_sequential(self) -> None:
        """Migrate data sequentially (single-threaded)."""
        for mapping in tqdm(self.table_mappings, desc="Migrating tables"):
            try:
                self._migrate_single_table(mapping)
                self.stats.processed_tables += 1
            except Exception as e:
                logger.error(f"Failed to migrate {mapping.old_table}: {e}")

    def _migrate_data_parallel(self) -> None:
        """Migrate data in parallel (multi-threaded)."""
        max_workers = min(10, len(self.table_mappings))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._migrate_single_table, mapping): mapping
                for mapping in self.table_mappings
            }
            
            with tqdm(total=len(self.table_mappings), desc="Migrating tables") as pbar:
                for future in as_completed(futures):
                    mapping = futures[future]
                    try:
                        future.result()
                        self.stats.processed_tables += 1
                    except Exception as e:
                        logger.error(f"Failed to migrate {mapping.old_table}: {e}")
                    finally:
                        pbar.update(1)

    def _migrate_single_table(self, mapping: TableMapping) -> None:
        """
        Migrate a single table.

        Args:
            mapping: Table mapping configuration
        """
        logger.info(f"Migrating {mapping.old_table} → {mapping.new_table}")
        
        symbol_id = self.symbol_ids.get(mapping.symbol)
        if not symbol_id or symbol_id < 0:
            logger.warning(f"No symbol ID for {mapping.symbol}, skipping {mapping.old_table}")
            return
        
        # Process in batches
        offset = 0
        migrated = 0
        
        with self.SessionLocal() as session:
            try:
                while offset < mapping.record_count:
                    # Fetch batch from old table
                    batch = self._fetch_batch(mapping.old_table, offset, BATCH_SIZE)
                    
                    if not batch:
                        break
                    
                    # Transform and insert into new table
                    success = self._insert_batch(
                        session, 
                        mapping.new_table, 
                        batch, 
                        mapping.column_mappings,
                        symbol_id
                    )
                    
                    if success:
                        migrated += len(batch)
                        self.stats.migrated_records += len(batch)
                    else:
                        self.stats.failed_records += len(batch)
                    
                    offset += BATCH_SIZE
                
                logger.info(f"Completed {mapping.old_table}: {migrated:,} records migrated")
                
            except Exception as e:
                session.rollback()
                logger.error(f"Error migrating {mapping.old_table}: {e}")
                raise

    def _fetch_batch(self, table_name: str, offset: int, limit: int) -> List[Dict]:
        """
        Fetch a batch of records from old table.

        Args:
            table_name: Old table name
            offset: Starting offset
            limit: Number of records to fetch

        Returns:
            List of record dictionaries
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(
                    text(f"SELECT * FROM `{table_name}` LIMIT :limit OFFSET :offset"),
                    {"limit": limit, "offset": offset}
                )
                
                # Convert to list of dicts
                columns = result.keys()
                return [dict(zip(columns, row)) for row in result.fetchall()]
                
        except Exception as e:
            logger.error(f"Failed to fetch batch from {table_name}: {e}")
            return []

    def _insert_batch(
        self,
        session: Session,
        table_name: str,
        batch: List[Dict],
        column_mappings: Dict[str, str],
        symbol_id: int
    ) -> bool:
        """
        Insert batch of records into new table.

        Args:
            session: Database session
            table_name: Target table name
            batch: List of records to insert
            column_mappings: Old→new column mappings
            symbol_id: Symbol ID for the records

        Returns:
            True if successful, False otherwise
        """
        try:
            # Transform records
            transformed = []
            for record in batch:
                new_record = {'symbol_id': symbol_id}
                
                for old_col, new_col in column_mappings.items():
                    if old_col in record:
                        new_record[new_col] = record[old_col]
                
                # Add metadata
                new_record['created_at'] = datetime.now()
                new_record['updated_at'] = datetime.now()
                
                transformed.append(new_record)
            
            # Bulk insert
            if table_name == 'prices':
                session.execute(
                    text("""
                        INSERT INTO prices 
                        (symbol_id, date, timestamp, open, high, low, close, volume, adj_close, created_at, updated_at)
                        VALUES 
                        (:symbol_id, :date, :timestamp, :open, :high, :low, :close, :volume, :adj_close, :created_at, :updated_at)
                        ON DUPLICATE KEY UPDATE 
                        open=VALUES(open), high=VALUES(high), low=VALUES(low), 
                        close=VALUES(close), volume=VALUES(volume), adj_close=VALUES(adj_close),
                        updated_at=VALUES(updated_at)
                    """),
                    transformed
                )
            elif table_name == 'signals':
                session.execute(
                    text("""
                        INSERT INTO signals 
                        (symbol_id, strategy_name, signal_type, generated_at, price, confidence, created_at, updated_at)
                        VALUES 
                        (:symbol_id, :strategy_name, :signal_type, :generated_at, :price, :confidence, :created_at, :updated_at)
                    """),
                    transformed
                )
            
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to insert batch into {table_name}: {e}")
            return False

    def phase4_validate_migration(self) -> Dict[str, any]:
        """
        Phase 4: Validate migration integrity.

        Returns:
            Dictionary with validation results
        """
        logger.info("=" * 80)
        logger.info("PHASE 4: Validating Migration")
        logger.info("=" * 80)
        
        validation = {
            'record_counts': {},
            'fk_integrity': True,
            'data_quality': {}
        }
        
        with self.SessionLocal() as session:
            # Count records in new tables
            for table in ['symbols', 'prices', 'signals']:
                try:
                    result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    validation['record_counts'][table] = count
                    logger.info(f"{table}: {count:,} records")
                except Exception as e:
                    logger.error(f"Failed to count {table}: {e}")
                    validation['record_counts'][table] = -1
            
            # Check foreign key integrity
            try:
                result = session.execute(text("""
                    SELECT COUNT(*) FROM prices p
                    LEFT JOIN symbols s ON p.symbol_id = s.id
                    WHERE s.id IS NULL
                """))
                orphaned = result.scalar()
                
                if orphaned > 0:
                    logger.warning(f"Found {orphaned} prices records with invalid symbol_id")
                    validation['fk_integrity'] = False
                else:
                    logger.info("Foreign key integrity: OK")
                    
            except Exception as e:
                logger.error(f"Failed to check FK integrity: {e}")
                validation['fk_integrity'] = False
            
            # Data quality checks
            try:
                # Check for NULL values in critical columns
                result = session.execute(text("""
                    SELECT COUNT(*) FROM prices 
                    WHERE close IS NULL OR volume IS NULL
                """))
                null_count = result.scalar()
                validation['data_quality']['null_values'] = null_count
                
                if null_count > 0:
                    logger.warning(f"Found {null_count} records with NULL critical values")
                else:
                    logger.info("Data quality checks: OK")
                    
            except Exception as e:
                logger.error(f"Failed data quality check: {e}")
        
        # Compare record counts
        expected = self.stats.total_records
        actual = validation['record_counts'].get('prices', 0)
        diff = abs(expected - actual)
        pct_diff = (diff / expected * 100) if expected > 0 else 0
        
        logger.info(f"Expected records: {expected:,}")
        logger.info(f"Actual records: {actual:,}")
        logger.info(f"Difference: {diff:,} ({pct_diff:.2f}%)")
        
        return validation

    def phase5_archive_old_tables(self) -> None:
        """Phase 5: Archive old tables by renaming with _old suffix."""
        logger.info("=" * 80)
        logger.info("PHASE 5: Archiving Old Tables")
        logger.info("=" * 80)
        
        if self.dry_run:
            logger.info("DRY RUN: Skipping table archival")
            return
        
        archived = 0
        failed = 0
        
        with self.engine.connect() as conn:
            for mapping in tqdm(self.table_mappings, desc="Archiving tables"):
                old_table = mapping.old_table
                new_name = f"{old_table}_old"
                
                try:
                    # Check if table exists
                    result = conn.execute(text("""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_schema = DATABASE() 
                        AND table_name = :table
                    """), {"table": old_table})
                    
                    if result.scalar() == 0:
                        logger.debug(f"Table {old_table} doesn't exist, skipping")
                        continue
                    
                    # Rename table
                    conn.execute(text(f"RENAME TABLE `{old_table}` TO `{new_name}`"))
                    conn.commit()
                    archived += 1
                    logger.debug(f"Archived: {old_table} → {new_name}")
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Failed to archive {old_table}: {e}")
                    failed += 1
        
        logger.info(f"Archived: {archived} tables")
        logger.info(f"Failed: {failed} tables")


def migrate_database(
    dry_run: bool = False,
    start_phase: int = 1,
    parallel: bool = False
) -> None:
    """
    Main migration function.

    Args:
        dry_run: If True, perform analysis only without actual migration
        start_phase: Phase to start from (1-5)
        parallel: If True, use parallel processing for migration

    Raises:
        ValueError: If start_phase is invalid
    """
    if start_phase < 1 or start_phase > 5:
        raise ValueError("start_phase must be between 1 and 5")
    
    logger.info("=" * 80)
    logger.info("DATABASE MIGRATION STARTED")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    logger.info(f"Start Phase: {start_phase}")
    logger.info(f"Parallel: {parallel}")
    logger.info("=" * 80)
    
    try:
        migrator = DatabaseMigrator(dry_run=dry_run, parallel=parallel)
        
        analysis = None
        
        # Phase 1: Analyze
        if start_phase <= 1:
            analysis = migrator.phase1_analyze_old_schema()
        
        # Phase 2: Map
        if start_phase <= 2:
            if not analysis and start_phase == 2:
                logger.warning("Starting from phase 2 without phase 1 analysis")
                analysis = migrator.phase1_analyze_old_schema()
            migrator.phase2_map_tables(analysis)
        
        # Phase 3: Migrate
        if start_phase <= 3:
            if not migrator.table_mappings and start_phase == 3:
                logger.warning("Starting from phase 3 without mappings")
                analysis = migrator.phase1_analyze_old_schema()
                migrator.phase2_map_tables(analysis)
            migrator.phase3_migrate_data()
        
        # Phase 4: Validate
        if start_phase <= 4:
            validation = migrator.phase4_validate_migration()
        
        # Phase 5: Archive
        if start_phase <= 5:
            migrator.phase5_archive_old_tables()
        
        logger.info("=" * 80)
        logger.info("DATABASE MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("=" * 80)
        
        # Print final statistics
        if migrator.stats.end_time and migrator.stats.start_time:
            duration = (migrator.stats.end_time - migrator.stats.start_time).total_seconds()
            logger.info(f"Total Duration: {duration:.2f} seconds")
        logger.info(f"Tables Processed: {migrator.stats.processed_tables}/{migrator.stats.total_tables}")
        logger.info(f"Records Migrated: {migrator.stats.migrated_records:,}")
        logger.info(f"Records Failed: {migrator.stats.failed_records:,}")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate StockJarvis database to new schema")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform analysis only without actual migration"
    )
    parser.add_argument(
        "--start-phase",
        type=int,
        default=1,
        choices=[1, 2, 3, 4, 5],
        help="Phase to start from (1-5)"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Use parallel processing for migration"
    )
    
    args = parser.parse_args()
    
    migrate_database(
        dry_run=args.dry_run,
        start_phase=args.start_phase,
        parallel=args.parallel
    )
