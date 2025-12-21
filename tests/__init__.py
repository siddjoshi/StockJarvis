# tests/__init__.py - Test package initialization
"""
StockJarvis Test Suite
=====================

Comprehensive test suite for the StockJarvis trading system.
Includes unit tests, integration tests, and fixtures.

Test Structure:
    - tests/unit/ - Unit tests for individual components
    - tests/integration/ - Integration tests for system workflows
    - conftest.py - Shared fixtures and test configuration

Usage:
    # Run all tests
    pytest

    # Run with coverage
    pytest --cov

    # Run specific marker
    pytest -m unit

    # Run specific test file
    pytest tests/unit/test_risk_manager.py

    # Run specific test
    pytest tests/unit/test_risk_manager.py::test_fixed_fractional_sizing
"""

__version__ = "1.0.0"
