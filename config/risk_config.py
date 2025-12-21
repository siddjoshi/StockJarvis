"""
Risk management configuration and parameters for StockJarvis.
Defines risk limits, position sizing methods, and circuit breakers.
"""

from typing import Dict, Any


# Position sizing method identifiers
class PositionSizingMethod:
    """Position sizing method constants."""
    FIXED_FRACTIONAL = "fixed_fractional"
    KELLY_CRITERION = "kelly_criterion"
    RISK_PARITY = "risk_parity"
    ATR_BASED = "atr_based"


# Default risk parameters
DEFAULT_RISK_PARAMS: Dict[str, Any] = {
    # Position Sizing Parameters
    "default_sizing_method": PositionSizingMethod.FIXED_FRACTIONAL,
    "risk_per_trade_pct": 2.0,  # % of capital to risk per trade
    "max_position_size_pct": 10.0,  # Max % of capital in a single position
    "min_position_size_shares": 1,  # Minimum shares to trade
    
    # Fixed Fractional Parameters
    "fixed_fractional_risk_pct": 2.0,  # % of capital to risk
    
    # Kelly Criterion Parameters
    "kelly_fraction": 0.25,  # Use 25% of full Kelly (conservative)
    "kelly_default_win_rate": 0.55,  # Default if no history
    "kelly_default_win_loss_ratio": 2.0,  # Default reward:risk
    "kelly_max_position_pct": 10.0,  # Cap Kelly at 10% position size
    
    # Risk Parity Parameters
    "risk_parity_target_volatility": 0.15,  # 15% annual volatility target
    "risk_parity_lookback_days": 20,  # Days for volatility calculation
    "risk_parity_min_volatility": 0.05,  # Minimum volatility threshold
    
    # ATR-Based Parameters
    "atr_period": 14,  # ATR calculation period
    "atr_multiplier": 2.0,  # ATR multiplier for position sizing
    "atr_risk_per_trade_pct": 2.0,  # % of capital to risk per ATR
    
    # Stop Loss Parameters
    "default_stop_loss_pct": 3.0,  # Default stop loss %
    "atr_stop_multiplier": 2.0,  # ATR multiplier for stops
    "trailing_stop_activation_pct": 5.0,  # % profit to activate trailing stop
    "trailing_stop_distance_pct": 3.0,  # Trailing stop distance
    "support_resistance_buffer_pct": 0.5,  # Buffer for S/R levels
    
    # Risk:Reward Parameters
    "min_risk_reward_ratio": 2.0,  # Minimum R:R for signals
    "default_reward_multiplier": 2.5,  # Default target = risk * this
}


# Portfolio-level risk limits
PORTFOLIO_RISK_LIMITS: Dict[str, Any] = {
    # Exposure Limits
    "max_total_exposure_pct": 80.0,  # Max % of capital deployed
    "max_sector_exposure_pct": 30.0,  # Max % in single sector
    "max_single_position_pct": 10.0,  # Max % in single stock
    "max_correlated_exposure_pct": 25.0,  # Max % in correlated positions
    
    # Position Limits
    "max_open_positions": 10,  # Maximum concurrent positions
    "max_positions_per_symbol": 1,  # Max positions per stock
    "max_daily_trades": 20,  # Max trades per day
    
    # Concentration Limits
    "max_long_exposure_pct": 80.0,  # Max long exposure
    "max_short_exposure_pct": 20.0,  # Max short exposure (if enabled)
    
    # Correlation Limits
    "correlation_threshold": 0.7,  # Positions with >0.7 correlation considered related
    "correlation_lookback_days": 60,  # Days for correlation calculation
}


