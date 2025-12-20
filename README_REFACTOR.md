# StockJarvis Trading System - Refactored Architecture

> **Note**: This is a major refactor branch (`refactor/simplified-architecture`) introducing a simplified, production-ready architecture while preserving all planned capabilities.

## 🎯 Architecture Overview

The new StockJarvis uses a **3-layer modular architecture** that eliminates complexity while maintaining robustness:

```
┌─────────────────────────────────────────────────────────────┐
│                     STOCKJARVIS v2.0                        │
└─────────────────────────────────────────────────────────────┘

                     ┌──────────────┐
                     │   FastAPI    │  REST API + WebSockets
                     │   Server     │  (Port 8000)
                     └──────┬───────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐      ┌───────▼──────┐    ┌──────▼─────┐
   │ Scanner │      │   Strategy    │    │  Position  │
   │ Engine  │◄─────┤   Engine      │────►│  Tracker   │
   └────┬────┘      └───────┬───────┘    └──────┬─────┘
        │                   │                    │
        └───────────┬───────┴────────────────────┘
                    │
            ┌───────▼────────┐
            │  Data Layer    │  Repository Pattern
            │  (SQLAlchemy)  │
            └───────┬────────┘
                    │
      ┌─────────────┼─────────────┐
      │             │             │
┌─────▼──────┐  ┌──▼───┐   ┌─────▼────┐
│   MySQL    │  │Redis │   │  Broker  │
│  Database  │  │Queue │   │  (Kite)  │
└────────────┘  └──────┘   └──────────┘
```

## ✨ Key Improvements

### 1. **Configuration Management**
- ✅ **No hardcoded credentials** - All sensitive data in `.env` file
- ✅ **Type-safe settings** using Pydantic
- ✅ **Environment-aware** (dev/staging/prod)

### 2. **Database Schema**
- ✅ **Normalized design** - Single `prices` table instead of 100+ per-stock tables
- ✅ **Proper indexes** and foreign keys
- ✅ **ORM with SQLAlchemy** - No raw SQL queries

### 3. **Strategy Framework**
- ✅ **Abstract base class** for all strategies
- ✅ **Plugin architecture** - Easy to add new strategies
- ✅ **Validation framework** - Strategies must pass 65%+ accuracy
- ✅ **Unified scanner** - Replaces separate EOD/Intraday scanners

### 4. **Modern Tech Stack**
- FastAPI (REST API)
- Celery + Redis (Background tasks)
- SQLAlchemy (ORM)
- Pandas (Data analysis)
- Docker (Deployment)

## 📁 Project Structure

```
StockJarvis/
├── config/
│   ├── __init__.py
│   └── settings.py          # Pydantic settings with .env loading
│
├── core/
│   ├── __init__.py
│   ├── logger.py            # Structured JSON logging
│   ├── strategy_engine.py   # Abstract Strategy base class
│   ├── scanner.py           # Unified symbol scanner
│   ├── backtester.py        # Vectorized backtesting [TODO]
│   ├── risk_manager.py      # Position sizing & limits [TODO]
│   └── position_tracker.py  # Position sync with broker [TODO]
│
├── data/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy ORM models
│   ├── repository.py        # Data access layer
│   └── providers/           # Data source plugins [TODO]
│
├── indicators/
│   ├── __init__.py
│   └── technical.py         # SMA, EMA, RSI, MACD, Bollinger, etc.
│
├── strategies/
│   ├── __init__.py
│   └── eod_strategies.py    # Example EOD strategies
│
├── broker/
│   └── zerodha.py           # Zerodha Kite integration [TODO]
│
├── api/
│   ├── __init__.py
│   ├── main.py              # FastAPI app [TODO]
│   └── websocket.py         # Real-time updates [TODO]
│
├── workers/
│   └── tasks.py             # Celery background tasks [TODO]
│
├── scripts/
│   ├── migrate_database.py  # Migrate old schema to new [TODO]
│   └── setup.py             # Initial setup wizard [TODO]
│
├── tests/
│   ├── conftest.py          # Pytest fixtures [TODO]
│   ├── unit/                # Unit tests [TODO]
│   └── integration/         # Integration tests [TODO]
│
├── .env.example             # Configuration template
├── .gitignore              # Git ignore rules
├── requirements.txt         # Python dependencies
├── schema.sql              # Database schema
├── docker-compose.yml      # Docker services [TODO]
├── Dockerfile              # Docker image [TODO]
└── README_REFACTOR.md      # This file
```

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- MySQL 8.0+
- Redis (for background tasks)

### 1. Setup Environment

```bash
# Clone and switch to refactor branch
git checkout refactor/simplified-architecture

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Settings

```bash
# Copy example configuration
cp .env.example .env

# Edit .env with your credentials
notepad .env  # Or your favorite editor
```

Required configuration:
- Database credentials
- Quandl API key
- Zerodha Kite API keys
- Email/SMS notification settings

### 3. Initialize Database

```bash
# Create database
mysql -u root -p < schema.sql

# Or using Python
python
>>> from data.repository import repository
>>> repository.create_tables()
```

### 4. Load Initial Data

```python
from data.repository import repository
from data.models import Exchange

# Add symbols
repository.add_symbol(
    symbol="RELIANCE",
    company_name="Reliance Industries Ltd",
    exchange=Exchange.NSE,
    is_fno=True,
    is_nifty50=True
)

