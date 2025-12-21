# StockJarvis Testing Framework

Comprehensive test suite for the StockJarvis trading system using pytest.

## 📋 Overview

This testing framework provides:
- **Unit Tests** - Fast, isolated tests for individual components
- **Integration Tests** - Tests for component interactions
- **Fixtures** - Reusable test data and mocked services
- **Coverage Reports** - 80%+ code coverage target
- **Async Support** - Full async/await testing capabilities

## 🚀 Quick Start

### Installation

```bash
# Install testing dependencies
pip install -r requirements.txt

# Or install test dependencies separately
pip install pytest pytest-asyncio pytest-cov pytest-mock faker aiosqlite
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov

# Run specific test file
pytest tests/unit/test_risk_manager.py

# Run specific test
pytest tests/unit/test_risk_manager.py::test_fixed_fractional_sizing

# Run tests by marker
pytest -m unit          # Only unit tests
pytest -m integration   # Only integration tests
pytest -m asyncio       # Only async tests

# Run with verbose output
pytest -v

# Run and show print statements
pytest -s
```

## 📁 Structure

```
tests/
├── __init__.py                      # Test package init
├── conftest.py                      # Core fixtures and configuration
├── pytest.ini                       # Pytest configuration (in root)
│
├── unit/                            # Unit tests
│   ├── __init__.py
│   ├── test_risk_manager.py        # RiskManager tests
│   ├── test_position_tracker.py    # PositionTracker tests
│   ├── test_position_sizer.py      # Position sizing tests
│   ├── test_stop_loss_manager.py   # Stop loss tests
│   ├── test_strategy_engine.py     # Strategy execution tests
│   └── test_scanner.py             # Market scanner tests
│
└── integration/                     # Integration tests
    ├── __init__.py
    ├── test_trading_workflow.py    # End-to-end trading flow
    ├── test_broker_integration.py  # Broker API integration
    └── test_data_pipeline.py       # Data collection pipeline
```

## 🧪 Test Categories

### Unit Tests
- Fast execution (< 1 second per test)
- Isolated components
- Mocked dependencies
- High coverage

```python
@pytest.mark.unit
def test_fixed_fractional_sizing(test_db_session, sample_symbol):
    risk_manager = RiskManager(test_db_session)
    # Test logic...
```

### Integration Tests
- Multiple components
- Real database (test instance)
- May use external services
- Slower execution

```python
@pytest.mark.integration
@pytest.mark.requires_db
async def test_full_trading_workflow(test_async_db_session):
    # Test logic...
```

### Async Tests
- Uses pytest-asyncio
- Async database sessions
- Async mocks

```python
@pytest.mark.asyncio
async def test_track_position(test_async_db_session, sample_symbol):
    tracker = PositionTracker(session_factory)
    result = await tracker.track_position(position_id)
```

## 🔧 Fixtures

### Database Fixtures

```python
# Synchronous database
def test_something(test_db_session):
    symbol = Symbol(symbol="TEST", company_name="Test Corp")
    test_db_session.add(symbol)
    test_db_session.commit()

# Asynchronous database
async def test_something_async(test_async_db_session):
    symbol = Symbol(symbol="TEST", company_name="Test Corp")
    test_async_db_session.add(symbol)
    await test_async_db_session.commit()
```

### Sample Data Fixtures

```python
# Sample symbol
def test_with_symbol(sample_symbol):
    assert sample_symbol.symbol == "RELIANCE"

# Sample strategy
def test_with_strategy(sample_strategy):
    assert sample_strategy.name == "RSI_MACD_Combo"

# Sample position
def test_with_position(sample_position):
    assert sample_position.quantity == 10
    assert sample_position.is_open is True
```

### Mock Services

```python
# Mock broker
def test_order_placement(mock_broker_client):
    mock_broker_client.place_order.return_value = {"order_id": "123"}
    # Test logic...

# Mock market data
def test_price_fetch(mock_market_data):
    mock_market_data.get_current_price.return_value = 2475.00
    # Test logic...
```

## 📊 Coverage

### Viewing Coverage

```bash
# Terminal report
pytest --cov --cov-report=term-missing

# HTML report
pytest --cov --cov-report=html
# Open htmlcov/index.html in browser

# XML report (for CI/CD)
pytest --cov --cov-report=xml
```

### Coverage Targets

- **Minimum**: 80% overall coverage
- **Core modules**: 90%+ coverage
  - `core/risk_manager.py`
  - `core/position_tracker.py`
  - `core/strategy_engine.py`
  - `data/repository.py`

### Excluding from Coverage

```python
def debug_helper():  # pragma: no cover
    """This function is excluded from coverage"""
    pass
```

## 🎯 Test Examples

### Basic Unit Test

```python
@pytest.mark.unit
def test_calculate_pnl(test_db_session, sample_symbol):
    """Test P&L calculation for long position."""
    position = Position(
        symbol_id=sample_symbol.id,
        quantity=10,
        entry_price=2450.00,
        current_price=2500.00,
    )
    
    pnl = (2500.00 - 2450.00) * 10
    assert pnl == 500.0
```

### Parametrized Test

