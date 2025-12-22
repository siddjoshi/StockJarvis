# StockJarvis AI Agent Instructions

An automated algorithmic trading system for Indian stock markets (NSE/BSE) with multi-broker support, strategy framework, risk management, and backtesting.

> ⚠️ **This is a LIVE-TRADING SYSTEM** — treat all changes with production-level rigor. Safety, correctness, and operational clarity are paramount.

---

## 🏗️ Architecture Overview

**3-Layer Modular Design** with clear separation of concerns:

```
API Layer (FastAPI) → Core Business Logic → Data Layer (SQLAlchemy ORM)
                           ↓
        Scanner, Strategy Engine, Risk Manager, Position Tracker
                           ↓
              MySQL Database + Redis Queue + Broker API
```

### Key Components

| Component | Location | Responsibility |
|-----------|----------|----------------|
| **Strategy Engine** | `core/strategy_engine.py` | Abstract `Strategy` base class with plugin registry. Implement `generate_signal()` and `get_required_history()`. |
| **Scanner** | `core/scanner.py` | Unified scanner for EOD/Intraday. Runs strategies across symbols with parallel execution. |
| **Risk Manager** | `core/risk_manager.py` | Position sizing (Fixed Fractional, Kelly, Risk Parity, ATR), stop loss, portfolio limits, circuit breakers. |
| **Repository** | `data/repository.py` | Single data access layer. Always use `with repository.get_session() as session:` |
| **Models** | `data/models.py` | Normalized schema. Single `prices` table for all symbols/timeframes. |

### Project Structure (Target State)

```
StockJarvis/
├── api/                    # REST API (FastAPI) - External interface ONLY
│   ├── routes/             # Endpoint handlers
│   └── schemas/            # Pydantic request/response models
├── core/                   # Business logic - NO external I/O here
│   ├── strategy_engine.py  # Strategy base class + registry
│   ├── scanner.py          # Strategy execution engine
│   ├── risk_manager.py     # Risk checks + position sizing
│   ├── position_tracker.py # Position monitoring
│   └── stop_loss_manager.py
├── strategies/             # Strategy implementations (PRODUCTION)
│   └── eod_strategies.py   # Validated, tradeable strategies
├── research/               # Experimental strategies (NOT for production)
├── data/                   # Data access layer
│   ├── models.py           # SQLAlchemy ORM models
│   └── repository.py       # Database operations
├── indicators/             # Technical indicators (pure functions)
│   └── technical.py        # SMA, RSI, MACD, etc.
├── BrokerModules/          # Broker adapters
│   └── Zerodha/            # Kite Connect integration
├── config/                 # Configuration management
│   ├── settings.py         # Pydantic settings
│   └── risk_config.py      # Risk parameters
├── workers/                # Background tasks (Celery)
└── tests/                  # Test suite
    ├── unit/               # Fast, isolated tests
    └── integration/        # Multi-component tests
```

**Separation Rules**:
- `strategies/` = Production-validated strategies only
- `research/` = Experiments, backtests, notebooks (never import in production)
- `core/` = Pure business logic (no HTTP, no broker calls)
- `api/` = HTTP interface only (thin layer over core)

---

## 🔑 Critical Developer Workflows

### Running the Application

```bash
# Development mode (always start here)
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Celery worker (separate terminal)
celery -A workers.celery_app worker --loglevel=info --concurrency=4

# Celery beat scheduler (separate terminal)
celery -A workers.celery_app beat --loglevel=info

# Flower monitoring dashboard (optional)
celery -A workers.celery_app flower --port=5555
```

### Docker Deployment

```bash
# Build and start all services (MySQL, Redis, API, Celery, Flower)
docker-compose up -d --build

# View logs for specific service
docker-compose logs -f api

# Scale workers
docker-compose up -d --scale celery_worker=4
```

### Testing

```bash
# Run all tests with coverage
pytest --cov

# Run specific category
pytest -m unit              # Fast unit tests only
pytest -m integration       # Integration tests only

# Run specific file or test
pytest tests/unit/test_risk_manager.py::test_fixed_fractional_sizing

# Coverage target: 80% minimum, 90%+ for core modules
```