# More symbols...
```

## 📊 Database Schema

### Core Tables

**symbols** - Stock master data
- Replaces scattered symbol lists
- Categories: Nifty50, F&O, sector, industry

**prices** - Unified OHLCV data
- All symbols and timeframes in one table
- Indexed on (symbol_id, timestamp, timeframe)

**strategies** - Registered strategies
- Tracks backtest performance
- Validation status

**signals** - Generated trading signals
- Links to strategy and symbol
- Tracks execution status

**orders** - Orders with broker
- Broker order ID tracking
- Paper vs live trading mode

**positions** - Current and historical positions
- Real-time P&L tracking
- Stop loss and target management

## 🎮 Usage Examples

### Running a Strategy Scan

```python
from core.scanner import create_eod_scanner
from strategies.eod_strategies import SMAGoldenCrossStrategy, RSIOversoldStrategy
from core.strategy_engine import registry

# Register strategies
registry.register(SMAGoldenCrossStrategy())
registry.register(RSIOversoldStrategy())

# Create scanner
scanner = create_eod_scanner()  # Uses all F&O symbols

# Run scan
signals = scanner.scan(parallel=True)

# Review signals
for signal in signals:
    print(f"{signal.action.value} {signal.symbol} @ {signal.price}")
    print(f"  SL: {signal.stop_loss}, Target: {signal.target}")
    print(f"  Reason: {signal.reason}\n")
```

### Creating a Custom Strategy

```python
from core.strategy_engine import Strategy, SignalOutput
from data.models import OrderAction
from indicators.technical import sma, rsi

class MyCustomStrategy(Strategy):
    def __init__(self):
        super().__init__(
            name="My_Custom_Strategy",
            description="Your strategy description",
            parameters={"param1": value1}
        )
    
    def get_required_history(self) -> int:
        return 50  # Number of days needed
    
    def generate_signal(self, symbol, data):
        # Your strategy logic here
        # Return SignalOutput or None
        pass

# Register and use
registry.register(MyCustomStrategy())
```

### Accessing Data

```python
from data.repository import repository
from datetime import datetime, timedelta

# Get historical prices
df = repository.get_prices(
    symbol="RELIANCE",
    start_date=datetime.now() - timedelta(days=365),
    end_date=datetime.now()
)

# Get latest price
latest = repository.get_latest_price("RELIANCE")
print(f"Latest close: {latest.close}")

# Get all open positions
positions = repository.get_open_positions()
for pos in positions:
    print(f"{pos.symbol.symbol}: {pos.quantity} @ {pos.entry_price}")
```

## 🧪 Testing

### Run Unit Tests

```bash
pytest tests/unit/
```

### Run Integration Tests

```bash
pytest tests/integration/
```

### Run with Coverage

```bash
pytest --cov=. --cov-report=html
```

## 🐳 Docker Deployment

### Build and Run

```bash
# Build services
docker-compose build

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

### Services

- `mysql` - Database (Port 3306)
- `redis` - Task queue (Port 6379)
- `api` - FastAPI server (Port 8000)
- `celery-worker` - Background tasks
- `celery-beat` - Task scheduler

## 📈 Migration from Old Schema

If you have existing data in the old per-stock table format:

```bash
# Run migration script
python scripts/migrate_database.py

# This will:
# 1. Backup existing database
# 2. Read all {SYMBOL}_daily tables
# 3. Insert into normalized prices table
# 4. Validate data integrity
```

## 🔧 Configuration Reference

### Trading Parameters

```python
# In .env file
TRADING_MODE=paper              # paper or live
TRADING_MAX_POSITIONS=5         # Max concurrent positions
TRADING_RISK_PER_TRADE=0.02    # 2% risk per trade
TRADING_MIN_STRATEGY_ACCURACY=0.65  # 65% min win rate
TRADING_MIN_RISK_REWARD=2.0    # Minimum 1:2 risk:reward
TRADING_CAPITAL=100000.0       # Total capital
```

### Scheduled Tasks

```python
# Cron format
APP_DATA_UPDATE_SCHEDULE=0 18 * * 1-5      # 6 PM weekdays
APP_SCANNER_SCHEDULE=30 9,15 * * 1-5       # 9:30 AM & 3 PM weekdays
```

## 🛡️ Security Best Practices

1. **Never commit `.env` file** - Contains sensitive credentials
2. **Use paper trading first** - Validate strategies before live trading
3. **Set proper position limits** - Limit risk exposure
4. **Monitor system health** - Use logging and alerts
5. **Regular backups** - Backup database regularly

## 📚 Next Steps

### Immediate TODOs
- [ ] Implement backtester with vectorized operations
- [ ] Build risk manager for position sizing
- [ ] Create FastAPI REST endpoints
- [ ] Add Celery tasks for scheduling
- [ ] Implement broker integration
- [ ] Write comprehensive tests
- [ ] Create Docker setup
- [ ] Build migration script

### Future Enhancements
- [ ] Machine learning model integration
- [ ] Advanced order types (bracket, trailing SL)
- [ ] Portfolio optimization
- [ ] Multi-timeframe analysis
- [ ] News sentiment integration
- [ ] Mobile app/Progressive Web App

## 🤝 Contributing

This is a major refactor. Key principles:

1. **Simplicity** - Keep it simple, avoid over-engineering
2. **Testing** - Write tests for all new features
3. **Documentation** - Document all public APIs
4. **Type hints** - Use Python type hints everywhere
5. **Security** - Never hardcode credentials

## 📝 License

Same as original StockJarvis project.

## 📞 Support

For questions or issues with the refactor:
1. Check this README
2. Review code documentation
3. Open an issue on GitHub

---

**Status**: 🚧 Work in Progress - Core framework complete, implementing remaining components

**Last Updated**: December 20, 2025