# Circuit breaker thresholds
CIRCUIT_BREAKER_THRESHOLDS: Dict[str, Any] = {
    # Drawdown Limits
    "max_daily_drawdown_pct": 5.0,  # Halt trading if daily loss > 5%
    "max_weekly_drawdown_pct": 10.0,  # Halt trading if weekly loss > 10%
    "max_total_drawdown_pct": 20.0,  # Halt trading if total loss > 20%
    
    # Loss Limits
    "max_daily_loss_amount": 10000.0,  # Max $ loss per day
    "max_consecutive_losses": 5,  # Halt after N consecutive losses
    "max_losses_per_day": 10,  # Max losing trades per day
    
    # Volatility Limits
    "max_portfolio_volatility": 0.30,  # 30% annual volatility limit
    "volatility_lookback_days": 30,  # Days for volatility calculation
    
    # Recovery Parameters
    "circuit_breaker_cooldown_hours": 24,  # Hours before auto-resume
    "require_manual_reset": True,  # Require manual intervention to resume
}


# Position sizing method configurations
POSITION_SIZING_METHODS: Dict[str, Dict[str, Any]] = {
    PositionSizingMethod.FIXED_FRACTIONAL: {
        "name": "Fixed Fractional",
        "description": "Risk a fixed % of capital per trade",
        "params": {
            "risk_pct": DEFAULT_RISK_PARAMS["fixed_fractional_risk_pct"],
        },
        "recommended_for": ["beginners", "conservative"],
    },
    
    PositionSizingMethod.KELLY_CRITERION: {
        "name": "Kelly Criterion",
        "description": "Optimal position size based on win rate and payoff ratio",
        "params": {
            "kelly_fraction": DEFAULT_RISK_PARAMS["kelly_fraction"],
            "default_win_rate": DEFAULT_RISK_PARAMS["kelly_default_win_rate"],
            "default_win_loss_ratio": DEFAULT_RISK_PARAMS["kelly_default_win_loss_ratio"],
        },
        "recommended_for": ["experienced", "aggressive"],
        "warnings": ["Can suggest large positions", "Requires accurate win rate"],
    },
    
    PositionSizingMethod.RISK_PARITY: {
        "name": "Risk Parity",
        "description": "Size positions to equalize volatility contribution",
        "params": {
            "target_volatility": DEFAULT_RISK_PARAMS["risk_parity_target_volatility"],
            "lookback_days": DEFAULT_RISK_PARAMS["risk_parity_lookback_days"],
        },
        "recommended_for": ["portfolio_managers", "diversification"],
    },
    
    PositionSizingMethod.ATR_BASED: {
        "name": "ATR-Based",
        "description": "Position size based on Average True Range volatility",
        "params": {
            "atr_period": DEFAULT_RISK_PARAMS["atr_period"],
            "atr_multiplier": DEFAULT_RISK_PARAMS["atr_multiplier"],
        },
        "recommended_for": ["momentum", "breakout_strategies"],
    },
}


# Risk management validation rules
RISK_VALIDATION_RULES: Dict[str, Any] = {
    # Pre-trade validation
    "require_stop_loss": True,  # Must have stop loss defined
    "require_target": True,  # Must have target defined
    "require_min_risk_reward": True,  # Must meet min R:R ratio
    "validate_liquidity": False,  # Check if stock has sufficient volume
    "min_volume": 100000,  # Minimum daily volume if liquidity check enabled
    
    # Position validation
    "check_correlation": True,  # Check correlation with existing positions
    "check_sector_exposure": True,  # Check sector concentration
    "check_drawdown": True,  # Check portfolio drawdown before trading
    
    # Order validation
    "check_margin_available": True,  # Ensure sufficient margin
    "check_price_sanity": True,  # Validate price is within reasonable range
    "max_price_deviation_pct": 5.0,  # Max % deviation from last close
}