### Database Operations

```python
# ALWAYS use repository context manager - never create raw sessions
from data.repository import repository

# Read operation
with repository.get_session() as session:
    symbols = repository.get_fno_symbols()

# Write operation (auto-commits on success, rolls back on error)
with repository.get_session() as session:
    repository.add_signal(strategy_name="...", symbol="...", ...)
```

---

## 📐 Python Coding Guidelines

### A. Coding Standards & Style

**Python Version**: 3.11+ required

**Naming Conventions**:
| Type | Convention | Example |
|------|------------|---------|
| Modules | `snake_case` | `risk_manager.py`, `eod_strategies.py` |
| Classes | `PascalCase` | `RiskManager`, `SMAGoldenCrossStrategy` |
| Functions | `snake_case` | `calculate_position_size()`, `generate_signal()` |
| Constants | `UPPER_SNAKE` | `MAX_POSITIONS`, `DEFAULT_STOP_LOSS_PCT` |
| Strategy names | `PascalCase_With_Underscores` | `"SMA_GoldenCross"`, `"RSI_Oversold"` |

**Type Hints** (CRITICAL for trading code):
```python
# ✅ REQUIRED for all public functions
def calculate_position_size(
    symbol: str,
    price: float,
    stop_loss: float,
    capital: float
) -> PositionSizeResult:
    ...

# ✅ Use Optional for nullable returns
def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
    ...

# ✅ Use Decimal for money (when precision critical)
from decimal import Decimal
order_value: Decimal = Decimal("10000.50")
```

**Docstrings** (Required for):
- All public classes and methods
- Strategy `generate_signal()` methods (explain logic)
- Risk management functions
- Anything handling money or orders

```python
def place_order(self, symbol: str, quantity: int, price: float) -> Order:
    """
    Place order with broker.
    
    Args:
        symbol: Stock ticker (e.g., "RELIANCE")
        quantity: Number of shares (positive for buy, negative for sell)
        price: Limit price in INR
        
    Returns:
        Order object with broker_order_id populated
        
    Raises:
        BrokerConnectionError: If broker API unreachable
        InsufficientFundsError: If margin insufficient
        
    Note:
        This method is IDEMPOTENT - duplicate calls with same
        client_order_id will return existing order.
    """
```

### B. Trading-Specific Best Practices

#### 🚨 CRITICAL: Order Placement Safety

```python
# ✅ CORRECT: Idempotent order placement
def place_order(self, signal: Signal) -> Order:
    # Generate deterministic order ID from signal
    client_order_id = f"{signal.id}_{signal.symbol}_{signal.timestamp.isoformat()}"
    
    # Check if order already exists
    existing = self.get_order_by_client_id(client_order_id)
    if existing:
        logger.info(f"Order already exists: {client_order_id}")
        return existing
    
    # Place new order
    return self._execute_order(client_order_id, signal)

# ❌ WRONG: Non-idempotent (can create duplicates on retry)
def place_order(self, signal: Signal) -> Order:
    return broker.place_order(signal.symbol, signal.quantity, signal.price)
```

#### Time Handling (Market Time vs System Time)

```python
from datetime import datetime
import pytz

IST = pytz.timezone('Asia/Kolkata')

# ✅ CORRECT: Always use market timezone for trading logic
def is_market_open() -> bool:
    now_ist = datetime.now(IST)
    market_open = now_ist.replace(hour=9, minute=15, second=0)
    market_close = now_ist.replace(hour=15, minute=30, second=0)
    return market_open <= now_ist <= market_close

# ✅ CORRECT: Store timestamps in UTC, display in IST
order.created_at = datetime.utcnow()  # Storage
display_time = order.created_at.replace(tzinfo=pytz.UTC).astimezone(IST)  # Display

# ❌ WRONG: Naive datetime comparison
if datetime.now() > some_market_time:  # Which timezone?!
```

#### Floating-Point Safety

