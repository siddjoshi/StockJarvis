# StockJarvis 🤖📈

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.105+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

**StockJarvis** is a fully automated algorithmic trading and investment system designed for the Indian stock market (NSE/BSE). It provides a comprehensive platform for automated trading with support for multiple brokers, customizable strategies, integrated risk management, backtesting, and real-time position monitoring.

---

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Database Setup](#database-setup)
- [Usage](#-usage)
  - [Running the API Server](#running-the-api-server)
  - [Running Celery Workers](#running-celery-workers)
  - [Using the Scanner](#using-the-scanner)
  - [Creating Custom Strategies](#creating-custom-strategies)
- [API Reference](#-api-reference)
- [Docker Deployment](#-docker-deployment)
- [Testing](#-testing)
- [Configuration Reference](#-configuration-reference)
- [Database Schema](#-database-schema)
- [Risk Management](#-risk-management)
- [Contributing](#-contributing)
- [Roadmap](#-roadmap)
- [License](#-license)

---

## ✨ Features

### Core Trading Features
- **Multi-Broker Support** - Zerodha Kite Connect integration with extensible broker abstraction
- **Strategy Framework** - Plugin-based architecture for easy strategy development
- **Paper & Live Trading** - Seamless switching between paper and live trading modes
- **Signal Generation** - Automated buy/sell signal generation from registered strategies
- **Position Management** - Real-time tracking of open positions with P&L calculation

### Risk Management
- **Position Sizing** - Multiple methods: Fixed Fractional, Kelly Criterion, Risk Parity, ATR-based
- **Stop Loss Management** - Automatic stop loss calculation and trailing stops
- **Circuit Breakers** - Automatic trading halt on drawdown or consecutive losses
- **Portfolio Limits** - Maximum position count, exposure limits, and per-symbol limits
- **Drawdown Monitoring** - Daily and total drawdown tracking with alerts

### Data & Analysis
- **Technical Indicators** - SMA, EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic, ADX, OBV
- **Multiple Timeframes** - Support for 1min, 5min, 15min, hourly, daily, weekly, monthly
- **Historical Data** - Normalized OHLCV data storage for all symbols
- **Backtesting** - Strategy validation with comprehensive performance metrics

### Infrastructure
- **FastAPI REST API** - High-performance async API with auto-generated docs
- **Celery Task Queue** - Distributed task processing with Redis backend
- **Docker Ready** - Multi-container deployment with docker-compose
- **Structured Logging** - JSON logging with request tracing
- **Health Monitoring** - Endpoints for health checks and metrics

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          STOCKJARVIS v2.0                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│    ┌─────────────┐     ┌─────────────┐     ┌─────────────┐              │
│    │   FastAPI   │────▶│   Celery    │────▶│   Flower    │              │
│    │   Server    │     │   Workers   │     │  Dashboard  │              │
│    │  (Port 8000)│     │             │     │ (Port 5555) │              │
│    └──────┬──────┘     └──────┬──────┘     └─────────────┘              │
│           │                   │                                          │
│    ┌──────▼──────────────────▼──────┐                                   │
│    │          Core Services          │                                   │
│    ├─────────────┬───────────────────┤                                   │
│    │  Strategy   │    Position       │                                   │
│    │   Engine    │    Tracker        │                                   │
│    ├─────────────┼───────────────────┤                                   │
│    │   Scanner   │  Risk Manager     │                                   │
│    └─────────────┴────────┬──────────┘                                   │
│                           │                                              │
│    ┌──────────────────────▼─────────────────────┐                       │
│    │            Data Repository                  │                       │
│    │         (SQLAlchemy ORM)                    │                       │
│    └──────────────────────┬─────────────────────┘                       │
│                           │                                              │
│    ┌──────────┬───────────┴───────────┬──────────┐                      │
│    │  MySQL   │        Redis          │  Broker  │                      │
│    │ Database │       Cache/Queue     │   API    │                      │
│    └──────────┴───────────────────────┴──────────┘                      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Component Overview

| Component | Description |
|-----------|-------------|
| **FastAPI Server** | REST API for external access, Swagger UI at `/api/docs` |
| **Celery Workers** | Background task processing for data collection, signals, monitoring |
| **Celery Beat** | Scheduled task execution (EOD data updates, strategy scans) |
| **Strategy Engine** | Abstract base class and registry for trading strategies |
| **Scanner** | Runs strategies across symbols to generate signals |
| **Risk Manager** | Position sizing, stop loss, circuit breakers, portfolio limits |
| **Position Tracker** | Real-time position monitoring and P&L tracking |
| **Data Repository** | Database abstraction layer using SQLAlchemy ORM |

---

## 🛠 Tech Stack

| Category | Technology |
|----------|------------|
| **Language** | Python 3.11+ |
| **Web Framework** | FastAPI 0.105+ |
| **Database** | MySQL 8.0+ / MariaDB 10.11+ |
| **ORM** | SQLAlchemy 2.0 |
| **Task Queue** | Celery 5.3+ with Redis backend |
| **Cache** | Redis 7+ |
| **Data Processing** | Pandas 2.1+, NumPy 1.26+ |
| **Technical Analysis** | TA-Lib 0.4.28 |
| **Broker API** | Zerodha Kite Connect 4.2+ |
| **Data Providers** | Quandl, NSEPy, yfinance |
| **Authentication** | JWT (python-jose), bcrypt |
| **Containerization** | Docker, Docker Compose |
| **Testing** | pytest, pytest-asyncio, pytest-cov |
| **Monitoring** | Flower, Prometheus metrics |

---

## 📁 Project Structure

```
StockJarvis/
├── api/                          # FastAPI application
│   ├── __init__.py
│   ├── main.py                   # Application entry point
│   ├── auth.py                   # Authentication handlers
│   ├── dependencies.py           # Dependency injection
│   ├── routes/                   # API route handlers
│   │   ├── strategies.py         # Strategy management (7 endpoints)
│   │   ├── positions.py          # Position management (5 endpoints)
│   │   ├── signals.py            # Signal management (5 endpoints)
│   │   ├── symbols.py            # Symbol management (7 endpoints)
│   │   ├── backtests.py          # Backtesting (5 endpoints)
│   │   └── risk.py               # Risk management (6 endpoints)
│   └── schemas/                  # Pydantic request/response models
│
├── config/                       # Configuration management
│   ├── __init__.py
│   ├── settings.py               # Pydantic settings with .env loading
│   └── risk_config.py            # Risk management parameters
│
├── core/                         # Core business logic
│   ├── __init__.py
│   ├── logger.py                 # Structured JSON logging
│   ├── strategy_engine.py        # Abstract Strategy base class
│   ├── scanner.py                # Unified symbol scanner
│   ├── risk_manager.py           # Main risk management system
│   ├── position_tracker.py       # Position monitoring
│   ├── position_sizer.py         # Position sizing algorithms
│   ├── stop_loss_manager.py      # Stop loss calculation
│   └── position_reconciler.py    # Broker reconciliation
│
├── data/                         # Data layer
│   ├── __init__.py
│   ├── models.py                 # SQLAlchemy ORM models
│   └── repository.py             # Database access patterns
│
├── indicators/                   # Technical indicators
│   ├── __init__.py
│   └── technical.py              # SMA, EMA, RSI, MACD, Bollinger, ATR, etc.
│
├── strategies/                   # Trading strategies
│   ├── __init__.py
│   └── eod_strategies.py         # Example EOD strategies
│
├── workers/                      # Celery background workers
│   ├── __init__.py
│   ├── celery_app.py             # Celery application configuration
│   ├── celeryconfig.py           # Celery settings
│   └── tasks/                    # Task definitions
│       ├── data_collection.py    # Data ingestion tasks
│       ├── signal_generation.py  # Signal generation tasks
│       ├── monitoring.py         # Position monitoring tasks
│       └── maintenance.py        # Cleanup and maintenance tasks
│
├── BrokerModules/                # Broker integrations
│   ├── JarvisBM.py               # Broker manager base
│   └── Zerodha/                  # Zerodha Kite implementation
│
├── tests/                        # Test suite
│   ├── conftest.py               # Pytest fixtures
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── mocks/                    # Mock objects
│
├── docker/                       # Docker configuration
│   ├── mysql/                    # MySQL initialization scripts
│   └── redis/                    # Redis configuration
│
├── scripts/                      # Utility scripts
│   ├── deploy.sh                 # Deployment script
│   ├── deploy.ps1                # Windows deployment script
│   └── migrate_database.py       # Database migration tools
│
├── .env.example                  # Environment template
├── docker-compose.yml            # Multi-service orchestration
├── Dockerfile                    # Multi-stage build
├── requirements.txt              # Python dependencies
├── schema.sql                    # Database schema
├── pytest.ini                    # Pytest configuration
└── README.md                     # This file
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+** - [Download](https://www.python.org/downloads/)
- **MySQL 8.0+** or **MariaDB 10.11+** - [Download MySQL](https://dev.mysql.com/downloads/)
- **Redis 7+** - [Download](https://redis.io/download/)
- **TA-Lib** - Required for technical indicators
  - Linux: `sudo apt-get install ta-lib`
  - macOS: `brew install ta-lib`
  - Windows: [Download prebuilt binary](https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/siddjoshi/StockJarvis.git
   cd StockJarvis
   
   # Switch to the refactored architecture branch
   git checkout refactor/simplified-architecture
   ```

2. **Create virtual environment**
   ```bash
   # Linux/macOS
   python -m venv venv
   source venv/bin/activate
   
   # Windows
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

### Configuration

1. **Copy the environment template**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your credentials**
   ```dotenv
   # Database
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=your_username
   DB_PASSWORD=your_password
   DB_DATABASE=stockjarvis
   
   # Redis
   REDIS_HOST=localhost
   REDIS_PORT=6379
   
   # Broker (Zerodha)
   ZERODHA_API_KEY=your_kite_api_key
   ZERODHA_API_SECRET=your_kite_api_secret
   
   # Data Provider
   QUANDL_API_KEY=your_quandl_api_key
   
   # Trading Mode (IMPORTANT: Start with paper!)
   TRADING_MODE=paper
   TRADING_CAPITAL=100000.0
   TRADING_MAX_POSITIONS=5
   TRADING_RISK_PER_TRADE=0.02
   ```

3. **Generate a secure secret key**
   ```bash
   # Linux/macOS
   openssl rand -hex 32
   
   # Use the output as APP_SECRET_KEY in .env
   ```

### Database Setup

1. **Create the database**
   ```bash
   mysql -u root -p < schema.sql
   ```

2. **Or initialize via Python**
   ```python
   from data.repository import repository
   repository.create_tables()
   ```

3. **Add initial symbols**
   ```python
   from data.repository import repository
   from data.models import Exchange
   
   # Add a symbol
   repository.add_symbol(
       symbol="RELIANCE",
       company_name="Reliance Industries Ltd",
       exchange=Exchange.NSE,
       is_fno=True,
       is_nifty50=True,
       sector="Energy"
   )
   ```

---

## 📖 Usage

### Running the API Server

```bash
# Development mode with auto-reload
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4

# Or using the module directly
python -m api.main
```

**Access Points:**
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/api/docs
- ReDoc: http://localhost:8000/api/redoc
- Health Check: http://localhost:8000/health

### Running Celery Workers

```bash
# Terminal 1: Start Celery Worker
celery -A workers.celery_app worker --loglevel=info --concurrency=4

# Terminal 2: Start Celery Beat (Scheduler)
celery -A workers.celery_app beat --loglevel=info

# Terminal 3: Start Flower (Monitoring Dashboard)
celery -A workers.celery_app flower --port=5555
```

**Flower Dashboard:** http://localhost:5555

### Using the Scanner

```python
from core.scanner import create_eod_scanner
from strategies.eod_strategies import (
    SMAGoldenCrossStrategy,
    RSIOversoldStrategy,
    MACDCrossoverStrategy,
    BollingerBreakoutStrategy
)
from core.strategy_engine import registry

# Register strategies
registry.register(SMAGoldenCrossStrategy())
registry.register(RSIOversoldStrategy())
registry.register(MACDCrossoverStrategy())
registry.register(BollingerBreakoutStrategy())

# Create scanner for EOD analysis
scanner = create_eod_scanner()

# Run scan across all F&O symbols
signals = scanner.scan(parallel=True)

# Process signals
for signal in signals:
    print(f"📊 {signal.action.value} {signal.symbol}")
    print(f"   Price: ₹{signal.price:.2f}")
    print(f"   Stop Loss: ₹{signal.stop_loss:.2f}")
    print(f"   Target: ₹{signal.target:.2f}")
    print(f"   R:R Ratio: {signal.risk_reward_ratio:.2f}")
    print(f"   Confidence: {signal.confidence:.0%}")
    print(f"   Reason: {signal.reason}")
    print()
```

### Creating Custom Strategies

```python
from typing import Optional
import pandas as pd

from core.strategy_engine import Strategy, SignalOutput
from data.models import OrderAction
from indicators.technical import sma, rsi, macd

class MyCustomStrategy(Strategy):
    """
    Custom trading strategy template.
    """
    
    def __init__(self):
        super().__init__(
            name="My_Custom_Strategy",
            description="Description of your strategy",
            parameters={
                "fast_period": 10,
                "slow_period": 20,
                "rsi_period": 14,
            }
        )
        self.fast_period = 10
        self.slow_period = 20
        self.rsi_period = 14
    
    def get_required_history(self) -> int:
        """Return minimum bars needed for calculations."""
        return max(self.slow_period, self.rsi_period) + 10
    
    def generate_signal(
        self, 
        symbol: str, 
        data: pd.DataFrame
    ) -> Optional[SignalOutput]:
        """
        Generate trading signal based on strategy logic.
        
        Args:
            symbol: Stock ticker
            data: DataFrame with OHLCV columns
            
        Returns:
            SignalOutput if signal generated, None otherwise
        """
        # Calculate indicators
        fast_sma = sma(data['close'], self.fast_period)
        slow_sma = sma(data['close'], self.slow_period)
        rsi_values = rsi(data['close'], self.rsi_period)
        
        # Get current values
        current_price = data['close'].iloc[-1]
        current_fast = fast_sma.iloc[-1]
        current_slow = slow_sma.iloc[-1]
        current_rsi = rsi_values.iloc[-1]
        
        # Previous values for crossover detection
        prev_fast = fast_sma.iloc[-2]
        prev_slow = slow_sma.iloc[-2]
        
        # BUY condition: Fast SMA crosses above Slow SMA + RSI not overbought
        if prev_fast <= prev_slow and current_fast > current_slow and current_rsi < 70:
            return SignalOutput(
                action=OrderAction.BUY,
                symbol=symbol,
                price=current_price,
                stop_loss=current_price * 0.95,  # 5% stop loss
                target=current_price * 1.10,     # 10% target
                confidence=0.70,
                reason=f"SMA crossover: {current_fast:.2f} > {current_slow:.2f}, RSI: {current_rsi:.1f}"
            )
        
        # SELL condition: Fast SMA crosses below Slow SMA + RSI not oversold
        elif prev_fast >= prev_slow and current_fast < current_slow and current_rsi > 30:
            return SignalOutput(
                action=OrderAction.SELL,
                symbol=symbol,
                price=current_price,
                stop_loss=current_price * 1.05,
                target=current_price * 0.90,
                confidence=0.70,
                reason=f"SMA crossover: {current_fast:.2f} < {current_slow:.2f}, RSI: {current_rsi:.1f}"
            )
        
        return None

# Register the strategy
from core.strategy_engine import registry
registry.register(MyCustomStrategy())
```

---

## 🔌 API Reference

### Authentication

All API endpoints require JWT authentication.

```bash
# Login to get token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}'

# Use token in requests
curl -X GET http://localhost:8000/api/positions \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Endpoints Overview

| Module | Endpoints | Description |
|--------|-----------|-------------|
| **Auth** | 4 | Login, register, refresh token, profile |
| **Strategies** | 7 | List, get, create, update, delete, execute, available |
| **Positions** | 5 | List, get, update stop-loss, close, portfolio summary |
| **Signals** | 5 | List, get, generate, delete, recent |
| **Symbols** | 7 | List, get, add, update, delete, prices, latest price |
| **Backtests** | 5 | Run, list, get, trades, delete |
| **Risk** | 6 | Portfolio risk, position size, circuit breaker status/reset/trigger, correlation |
| **Orders** | 5 | List, get, create, cancel, update status |

### Key Endpoints

#### Strategies

```http
GET    /api/strategies                    # List all strategies
POST   /api/strategies                    # Register new strategy
GET    /api/strategies/{id}               # Get strategy details
PATCH  /api/strategies/{id}               # Update strategy
DELETE /api/strategies/{id}               # Delete strategy
POST   /api/strategies/execute            # Execute strategy on symbols
GET    /api/strategies/available          # List available plugin strategies
```

#### Positions

```http
GET    /api/positions                     # List positions (with filters)
GET    /api/positions/portfolio           # Portfolio summary with metrics
GET    /api/positions/{id}                # Get position details
PATCH  /api/positions/{id}/stop-loss      # Update stop loss
POST   /api/positions/{id}/close          # Close position
```

#### Signals

```http
GET    /api/signals                       # List signals (with filters)
GET    /api/signals/recent                # Get signals from last N hours
POST   /api/signals/generate              # Manually create signal
GET    /api/signals/{id}                  # Get signal details
DELETE /api/signals/{id}                  # Delete unexecuted signal
```

#### Risk Management

```http
GET    /api/risk/portfolio                # Portfolio risk metrics
GET    /api/risk/position-size            # Calculate recommended position size
GET    /api/risk/circuit-breaker          # Get circuit breaker status
POST   /api/risk/circuit-breaker/reset    # Reset circuit breaker
POST   /api/risk/circuit-breaker/trigger  # Manually trigger circuit breaker
GET    /api/risk/correlation/{s1}/{s2}    # Calculate position correlation
```

#### Backtesting

```http
POST   /api/backtests                     # Execute backtest
GET    /api/backtests                     # List backtest results
GET    /api/backtests/{id}                # Get backtest details
GET    /api/backtests/{id}/trades         # Get trade history
DELETE /api/backtests/{id}                # Delete backtest result
```

---

## 🐳 Docker Deployment

### Quick Start with Docker

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Edit .env with your credentials
# Generate secret key: openssl rand -hex 32

# 3. Build and start all services
docker-compose up -d --build

# 4. Check status
docker-compose ps

# 5. View logs
docker-compose logs -f
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| `mysql` | 3306 | MariaDB 10.11 database |
| `redis` | 6379 | Redis 7 cache/queue |
| `api` | 8000 | FastAPI application |
| `celery_worker` | - | Background task processor |
| `celery_beat` | - | Task scheduler |
| `flower` | 5555 | Celery monitoring dashboard |

### Management Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart specific service
docker-compose restart api

# View logs
docker-compose logs -f api

# Scale workers
docker-compose up -d --scale celery_worker=4

# Create database backup
docker-compose exec mysql mysqldump -u root -p stockjarvis > backup.sql

# Clean everything (WARNING: removes data!)
docker-compose down -v --rmi all
```

### Resource Requirements

| Service | Memory Limit | CPU Limit |
|---------|--------------|-----------|
| MySQL | 2GB | 2.0 |
| Redis | 512MB | 0.5 |
| API | 1GB | 1.0 |
| Celery Worker | 2GB | 2.0 |
| Celery Beat | 512MB | 0.5 |
| Flower | 256MB | 0.25 |

**Minimum Total**: 4GB RAM, 4 CPU cores, 10GB disk space

---

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov --cov-report=html

# Run specific test file
pytest tests/unit/test_risk_manager.py

# Run specific test
pytest tests/unit/test_risk_manager.py::test_fixed_fractional_sizing

# Run by marker
pytest -m unit          # Only unit tests
pytest -m integration   # Only integration tests
pytest -m asyncio       # Only async tests

# Verbose output
pytest -v

# Show print statements
pytest -s
```

### Test Categories

- **Unit Tests** (`tests/unit/`) - Fast, isolated component tests
- **Integration Tests** (`tests/integration/`) - Multi-component tests with database
- **Mocks** (`tests/mocks/`) - Mock objects for external services

### Coverage Target

- **Minimum**: 80% overall coverage
- **Core modules**: 90%+ coverage

### Example Test

```python
import pytest
from core.risk_manager import RiskManager
from data.models import OrderAction

@pytest.mark.unit
def test_position_size_calculation(test_db_session, sample_symbol):
    """Test position sizing with fixed fractional method."""
    risk_manager = RiskManager(test_db_session)
    
    signal_data = {
        "action": OrderAction.BUY,
        "price": 2500.0,
        "stop_loss": 2400.0,
        "target": 2700.0
    }
    
    account_info = {"balance": 100000.0}
    
    recommendation = risk_manager.calculate_position_size(
        symbol="RELIANCE",
        signal_data=signal_data,
        account_info=account_info,
        method="fixed_fractional"
    )
    
    assert recommendation.quantity > 0
    assert recommendation.risk_reward_ratio >= 2.0
    assert recommendation.passed_checks
```

---

## ⚙️ Configuration Reference

### Environment Variables

#### Database Configuration
```dotenv
DB_HOST=localhost           # Database host
DB_PORT=3306               # Database port
DB_USER=your_username      # Database username
DB_PASSWORD=your_password  # Database password
DB_DATABASE=stockjarvis    # Database name
DB_POOL_SIZE=5             # Connection pool size
```

#### Redis Configuration
```dotenv
REDIS_HOST=localhost       # Redis host
REDIS_PORT=6379           # Redis port
REDIS_DB=0                # Redis database number
REDIS_PASSWORD=           # Redis password (optional)
```

#### Trading Configuration
```dotenv
TRADING_MODE=paper                    # paper or live
TRADING_CAPITAL=100000.0             # Total trading capital
TRADING_MAX_POSITIONS=5              # Maximum concurrent positions
TRADING_RISK_PER_TRADE=0.02          # Risk per trade (2%)
TRADING_MIN_STRATEGY_ACCURACY=0.65   # Minimum strategy win rate (65%)
TRADING_MIN_RISK_REWARD=2.0          # Minimum risk:reward ratio
```

#### Broker Configuration (Zerodha)
```dotenv
ZERODHA_API_KEY=your_api_key
ZERODHA_API_SECRET=your_api_secret
ZERODHA_ACCESS_TOKEN=               # Generated after OAuth login
ZERODHA_REDIRECT_URL=http://localhost:8000/broker/callback
```

#### Data Provider Configuration
```dotenv
QUANDL_API_KEY=your_quandl_api_key
```

#### Notification Configuration
```dotenv
NOTIFICATION_SENDGRID_API_KEY=your_sendgrid_key
NOTIFICATION_EMAIL_FROM=jarvis@yourdomain.com
NOTIFICATION_EMAIL_TO=admin@example.com
NOTIFICATION_WAY2SMS_USERNAME=your_username
NOTIFICATION_WAY2SMS_PASSWORD=your_password
NOTIFICATION_SMS_TO=9876543210
```

#### Application Configuration
```dotenv
APP_ENV=development              # development, staging, production
APP_DEBUG=True                   # Enable debug mode
APP_LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR, CRITICAL
APP_SECRET_KEY=your-secret-key  # JWT signing key (use openssl rand -hex 32)
APP_API_HOST=0.0.0.0            # API server host
APP_API_PORT=8000               # API server port
APP_API_WORKERS=4               # Number of API workers
```

#### Scheduled Tasks (Cron Format)
```dotenv
APP_DATA_UPDATE_SCHEDULE=0 18 * * 1-5      # 6 PM weekdays
APP_SCANNER_SCHEDULE=30 9,15 * * 1-5       # 9:30 AM & 3 PM weekdays
```

---

## 💾 Database Schema

### Tables Overview

| Table | Description |
|-------|-------------|
| `symbols` | Stock master data (ticker, company, exchange, categories) |
| `prices` | Unified OHLCV data for all symbols and timeframes |
| `strategies` | Registered trading strategies with backtest metrics |
| `signals` | Trading signals generated by strategies |
| `orders` | Orders placed with broker |
| `positions` | Current and historical positions |
| `backtest_results` | Backtest performance metrics |
| `alerts` | System alerts and notifications |

### Entity Relationship

```
symbols (1) ──────── (N) prices
    │
    ├─────── (N) signals ──────── (N) strategies
    │
    ├─────── (N) positions
    │
    └─────── (N) orders ──────── (1) signals
                  │
                  └──────── (1) backtest_results
```

### Key Indexes

- `prices`: `(symbol_id, timestamp, timeframe)` - Fast price lookups
- `signals`: `(symbol_id, created_at)`, `(strategy_id, created_at)`
- `positions`: `(symbol_id, is_open)`
- `orders`: `(status, created_at)`, `(broker_order_id)`

---

## 🛡 Risk Management

### Position Sizing Methods

| Method | Description | Use Case |
|--------|-------------|----------|
| **Fixed Fractional** | Risk fixed % of capital per trade | Standard approach |
| **Kelly Criterion** | Optimal sizing based on win rate | Aggressive trading |
| **Risk Parity** | Equal risk contribution | Portfolio balancing |
| **ATR-Based** | Size based on volatility | Volatility adjustment |

### Circuit Breakers

Automatic trading halt when thresholds are exceeded:

| Threshold | Default | Description |
|-----------|---------|-------------|
| Max Daily Drawdown | 5% | Maximum loss per day |
| Max Total Drawdown | 20% | Maximum loss from peak |
| Max Consecutive Losses | 5 | Maximum losing streak |
| Cooldown Period | 24 hours | Time before reset allowed |

### Portfolio Limits

| Limit | Default | Description |
|-------|---------|-------------|
| Max Open Positions | 5 | Maximum concurrent positions |
| Max Single Position | 20% | Maximum exposure per position |
| Max Total Exposure | 80% | Maximum total portfolio exposure |
| Max Per Symbol | 2 | Maximum positions per symbol |

---

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Write tests** for your changes
4. **Ensure tests pass**: `pytest`
5. **Commit with descriptive messages**
6. **Push to your branch**: `git push origin feature/amazing-feature`
7. **Open a Pull Request**

### Coding Standards

- Use Python type hints everywhere
- Write docstrings for all public functions
- Follow PEP 8 style guidelines
- Keep it simple - avoid over-engineering
- Never hardcode credentials

---

## 🗺 Roadmap

### Current Status: 🚧 Active Development

### Phase 1 (P0) - Foundation ✅
- [x] Core architecture refactor
- [x] Normalized database schema
- [x] Strategy framework with plugin architecture
- [x] Technical indicators library
- [x] FastAPI REST API
- [x] Docker deployment setup
- [x] Testing framework

### Phase 2 (P0) - In Progress
- [ ] Complete backtester implementation
- [ ] Zerodha broker adapter
- [ ] Position reconciliation with broker
- [ ] Alembic database migrations

### Phase 3 (P1) - Planned
- [ ] Data provider abstraction
- [ ] Watchlist management
- [ ] Enhanced notifications (email/SMS)
- [ ] JWT refresh token flow
- [ ] Rate limiting

### Phase 4 (P2) - Future
- [ ] Web dashboard UI
- [ ] Machine learning integration
- [ ] Multi-timeframe analysis
- [ ] Advanced order types (bracket, trailing SL)
- [ ] Mobile app / PWA

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Disclaimer

**IMPORTANT:** This software is for educational and research purposes only. 

- **Always test in paper trading mode first**
- **Never risk more than you can afford to lose**
- **Past performance does not guarantee future results**
- **The authors are not responsible for any financial losses**

Trading in financial markets involves substantial risk. Please consult with a qualified financial advisor before making any investment decisions.

---

## 📞 Support

- **Documentation**: [README_REFACTOR.md](README_REFACTOR.md)
- **Testing Guide**: [TESTING.md](TESTING.md)
- **Docker Guide**: [DOCKER_DEPLOYMENT.md](DOCKER_DEPLOYMENT.md)
- **API Reference**: [API_ROUTES_SUMMARY.md](API_ROUTES_SUMMARY.md)
- **Issues**: [GitHub Issues](https://github.com/siddjoshi/StockJarvis/issues)

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/siddjoshi">siddjoshi</a>
</p>

<p align="center">
  <i>StockJarvis - Your AI-Powered Trading Companion</i>
</p>