```python
@pytest.mark.unit
@pytest.mark.parametrize("method,expected_type", [
    (PositionSizingMethod.FIXED_FRACTIONAL, "fixed_fractional"),
    (PositionSizingMethod.KELLY_CRITERION, "kelly_criterion"),
    (PositionSizingMethod.RISK_PARITY, "risk_parity"),
])
def test_sizing_methods(method, expected_type, test_db_session):
    risk_manager = RiskManager(test_db_session)
    # Test each sizing method...
```

### Async Test

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_track_position(test_async_db_session, sample_symbol):
    """Test async position tracking."""
    async def get_session():
        return test_async_db_session
    
    tracker = PositionTracker(lambda: get_session())
    
    # Create position
    position = Position(...)
    test_async_db_session.add(position)
    await test_async_db_session.commit()
    
    # Track position
    pnl = await tracker.track_position(position.id)
    assert pnl is not None
```

### Mock Test

```python
@pytest.mark.unit
def test_broker_order(mock_broker_client):
    """Test order placement with mocked broker."""
    mock_broker_client.place_order.return_value = {
        "order_id": "MOCK123",
        "status": "COMPLETE"
    }
    
    result = place_order_via_broker(mock_broker_client, ...)
    
    assert result["order_id"] == "MOCK123"
    mock_broker_client.place_order.assert_called_once()
```

## 🏗️ Writing New Tests

### Test Naming Convention

```python
# Format: test_<what>_<condition>
def test_calculate_pnl_long_position_profit()
def test_validate_position_risk_exceeds_limit()
def test_circuit_breaker_trigger_on_drawdown()
```

### Test Structure (AAA Pattern)

```python
def test_something():
    # Arrange - Setup test data
    position = Position(...)
    
    # Act - Perform the action
    result = calculate_pnl(position)
    
    # Assert - Verify the result
    assert result.pnl == 500.0
```

### Using Fixtures

```python
# Arrange
@pytest.fixture
def trading_scenario(test_db_session, sample_symbol):
    """Create a complete trading scenario."""
    strategy = Strategy(...)
    signal = Signal(...)
    position = Position(...)
    return {"strategy": strategy, "signal": signal, "position": position}

# Use in test
def test_trading_workflow(trading_scenario):
    assert trading_scenario["position"].is_open
```

## 🚦 CI/CD Integration

### GitHub Actions

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run tests with coverage
      run: |
        pytest --cov --cov-report=xml --cov-report=term
    
    - name: Upload coverage
      uses: codecov/codecov-action@v2
```

## 🐛 Debugging Tests

### Run specific test with debugging

```bash
# With pdb debugger
pytest --pdb tests/unit/test_risk_manager.py::test_circuit_breaker

# Show print statements
pytest -s tests/unit/test_risk_manager.py

# Show local variables on failure
pytest -l tests/unit/test_risk_manager.py
```

### Using breakpoints

```python
def test_something():
    position = Position(...)
    
    import pdb; pdb.set_trace()  # Breakpoint
    
    result = calculate_pnl(position)
    assert result.pnl > 0
```

## 📝 Best Practices

1. **One Assert Per Test** (when possible)
   ```python
   # Good
   def test_position_quantity():
       assert position.quantity == 10
   
   def test_position_price():
       assert position.entry_price == 2450.0
   ```

2. **Use Descriptive Names**
   ```python
   # Good
   def test_circuit_breaker_triggers_on_max_drawdown()
   
   # Avoid
   def test_cb()
   ```

3. **Test Edge Cases**
   ```python
   def test_calculate_pnl_zero_quantity()
   def test_calculate_pnl_negative_price()
   def test_calculate_pnl_with_none_values()
   ```

4. **Mock External Dependencies**
   ```python
   @patch('broker_module.KiteConnect')
   def test_with_mocked_broker(mock_kite):
       # Test without real API calls
   ```

5. **Clean Up Resources**
   ```python
   @pytest.fixture
   def resource():
       r = create_resource()
       yield r
       r.cleanup()  # Always cleanup
   ```

## 🔍 Common Issues

### Issue: Tests hanging
**Solution**: Check for infinite loops or missing mocks for async operations

### Issue: Database errors
**Solution**: Ensure test database is properly cleaned between tests

### Issue: Import errors
**Solution**: Make sure `PYTHONPATH` includes project root

```bash
# Add to shell profile or .env
export PYTHONPATH="${PYTHONPATH}:/path/to/StockJarvis"
```

### Issue: Async fixture errors
**Solution**: Use `pytest-asyncio` and mark async fixtures correctly

```python
@pytest.fixture
async def async_resource():
    resource = await create_async_resource()
    yield resource
    await resource.cleanup()
```

## 📚 Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)

## 🎓 Learning Path

1. **Start with**: Unit tests for simple functions
2. **Progress to**: Tests with fixtures and mocks
3. **Advanced**: Async tests and integration tests
4. **Master**: Custom fixtures and parametrization

## 📞 Support

For questions or issues with tests:
1. Check existing test examples
2. Review pytest documentation
3. Check test coverage reports
4. Ask in team channels

---

**Happy Testing! 🧪✨**