```python
from decimal import Decimal, ROUND_DOWN

# ✅ CORRECT: Use Decimal for price comparisons
def prices_equal(p1: float, p2: float, tolerance: float = 0.01) -> bool:
    return abs(p1 - p2) < tolerance

# ✅ CORRECT: Round quantities to lot size
def round_to_lot_size(quantity: int, lot_size: int = 1) -> int:
    return (quantity // lot_size) * lot_size

# ✅ CORRECT: Use Decimal for position value calculations
position_value = Decimal(str(quantity)) * Decimal(str(price))

# ❌ WRONG: Direct float comparison
if current_price == target_price:  # Almost never true!
```

#### Avoiding Look-Ahead Bias (Backtesting)

```python
# ✅ CORRECT: Signal uses only data available at signal time
def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
    # Use iloc[-1] for current bar, iloc[-2] for previous
    current_close = data['close'].iloc[-1]
    prev_close = data['close'].iloc[-2]
    
    # Calculate indicator on data EXCLUDING current bar for entry
    sma = data['close'].iloc[:-1].rolling(20).mean().iloc[-1]
    
    if current_close > sma:
        return SignalOutput(price=current_close, ...)

# ❌ WRONG: Using future data
def generate_signal(self, symbol: str, data: pd.DataFrame):
    # This "knows" tomorrow's high!
    next_day_high = data['high'].iloc[-1]  # If data includes future
    if current_price < next_day_high * 0.95:
        return SignalOutput(...)
```

### C. Error Handling & Resilience

#### When to Fail Fast vs Fail Safe

| Scenario | Behavior | Example |
|----------|----------|---------|
| **Invalid order parameters** | FAIL FAST | Negative quantity, invalid symbol |
| **Risk limit exceeded** | FAIL FAST | Position too large, drawdown limit |
| **Broker connection timeout** | FAIL SAFE + Retry | Network blip, retry 3x |
| **Data feed gap** | FAIL SAFE + Alert | Log warning, use last known price |
| **Strategy exception** | FAIL SAFE + Skip | Continue with other strategies |

```python
# ✅ CORRECT: Fail fast on invalid orders
def validate_order(order: Order) -> None:
    if order.quantity <= 0:
        raise InvalidOrderError(f"Quantity must be positive: {order.quantity}")
    if order.price <= 0:
        raise InvalidOrderError(f"Price must be positive: {order.price}")
    # Validation failures should NEVER be retried

# ✅ CORRECT: Fail safe with retry on transient errors
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(BrokerConnectionError)
)
def fetch_positions(self) -> List[Position]:
    return self.broker.get_positions()

# ✅ CORRECT: Circuit breaker for repeated failures
class TradingCircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_timeout: int = 300):
        self.failures = 0
        self.threshold = failure_threshold
        self.is_open = False
        
    def record_failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.is_open = True
            logger.critical("Circuit breaker OPEN - trading halted")
```

#### Custom Exception Hierarchy

```python
# Define in core/exceptions.py
class StockJarvisError(Exception):
    """Base exception for all trading errors."""
    pass

class OrderError(StockJarvisError):
    """Order-related errors."""
    pass

class InvalidOrderError(OrderError):
    """Invalid order parameters - do not retry."""
    pass

class OrderExecutionError(OrderError):
    """Order execution failed - may retry."""
    pass

class RiskLimitError(StockJarvisError):
    """Risk limit exceeded - fail fast."""
    pass

class DataError(StockJarvisError):
    """Data quality or availability issue."""
    pass
```

### D. Configuration & Secrets

**CRITICAL**: All config in `.env` → Pydantic settings. Never hardcode.

```python
from config import settings

# ✅ CORRECT: Access via settings
db_url = settings.db.url
trading_mode = settings.trading.mode  # 'paper' or 'live'
api_key = settings.zerodha.api_key

# ❌ WRONG: Hardcoded values
API_KEY = "xxxx-your-key-here"  # NEVER!
MAX_POSITIONS = 5  # Should be in config
```