# Stop loss configuration
STOP_LOSS_CONFIG: Dict[str, Any] = {
    # Stop loss types
    "types": {
        "percentage": "Fixed percentage from entry",
        "atr": "ATR-based dynamic stop",
        "support_resistance": "Support/resistance level",
        "trailing": "Trailing stop following price",
    },
    
    # Default stop loss type
    "default_type": "atr",
    
    # Trailing stop configuration
    "trailing": {
        "activation_profit_pct": DEFAULT_RISK_PARAMS["trailing_stop_activation_pct"],
        "distance_pct": DEFAULT_RISK_PARAMS["trailing_stop_distance_pct"],
        "update_frequency_seconds": 60,  # How often to update trailing stop
    },
    
    # ATR stop configuration
    "atr": {
        "period": DEFAULT_RISK_PARAMS["atr_period"],
        "multiplier": DEFAULT_RISK_PARAMS["atr_stop_multiplier"],
        "min_stop_distance_pct": 1.0,  # Minimum stop distance
        "max_stop_distance_pct": 10.0,  # Maximum stop distance
    },
}


# Risk metrics calculation parameters
RISK_METRICS_CONFIG: Dict[str, Any] = {
    # Volatility calculation
    "volatility_window": 20,  # Days for volatility calculation
    "volatility_annual_factor": 252,  # Trading days per year
    
    # Correlation calculation
    "correlation_window": 60,  # Days for correlation calculation
    "correlation_min_periods": 20,  # Minimum periods for valid correlation
    
    # Beta calculation
    "beta_window": 60,  # Days for beta calculation
    "beta_benchmark": "NIFTY50",  # Benchmark index
    
    # Sharpe ratio calculation
    "risk_free_rate": 0.05,  # 5% annual risk-free rate
    
    # Value at Risk (VaR)
    "var_confidence_level": 0.95,  # 95% confidence level
    "var_window": 252,  # 1 year lookback
}


# Emergency protocols
EMERGENCY_PROTOCOLS: Dict[str, Any] = {
    # Auto-exit scenarios
    "enable_auto_exit": True,
    "auto_exit_triggers": {
        "hit_stop_loss": True,
        "circuit_breaker_triggered": True,
        "exchange_halt": False,  # Don't auto-exit on exchange halt
        "system_error": False,
    },
    
    # Position flattening
    "flatten_on_eod": False,  # Close all positions at end of day
    "flatten_on_friday": False,  # Close all positions on Friday
    "flatten_time": "15:15",  # Time to flatten (if enabled)
    
    # Alert escalation
    "alert_levels": {
        "info": ["log"],  # Just log
        "warning": ["log", "email"],  # Log + email
        "critical": ["log", "email", "sms"],  # Log + email + SMS
        "emergency": ["log", "email", "sms", "halt_trading"],  # All + halt
    },
}


def get_risk_param(param_name: str, default: Any = None) -> Any:
    """
    Get a risk parameter value.
    
    Args:
        param_name: Parameter name
        default: Default value if not found
    
    Returns:
        Parameter value
    """
    return DEFAULT_RISK_PARAMS.get(param_name, default)


def get_portfolio_limit(limit_name: str, default: Any = None) -> Any:
    """
    Get a portfolio limit value.
    
    Args:
        limit_name: Limit name
        default: Default value if not found
    
    Returns:
        Limit value
    """
    return PORTFOLIO_RISK_LIMITS.get(limit_name, default)


def get_circuit_breaker_threshold(threshold_name: str, default: Any = None) -> Any:
    """
    Get a circuit breaker threshold.
    
    Args:
        threshold_name: Threshold name
        default: Default value if not found
    
    Returns:
        Threshold value
    """
    return CIRCUIT_BREAKER_THRESHOLDS.get(threshold_name, default)


def validate_risk_params(params: Dict[str, Any]) -> bool:
    """
    Validate custom risk parameters.
    
    Args:
        params: Dictionary of risk parameters
    
    Returns:
        True if valid, False otherwise
    """
    # Check critical parameters are within valid ranges
    if "risk_per_trade_pct" in params:
        if not 0 < params["risk_per_trade_pct"] <= 10:
            return False
    
    if "max_position_size_pct" in params:
        if not 0 < params["max_position_size_pct"] <= 50:
            return False
    
    if "min_risk_reward_ratio" in params:
        if not 0 < params["min_risk_reward_ratio"] <= 10:
            return False
    
    return True
