"""
scripts/migration_validator.py

Migration validator script to ensure data integrity during database schema migration.
Validates record counts, data integrity, and data quality between old and new schemas.
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict
import json

from sqlalchemy import create_engine, text, inspect, MetaData, Table
from sqlalchemy.orm import sessionmaker, Session
from tqdm import tqdm

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import settings
from core.logger import setup_logging, get_logger


# Setup logging for migration validator
log_file = Path("logs/migration_validator.log")
log_file.parent.mkdir(parents=True, exist_ok=True)
logger = get_logger(__name__)


class ValidationResult:
    """Container for validation results."""
    
    def __init__(self, check_name: str):
        self.check_name = check_name
        self.passed = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: Dict[str, Any] = {}
        self.timestamp = datetime.utcnow()
    
    def add_error(self, message: str):
        """Add an error to the result."""
        self.errors.append(message)
        self.passed = False
    
    def add_warning(self, message: str):
        """Add a warning to the result."""
        self.warnings.append(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "check_name": self.check_name,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "timestamp": self.timestamp.isoformat()
        }


class MigrationValidator:
    """Validates database migration from old schema to new normalized schema."""
    
    def __init__(self, session: Session):
        """
        Initialize validator.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.engine = session.bind
        self.results: List[ValidationResult] = []
        logger.info("MigrationValidator initialized")
    
    def validate_record_counts(
        self,
        old_table: str,
        new_table: str,
        condition: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate that record counts match between old and new tables.
        
        Args:
            old_table: Name of old table (e.g., 'SBIN_old')
            new_table: Name of new table (e.g., 'prices')
            condition: Optional WHERE condition for new table
        
        Returns:
            ValidationResult with comparison details
        """
        result = ValidationResult(f"Record Count: {old_table} -> {new_table}")
        logger.info(f"Validating record counts: {old_table} -> {new_table}")
        
        try:
            # Check if old table exists
            inspector = inspect(self.engine)
            if old_table not in inspector.get_table_names():
                result.add_warning(f"Old table '{old_table}' not found (may have been dropped)")
                return result
            
            # Count records in old table
            old_count_query = text(f"SELECT COUNT(*) FROM `{old_table}`")
            old_count = self.session.execute(old_count_query).scalar()
            
            # Count records in new table
            if condition:
                new_count_query = text(f"SELECT COUNT(*) FROM {new_table} WHERE {condition}")
            else:
                new_count_query = text(f"SELECT COUNT(*) FROM {new_table}")
            new_count = self.session.execute(new_count_query).scalar()
            
            result.info["old_count"] = old_count
            result.info["new_count"] = new_count
            result.info["difference"] = new_count - old_count
            
            if old_count != new_count:
                result.add_error(
                    f"Record count mismatch: {old_table}={old_count}, "
                    f"{new_table}={new_count}, difference={new_count - old_count}"
                )
            else:
                logger.info(f"✓ Record counts match: {old_count} records")
            
        except Exception as e:
            result.add_error(f"Failed to validate record counts: {str(e)}")
            logger.error(f"Error validating record counts: {str(e)}", exc_info=True)
        
        self.results.append(result)
        return result
    
    def validate_data_integrity(self) -> ValidationResult:
        """
        Validate data integrity constraints (FK, NOT NULL, etc.).
        
        Returns:
            ValidationResult with integrity check details
        """
        result = ValidationResult("Data Integrity Checks")
        logger.info("Validating data integrity constraints")
        
        integrity_checks = [
            # Foreign key violations
            {
                "name": "Prices FK to Symbols",
                "query": """
                    SELECT COUNT(*) FROM prices p
                    LEFT JOIN symbols s ON p.symbol_id = s.id
                    WHERE s.id IS NULL
                """
            },
            {
                "name": "Signals FK to Symbols",
                "query": """
                    SELECT COUNT(*) FROM signals sig
                    LEFT JOIN symbols s ON sig.symbol_id = s.id
                    WHERE s.id IS NULL
                """
            },
            {
                "name": "Signals FK to Strategies",
                "query": """
                    SELECT COUNT(*) FROM signals sig
                    LEFT JOIN strategies st ON sig.strategy_id = st.id
                    WHERE st.id IS NULL
                """
            },
            {
                "name": "Positions FK to Symbols",
                "query": """
                    SELECT COUNT(*) FROM positions pos
                    LEFT JOIN symbols s ON pos.symbol_id = s.id
                    WHERE s.id IS NULL
                """
            },
            # NOT NULL violations
            {
                "name": "Prices NOT NULL constraints",
                "query": """
                    SELECT COUNT(*) FROM prices
                    WHERE symbol_id IS NULL OR timestamp IS NULL
                       OR open IS NULL OR high IS NULL OR low IS NULL
                       OR close IS NULL OR volume IS NULL
                """
            },
            {
                "name": "Symbols NOT NULL constraints",
                "query": """
                    SELECT COUNT(*) FROM symbols
                    WHERE symbol IS NULL OR company_name IS NULL OR exchange IS NULL
                """
            },
            {
                "name": "Signals NOT NULL constraints",
                "query": """
                    SELECT COUNT(*) FROM signals
                    WHERE strategy_id IS NULL OR symbol_id IS NULL
                       OR action IS NULL OR price IS NULL
                       OR stop_loss IS NULL OR target IS NULL
                """
            },
        ]
        
        for check in tqdm(integrity_checks, desc="Integrity checks"):
            try:
                violations = self.session.execute(text(check["query"])).scalar()
                result.info[check["name"]] = violations
                
                if violations > 0:
                    result.add_error(f"{check['name']}: {violations} violations found")
                    logger.warning(f"✗ {check['name']}: {violations} violations")
                else:
                    logger.info(f"✓ {check['name']}: No violations")
                    
            except Exception as e:
                result.add_warning(f"{check['name']}: Check failed - {str(e)}")
                logger.error(f"Error in {check['name']}: {str(e)}")
        
        self.results.append(result)
        return result
    
    def validate_data_quality(self) -> ValidationResult:
        """
        Validate data quality (invalid dates, negative prices, duplicates, etc.).
        
        Returns:
            ValidationResult with quality check details
        """
        result = ValidationResult("Data Quality Checks")
        logger.info("Validating data quality")
        
        quality_checks = [
            # Invalid dates
            {
                "name": "Future timestamps",
                "query": f"""
                    SELECT COUNT(*) FROM prices
                    WHERE timestamp > '{datetime.utcnow()}'
                """
            },
            {
                "name": "Very old timestamps (before 2000)",
                "query": """
                    SELECT COUNT(*) FROM prices
                    WHERE timestamp < '2000-01-01'
                """
            },
            # Invalid prices
            {
                "name": "Negative prices",
                "query": """
                    SELECT COUNT(*) FROM prices
                    WHERE open < 0 OR high < 0 OR low < 0 OR close < 0
                """
            },
            {
                "name": "Zero prices",
                "query": """
                    SELECT COUNT(*) FROM prices
                    WHERE open = 0 OR high = 0 OR low = 0 OR close = 0
                """
            },
            {
                "name": "Invalid OHLC relationships (high < low)",
                "query": """
                    SELECT COUNT(*) FROM prices
                    WHERE high < low OR high < open OR high < close
                       OR low > open OR low > close
                """
            },
            {
                "name": "Negative or zero volume",
                "query": """
                    SELECT COUNT(*) FROM prices
                    WHERE volume <= 0
                """
            },
            # Duplicates
            {
                "name": "Duplicate price records",
                "query": """
                    SELECT COUNT(*) FROM (
                        SELECT symbol_id, timestamp, timeframe, COUNT(*) as cnt
                        FROM prices
                        GROUP BY symbol_id, timestamp, timeframe
                        HAVING cnt > 1
                    ) as dups
                """
            },
            {
                "name": "Duplicate symbols",
                "query": """
                    SELECT COUNT(*) FROM (
                        SELECT symbol, COUNT(*) as cnt
                        FROM symbols
                        GROUP BY symbol
                        HAVING cnt > 1
                    ) as dups
                """
            },
            # Signal quality
            {
                "name": "Invalid signal targets (target <= entry for BUY)",
                "query": """
                    SELECT COUNT(*) FROM signals
                    WHERE action = 'BUY' AND target <= price
                """
            },
            {
                "name": "Invalid signal stop loss (stop_loss >= entry for BUY)",
                "query": """
                    SELECT COUNT(*) FROM signals
                    WHERE action = 'BUY' AND stop_loss >= price
                """
            },
            {
                "name": "Invalid signal confidence (outside 0-1)",
                "query": """
                    SELECT COUNT(*) FROM signals
                    WHERE confidence < 0 OR confidence > 1
                """
            },
        ]
        
        for check in tqdm(quality_checks, desc="Quality checks"):
            try:
                issues = self.session.execute(text(check["query"])).scalar()
                result.info[check["name"]] = issues
                
                if issues > 0:
                    # Some issues are warnings, not errors
                    if "old timestamps" in check["name"].lower() or "zero volume" in check["name"].lower():
                        result.add_warning(f"{check['name']}: {issues} issues found")
                        logger.warning(f"⚠ {check['name']}: {issues} issues")
                    else:
                        result.add_error(f"{check['name']}: {issues} issues found")
                        logger.warning(f"✗ {check['name']}: {issues} issues")
                else:
                    logger.info(f"✓ {check['name']}: No issues")
                    
            except Exception as e:
                result.add_warning(f"{check['name']}: Check failed - {str(e)}")
                logger.error(f"Error in {check['name']}: {str(e)}")
        
        self.results.append(result)
        return result
    
    def validate_symbol_migration(self) -> ValidationResult:
        """
        Validate that all symbols from old tables are present in symbols table.
        
        Returns:
            ValidationResult with symbol migration details
        """
        result = ValidationResult("Symbol Migration Validation")
        logger.info("Validating symbol migration")
        
        try:
            # Get all tables ending with _old
            inspector = inspect(self.engine)
            all_tables = inspector.get_table_names()
            old_tables = [t for t in all_tables if t.endswith('_old')]
            
            if not old_tables:
                result.add_warning("No old tables found (ending with '_old')")
                self.results.append(result)
                return result
            
            # Extract expected symbols from old table names
            expected_symbols = []
            for table in old_tables:
                symbol = table.replace('_old', '')
                # Handle NSE suffix
                if symbol.endswith('_NSE'):
                    symbol = symbol.replace('_NSE', '')
                expected_symbols.append(symbol)
            
            # Check if all symbols exist
            query = text("SELECT symbol FROM symbols WHERE symbol IN :symbols")
            found_symbols = [row[0] for row in self.session.execute(
                query, {"symbols": tuple(expected_symbols)}
            )]
            
            missing_symbols = set(expected_symbols) - set(found_symbols)
            
            result.info["total_expected"] = len(expected_symbols)
            result.info["found"] = len(found_symbols)
            result.info["missing"] = list(missing_symbols)
            
            if missing_symbols:
                result.add_error(
                    f"{len(missing_symbols)} symbols not found in symbols table: "
                    f"{', '.join(list(missing_symbols)[:10])}{'...' if len(missing_symbols) > 10 else ''}"
                )
            else:
                logger.info(f"✓ All {len(expected_symbols)} symbols found in symbols table")
            
        except Exception as e:
            result.add_error(f"Failed to validate symbol migration: {str(e)}")
            logger.error(f"Error validating symbol migration: {str(e)}", exc_info=True)
        
        self.results.append(result)
        return result
    
    def generate_validation_report(
        self,
        output_dir: Path = Path("reports")
    ) -> Tuple[Path, Path]:
        """
        Generate HTML and JSON validation reports.
        
        Args:
            output_dir: Directory to save reports
        
        Returns:
            Tuple of (html_path, json_path)
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Generate JSON report
        json_path = output_dir / f"migration_validation_{timestamp}.json"
        json_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_checks": len(self.results),
            "passed_checks": sum(1 for r in self.results if r.passed),
            "failed_checks": sum(1 for r in self.results if not r.passed),
            "results": [r.to_dict() for r in self.results]
        }
        
        with open(json_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        logger.info(f"JSON report saved to {json_path}")
        
        # Generate HTML report
        html_path = output_dir / f"migration_validation_{timestamp}.html"
        html_content = self._generate_html_report(json_data)
        
        with open(html_path, 'w') as f:
            f.write(html_content)
        
        logger.info(f"HTML report saved to {html_path}")
        
        return html_path, json_path
    
    def _generate_html_report(self, json_data: Dict) -> str:
        """Generate HTML report from validation results."""
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Migration Validation Report</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .summary-card {{
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        .summary-card.passed {{
            background-color: #d4edda;
            border: 2px solid #28a745;
        }}
        .summary-card.failed {{
            background-color: #f8d7da;
            border: 2px solid #dc3545;
        }}
        .summary-card h3 {{
            margin: 0 0 10px 0;
            font-size: 2em;
        }}
        .summary-card p {{
            margin: 0;
            color: #666;
        }}
        .result {{
            margin: 20px 0;
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid #ccc;
        }}
        .result.passed {{
            background-color: #d4edda;
            border-left-color: #28a745;
        }}
        .result.failed {{
            background-color: #f8d7da;
            border-left-color: #dc3545;
        }}
        .result h3 {{
            margin-top: 0;
            color: #2c3e50;
        }}
        .error {{
            color: #dc3545;
            margin: 5px 0;
            padding: 8px;
            background-color: #fff5f5;
            border-radius: 4px;
        }}
        .warning {{
            color: #ffc107;
            margin: 5px 0;
            padding: 8px;
            background-color: #fffef5;
            border-radius: 4px;
        }}
        .info {{
            margin: 10px 0;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.9em;
        }}
        .timestamp {{
            color: #666;
            font-size: 0.9em;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Migration Validation Report</h1>
        
        <div class="summary">
            <div class="summary-card">
                <h3>{json_data['total_checks']}</h3>
                <p>Total Checks</p>
            </div>
            <div class="summary-card passed">
                <h3>{json_data['passed_checks']}</h3>
                <p>Passed ✓</p>
            </div>
            <div class="summary-card failed">
                <h3>{json_data['failed_checks']}</h3>
                <p>Failed ✗</p>
            </div>
        </div>
        
        <h2>Validation Results</h2>
"""
        
        for result_data in json_data['results']:
            status_class = 'passed' if result_data['passed'] else 'failed'
            status_icon = '✓' if result_data['passed'] else '✗'
            
            html += f"""
        <div class="result {status_class}">
            <h3>{status_icon} {result_data['check_name']}</h3>
"""
            
            if result_data['errors']:
                html += '<div><strong>Errors:</strong></div>'
                for error in result_data['errors']:
                    html += f'<div class="error">❌ {error}</div>'
            
            if result_data['warnings']:
                html += '<div><strong>Warnings:</strong></div>'
                for warning in result_data['warnings']:
                    html += f'<div class="warning">⚠️ {warning}</div>'
            
            if result_data['info']:
                html += '<div><strong>Details:</strong></div><div class="info">'
                for key, value in result_data['info'].items():
                    html += f'<div>{key}: {value}</div>'
                html += '</div>'
            
            html += '</div>'
        
        html += f"""
        <div class="timestamp">
            Generated: {json_data['timestamp']}
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def validate_all(self) -> bool:
        """
        Run all validation checks.
        
        Returns:
            True if all validations passed, False otherwise
        """
        logger.info("=" * 60)
        logger.info("Starting comprehensive migration validation")
        logger.info("=" * 60)
        
        # Run all validations
        self.validate_symbol_migration()
        self.validate_data_integrity()
        self.validate_data_quality()
        
        # Generate report
        html_path, json_path = self.generate_validation_report()
        
        # Summary
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        
        logger.info("=" * 60)
        logger.info(f"Validation Summary: {passed}/{total} checks passed")
        if failed > 0:
            logger.error(f"❌ {failed} checks failed")
        else:
            logger.info("✅ All validation checks passed!")
        logger.info(f"Reports generated: {html_path}, {json_path}")
        logger.info("=" * 60)
        
        return failed == 0


def main():
    """Main entry point for migration validator."""
    parser = argparse.ArgumentParser(
        description="Validate StockJarvis database migration"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Directory to save validation reports (default: reports/)"
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
    
    logger.info("Migration Validator started")
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
        
        # Create validator
        validator = MigrationValidator(session)
        
        # Run validation
        success = validator.validate_all()
        
        # Cleanup
        session.close()
        engine.dispose()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"Fatal error during validation: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