**Environment-Based Config**:
```python
# .env.development
TRADING_MODE=paper
APP_DEBUG=true
DB_DATABASE=stockjarvis_dev

# .env.production  
TRADING_MODE=live
APP_DEBUG=false
DB_DATABASE=stockjarvis_prod
```

### E. Logging, Metrics & Observability

**Logging Levels**:
| Level | Use For |
|-------|---------|
| `DEBUG` | Strategy calculations, indicator values |
| `INFO` | Signal generated, order placed, position opened |
| `WARNING` | Data gaps, retry attempts, approaching limits |
| `ERROR` | Failed operations, exceptions caught |
| `CRITICAL` | Circuit breaker triggered, system halt |

**MUST Log in Trading Systems**:
```python
# ✅ Order lifecycle events
logger.info(f"ORDER_PLACED: {order.id} {order.action} {order.symbol} qty={order.quantity} price={order.price}")
logger.info(f"ORDER_FILLED: {order.id} filled_qty={order.filled_quantity} avg_price={order.average_price}")
logger.info(f"ORDER_REJECTED: {order.id} reason={order.error_message}")

# ✅ Position changes
logger.info(f"POSITION_OPENED: {symbol} qty={quantity} entry={entry_price}")
logger.info(f"POSITION_CLOSED: {symbol} pnl={realized_pnl} holding_period={days}")

# ✅ Risk events
logger.warning(f"RISK_WARNING: Daily drawdown at {drawdown:.2%}")
logger.critical(f"CIRCUIT_BREAKER: Trading halted - {reason}")

# ✅ Include correlation IDs
logger.info(f"Signal generated", extra={
    "signal_id": signal.id,
    "strategy": strategy.name,
    "symbol": symbol,
    "action": signal.action.value
})
```

---

## 🎯 Strategy Development Pattern

```python
from core.strategy_engine import Strategy, SignalOutput, registry
from data.models import OrderAction

class MyStrategy(Strategy):
    def __init__(self):
        super().__init__(
            name="My_Strategy",  # Unique name with underscores
            description="...",
            parameters={"param1": value}
        )
    
    def get_required_history(self) -> int:
        return 50  # Minimum bars needed
    
    def generate_signal(self, symbol: str, data: pd.DataFrame) -> Optional[SignalOutput]:
        # 1. Calculate indicators using indicators.technical module
        # 2. Check conditions
        # 3. Return SignalOutput with price, stop_loss, target, confidence, reason
        # 4. Signal validates automatically (R:R >= 2.0, confidence >= 0.5)
        pass

# Register globally
registry.register(MyStrategy())
```

**Signal Validation**: Signals auto-validate via `SignalOutput.is_valid()`:
- Risk:reward ratio >= `settings.trading.min_risk_reward` (default 2.0)
- Confidence >= 0.5
- Price levels consistent with action (BUY: stop < price < target; SELL: target < price < stop)

### Database Schema Patterns

**Enum-Driven Design**: Use SQLAlchemy enums for type safety
```python
from data.models import OrderAction, OrderStatus, Timeframe, TradingMode

# These are enums, not strings
action = OrderAction.BUY  # NOT "BUY"
status = OrderStatus.PENDING
timeframe = Timeframe.DAILY
```

**Relationship Navigation**:
```python
symbol = session.query(Symbol).first()
prices = symbol.prices  # One-to-many relationship
latest_signal = symbol.signals[0]  # Access related signals
```

---

## 🔍 Code Review Guidelines

### A. High-Risk Areas (MUST Review Carefully)

| Area | Risk | What to Check |
|------|------|---------------|
| **Order execution** | Duplicate orders, wrong quantity | Idempotency, validation, error handling |
| **Risk checks** | Exceeded limits, blown account | All paths check limits, circuit breakers work |
| **Position sizing** | Over-leverage, wrong calculations | Math correctness, edge cases (0, negative) |
| **Stop loss logic** | Stops not triggering, wrong prices | Time-in-force, market hours, price types |
| **Retry logic** | Infinite loops, duplicate actions | Max retries, backoff, idempotency |
| **Time-sensitive code** | Race conditions, stale data | Market hours, timezone handling |

