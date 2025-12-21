# 🧪 Pytest Quick Reference - StockJarvis

## Quick Commands

```bash
# Run all tests
pytest

# With coverage
pytest --cov

# HTML coverage report
pytest --cov --cov-report=html

# Run specific file
pytest tests/unit/test_risk_manager.py

# Run specific test
pytest tests/unit/test_risk_manager.py::test_fixed_fractional_sizing

# Run by marker
pytest -m unit           # Unit tests only
pytest -m asyncio        # Async tests only
pytest -m "not slow"     # Exclude slow tests

# Verbose output
pytest -v

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Run last failed tests
pytest --lf

# Show local variables on failure
pytest -l

# Debug mode
pytest --pdb
```

## Common Fixtures

```python
# Database (sync)
def test_something(test_db_session):
    symbol = Symbol(...)
    test_db_session.add(symbol)
    test_db_session.commit()

# Database (async)
async def test_async(test_async_db_session):
    symbol = Symbol(...)
    test_async_db_session.add(symbol)
    await test_async_db_session.commit()

# Sample data
def test_with_data(sample_symbol, sample_strategy, sample_position):
    assert sample_symbol.symbol == "RELIANCE"
    assert sample_position.is_open

# Mocks
def test_with_mocks(mock_broker_client, mock_market_data):
    mock_broker_client.place_order.return_value = {...}
    mock_market_data.get_current_price.return_value = 2475.00
```

## Test Markers

```python
@pytest.mark.unit              # Fast unit test
@pytest.mark.integration       # Integration test
@pytest.mark.asyncio           # Async test
@pytest.mark.slow              # Slow test
@pytest.mark.requires_db       # Needs database
@pytest.mark.requires_broker   # Needs broker API
```

## Test Patterns

### Basic Test (AAA Pattern)
```python
def test_calculate_pnl(sample_position):
    # Arrange
    position = sample_position
    
    # Act
    pnl = calculate_pnl(position)
    
    # Assert
    assert pnl > 0
```

### Async Test
```python
@pytest.mark.asyncio
async def test_track_position(test_async_db_session):
    tracker = PositionTracker(session_factory)
    result = await tracker.track_position(1)
    assert result is not None
```

### Parametrized Test
```python
@pytest.mark.parametrize("quantity,expected", [
    (10, 100.0),
    (20, 200.0),
    (0, 0.0),
])
def test_calculation(quantity, expected):
    result = calculate(quantity)
    assert result == expected
```

### Test with Mock
```python
from unittest.mock import Mock, patch

def test_with_mock(mock_broker_client):
    mock_broker_client.place_order.return_value = {"order_id": "123"}
    result = place_order(mock_broker_client, ...)
    assert result["order_id"] == "123"
    mock_broker_client.place_order.assert_called_once()
```

### Test Exception
```python
def test_raises_error():
    with pytest.raises(ValueError) as exc_info:
        risky_function()
    assert "invalid" in str(exc_info.value)
```

## Assertions

```python
# Basic assertions
assert value == 10
assert value > 0
assert value is True
assert "text" in string

# Approximate comparison (for floats)
assert value == pytest.approx(2.0, rel=0.01)  # 1% tolerance
assert value == pytest.approx(2.0, abs=0.1)   # Absolute tolerance

# Collection assertions
assert len(items) == 5
assert item in items
assert all(x > 0 for x in values)
```

## Coverage

```bash
# Generate coverage report
pytest --cov=core --cov=data --cov-report=html

# View in browser
# Open htmlcov/index.html

# Show missing lines
pytest --cov --cov-report=term-missing

# Fail if coverage < 80%
pytest --cov --cov-fail-under=80
```

## File Structure

```
StockJarvis/
├── pytest.ini                 # Config
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Fixtures
│   └── unit/
│       ├── __init__.py
│       ├── test_risk_manager.py
│       └── test_position_tracker.py
```

## Common Issues & Solutions

### "No module named 'core'"
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
# Or run from project root
```

### "Database locked"
```python
# Use in-memory database (already configured in conftest.py)
engine = create_engine("sqlite:///:memory:")
```

### "Async fixture error"
```python
# Mark async fixtures properly
@pytest.fixture
async def async_resource():
    return await create_resource()
```

### "Tests hanging"
```python
# Add timeout
@pytest.mark.timeout(5)
def test_something():
    ...
```

## Best Practices

1. ✅ **One test per function** - Test single behavior
2. ✅ **Descriptive names** - `test_circuit_breaker_triggers_on_drawdown`
3. ✅ **Use fixtures** - Don't repeat setup code
4. ✅ **Mock external APIs** - Don't hit real services
5. ✅ **Test edge cases** - Zero, None, negative values
6. ✅ **Clean up resources** - Use fixtures with cleanup
7. ✅ **Fast tests** - Use in-memory databases
8. ✅ **Independent tests** - No test dependencies

## Debugging

```bash
# Run with debugger
pytest --pdb

# Set breakpoint in test
import pdb; pdb.set_trace()

# Show print statements
pytest -s

# Verbose output with locals
pytest -vl
```

## CI/CD Example

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest --cov --cov-report=xml
      - uses: codecov/codecov-action@v2
```

---

**Quick tips:**
- Run tests frequently during development
- Aim for 80%+ coverage
- Write tests before fixing bugs
- Keep tests fast and focused
- Use fixtures to reduce duplication

**Happy Testing! 🚀**