### B. Review Checklist (Ask These Questions)

**Order Safety**:
- [ ] Could this place duplicate orders on retry?
- [ ] What happens if broker returns timeout but order was placed?
- [ ] Is quantity validated (positive, within limits, lot size)?
- [ ] Is there a maximum order value check?

**Failure Modes**:
- [ ] Could this fail silently (swallow exceptions)?
- [ ] What happens if the database is unavailable?
- [ ] What happens if the broker API is down?
- [ ] Are all error paths logged with context?

**Strategy Correctness**:
- [ ] Is strategy behavior deterministic (same input → same output)?
- [ ] Could this have look-ahead bias?
- [ ] Are indicators calculated correctly (check math)?
- [ ] Is this safe to run in live trading?

**Data Quality**:
- [ ] What if data has gaps or missing values?
- [ ] What if data is delayed or stale?
- [ ] Are NaN/None values handled?

### C. What MUST Block a Merge

🚫 **NEVER MERGE** if:
- Order execution code lacks idempotency
- Risk limits can be bypassed
- Secrets/credentials in code
- No error handling on broker calls
- Strategy modifies global state
- Missing validation on user inputs
- Breaking change to signal format without migration

⚠️ **Merge with Tech Debt Ticket** if:
- Missing tests (but code is safe)
- Incomplete logging
- Hardcoded non-sensitive values
- Suboptimal performance (but correct)
- Missing docstrings

### D. Safe Refactoring Patterns

**Modifying Existing Strategies**:
```python
# ✅ CORRECT: Version strategies, don't modify in place
class RSI_Oversold_V2(Strategy):  # New version
    """Improved RSI with volume confirmation."""
    ...

# Keep old version for comparison
class RSI_Oversold_V1(Strategy):  # Original
    ...

# ✅ CORRECT: Feature flag for gradual rollout
if settings.features.use_new_rsi_strategy:
    registry.register(RSI_Oversold_V2())
else:
    registry.register(RSI_Oversold_V1())
```

**Backward Compatibility Rules**:
- Never change signal format without migration
- Never remove fields from API responses
- Add new optional parameters with defaults
- Keep old endpoints, deprecate with warnings

### E. Test Requirements for PRs

| Change Type | Test Requirement |
|-------------|------------------|
| New strategy | Unit tests + backtest results |
| Order execution | Unit + integration + manual paper trade |
| Risk management | Unit tests for all edge cases |
| Bug fix | Regression test proving fix |
| API endpoint | Request/response tests |
| Config change | Validation tests |

**When Tests Can Be Deferred** (document in PR):
- Urgent production fix (create ticket for tests)
- Pure refactor with existing coverage
- Documentation-only changes

---

## 🔌 Integration Points & External Dependencies

### Broker Integration (Zerodha Kite)

- **Location**: `BrokerModules/Zerodha/`
- **Auth Flow**: OAuth → request token → access token (stored in `.env`)
- **Paper Trading**: Default mode. Use `repository.add_order()` with `trading_mode=TradingMode.PAPER`
- **Live Trading**: Requires `ZERODHA_ACCESS_TOKEN` in `.env` and `TRADING_MODE=live`

### Data Providers

**Primary**: Quandl (requires `QUANDL_API_KEY` in `.env`)
**Fallback**: NSEPy, yfinance (no key needed)
**Storage**: All data normalized in `prices` table with `timeframe` column

### Task Queue (Celery + Redis)

- **Broker URL**: `redis://localhost:6379/0` (configurable via `REDIS_*` env vars)
- **Task Types**: Data collection, signal generation, position monitoring, maintenance
- **Scheduling**: Cron-like schedules in `APP_DATA_UPDATE_SCHEDULE`, `APP_SCANNER_SCHEDULE`

---

## 🎯 Testing Conventions

### Fixture Usage

```python
# Standard fixtures from conftest.py
def test_something(test_db_session, sample_symbol, sample_strategy):
    # test_db_session: SQLite in-memory DB for isolation
    # sample_symbol: Pre-created Symbol(symbol="RELIANCE", ...)
    # sample_strategy: Pre-created Strategy(name="RSI_MACD_Combo", ...)
    pass

# Async fixtures for async code
@pytest.mark.asyncio
async def test_async_code(test_async_db_session):
    # Use await for async operations
    pass
```

### Test Organization

- **Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.asyncio`
- **Naming**: `test_<what>_<condition>` (e.g., `test_calculate_pnl_long_position_profit`)
- **AAA Pattern**: Arrange → Act → Assert (clear separation)
- **One Assert Per Test**: When possible, test one behavior per test function

### Mocking External Services

```python
# Mock broker API (avoid real API calls in tests)
@patch('broker_module.KiteConnect')
def test_order_placement(mock_kite):
    mock_kite.place_order.return_value = {"order_id": "123"}
    # Test logic...
```

### Testing Guidelines by Component

| Component | Test Type | What to Test |
|-----------|-----------|--------------|
| Strategies | Unit + Backtest | Signal generation, edge cases, historical performance |
| Risk Manager | Unit | All position sizing methods, limit checks, circuit breakers |
| Repository | Integration | CRUD operations, transactions, edge cases |
| API Routes | Integration | Request validation, auth, response format |
| Broker Adapter | Unit (mocked) | Order translation, error handling |

---

## ⚠️ Common Pitfalls & Solutions

### 1. Database Sessions

**Problem**: Creating sessions manually causes leaks
```python
# ❌ WRONG
session = SessionLocal()
symbol = session.query(Symbol).first()
```

**Solution**: Always use repository context manager
```python
# ✅ CORRECT
with repository.get_session() as session:
    symbol = repository.get_symbol("RELIANCE")
```

### 2. Strategy Registration

**Problem**: Strategy not available in scanner
```python
# ❌ WRONG - Creating strategy but not registering
strategy = MyStrategy()
scanner = create_eod_scanner()  # Won't include MyStrategy
```

**Solution**: Register strategy in global registry
```python
# ✅ CORRECT
from core.strategy_engine import registry

registry.register(MyStrategy())  # Now available to all scanners
```

### 3. Trading Mode Safety

**Problem**: Accidentally executing live trades during development
```python
# ⚠️ DANGER - Always check mode before real broker calls
if settings.trading.mode == "live":
    broker.place_order(...)  # Real money!
```

**Solution**: Default to paper trading, explicit live mode check
```python
# ✅ CORRECT
# .env file should have TRADING_MODE=paper during development
trading_mode = TradingMode.PAPER if settings.trading.mode == "paper" else TradingMode.LIVE
```

### 4. Data Validation

**Problem**: Strategy crashes on incomplete data
```python
# ❌ WRONG - Assuming data has enough history
sma_50 = sma(data['close'], 50)  # Crashes if data < 50 bars
```

**Solution**: Use strategy's built-in validation
```python
# ✅ CORRECT
if not strategy.validate_data(data):
    return None  # Gracefully skip insufficient data
```

---

## 📁 Key Files Reference

### Core Logic
- **Strategy Framework**: `core/strategy_engine.py` (base class, registry, signal validation)
- **Scanner**: `core/scanner.py` (parallel execution, strategy application)
- **Risk Management**: `core/risk_manager.py`, `core/position_sizer.py`, `core/stop_loss_manager.py`
- **Position Tracking**: `core/position_tracker.py`, `core/position_reconciler.py`

### Configuration
- **Settings**: `config/settings.py` (Pydantic settings with .env loading)
- **Risk Config**: `config/risk_config.py` (position sizing methods, portfolio limits, circuit breakers)

### Data Layer
- **Models**: `data/models.py` (SQLAlchemy ORM, all tables + enums)
- **Repository**: `data/repository.py` (single data access point, context managers)

### API
- **Main App**: `api/main.py` (FastAPI app, middleware, route registration)
- **Routes**: `api/routes/*.py` (strategies, positions, signals, symbols, backtests, risk, orders)
- **Schemas**: `api/schemas/*.py` (Pydantic request/response models)

### Examples
- **Strategy Templates**: `strategies/eod_strategies.py` (Golden Cross, RSI, MACD, Bollinger)
- **Technical Indicators**: `indicators/technical.py` (SMA, EMA, RSI, MACD, Bollinger, ATR, Stochastic, ADX, OBV)

---

## 🚨 Important Notes

1. **Always Start with Paper Trading**: `TRADING_MODE=paper` in `.env`. Never commit live credentials.

2. **Strategy Validation Required**: Strategies must pass backtest validation (65%+ accuracy) before live trading. Check `strategy.is_tradeable()`.

3. **Database Schema Migration**: Old per-stock tables (`{SYMBOL}_daily`) → new normalized `prices` table. Use `scripts/migrate_database.py` if migrating existing data.

4. **Circuit Breakers Active**: Trading auto-halts on:
   - Daily drawdown > 5%
   - Total drawdown > 20%
   - 5 consecutive losses
   - Cooldown: 24 hours

5. **Position Limits Enforced**:
   - Max open positions: 5 (configurable)
   - Max single position: 20% of capital
   - Max total exposure: 80% of capital

6. **Testing Before Deployment**: Run `pytest --cov` and ensure 80%+ coverage before merging. Integration tests require database.

---

## � Prioritization & Adoption Plan

### Day 1 Rules (Non-Negotiable)

These must be enforced immediately on ALL new code:

1. **No hardcoded secrets** - Use `.env` + Pydantic settings
2. **Paper trading default** - `TRADING_MODE=paper` unless explicitly live
3. **Idempotent order placement** - Client order IDs required
4. **Repository pattern for DB** - No raw `SessionLocal()` calls
5. **Type hints on public functions** - Especially trading/money code
6. **Log all order lifecycle events** - Place, fill, reject, cancel
7. **Validate all user inputs** - Quantity > 0, valid symbols, etc.

### 90-Day Maturity Goals

| Week | Goal | Metric |
|------|------|--------|
| 1-2 | Enforce Day 1 rules via PR reviews | 100% compliance on new code |
| 3-4 | Add unit tests for `core/` modules | 80% coverage on core |
| 5-6 | Implement CI pipeline with linting | All PRs pass `ruff` + `mypy` |
| 7-8 | Document all strategies with backtests | Strategy → backtest → results |
| 9-12 | Integration tests for order flow | Paper trade E2E tests pass |

### Tooling Recommendations

**Linting & Formatting** (add to `pyproject.toml`):
```toml
[tool.ruff]
line-length = 100
select = ["E", "F", "W", "I", "N", "B", "A", "C4", "SIM"]
ignore = ["E501"]  # Line length handled separately

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["unit", "integration", "slow"]
```

**Pre-commit Hooks** (`.pre-commit-config.yaml`):
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.7.1
    hooks:
      - id: mypy
        additional_dependencies: [pydantic, sqlalchemy]
```

**CI Enforcement** (GitHub Actions):
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: ruff check .
      - run: mypy core/ data/ config/
      - run: pytest --cov --cov-fail-under=80
```

---

## �📚 Quick Reference Commands

```bash
# Development
uvicorn api.main:app --reload              # Start API server
pytest --cov                               # Run tests with coverage
docker-compose logs -f api                 # View API logs

# Database
mysql -u root -p < schema.sql              # Initialize database
python -c "from data.repository import repository; repository.create_tables()"  # Create tables via ORM

# Strategy Development
python -c "from core.scanner import create_eod_scanner; scanner = create_eod_scanner(); signals = scanner.scan()"

# Monitoring
curl http://localhost:8000/health          # Health check
curl http://localhost:8000/metrics         # System metrics
open http://localhost:5555                 # Flower dashboard (Celery)
```

---

**Last Updated**: December 22, 2025  
**For Questions**: Check `README.md`, `README_REFACTOR.md`, `TESTING.md`, `API_ROUTES_SUMMARY.md`
