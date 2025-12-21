"""
Position sizing algorithms for risk management.
Implements various position sizing methods: Fixed Fractional, Kelly Criterion, Risk Parity, ATR-based.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
import math
import pandas as pd
import numpy as np

from core.logger import get_logger
from config.risk_config import DEFAULT_RISK_PARAMS

logger = get_logger(__name__)


@dataclass
class PositionSizeResult:
    """Result from position size calculation."""
    
    quantity: int  # Number of shares to trade
    position_value: float  # Total position value in currency
    risk_amount: float  # Amount of capital at risk
    position_pct: float  # Position size as % of capital
    method: str  # Sizing method used
    metadata: Dict[str, Any]  # Additional calculation details
    warnings: list  # Any warnings generated
    
    def is_valid(self) -> bool:
        """Check if position size is valid (quantity > 0)."""
        return self.quantity > 0


class BasePositionSizer(ABC):
    """Abstract base class for position sizing algorithms."""
    
    def __init__(self, params: Dict[str, Any] = None):
        """
        Initialize position sizer.
        
        Args:
            params: Algorithm-specific parameters
        """
        self.params = params or {}
        self.logger = get_logger(self.__class__.__name__)
    
    @abstractmethod
    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        symbol_data: Dict[str, Any] = None
    ) -> PositionSizeResult:
        """
        Calculate position size.
        
        Args:
            entry_price: Entry price per share
            stop_loss: Stop loss price per share
            account_balance: Total account balance
            symbol_data: Additional symbol-specific data (volatility, ATR, etc.)
        
        Returns:
            PositionSizeResult with calculated quantity
        """
        pass
    
    def _calculate_risk_per_share(self, entry_price: float, stop_loss: float) -> float:
        """
        Calculate risk per share.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
        
        Returns:
            Risk amount per share
        """
        return abs(entry_price - stop_loss)
    
    def _validate_inputs(self, entry_price: float, stop_loss: float, account_balance: float) -> bool:
        """
        Validate input parameters.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            account_balance: Account balance
        
        Returns:
            True if valid, False otherwise
        """
        if entry_price <= 0:
            self.logger.error(f"Invalid entry price: {entry_price}")
            return False
        
        if stop_loss <= 0:
            self.logger.error(f"Invalid stop loss: {stop_loss}")
            return False
        
        if account_balance <= 0:
            self.logger.error(f"Invalid account balance: {account_balance}")
            return False
        
        if entry_price == stop_loss:
            self.logger.error("Entry price equals stop loss")
            return False
        
        return True
    
    def _cap_position_size(
        self,
        quantity: int,
        entry_price: float,
        account_balance: float,
        max_position_pct: float = None
    ) -> tuple[int, list]:
        """
        Cap position size at maximum allowed percentage.
        
        Args:
            quantity: Calculated quantity
            entry_price: Entry price
            account_balance: Account balance
            max_position_pct: Maximum position size as % (uses default if None)
        
        Returns:
            Tuple of (capped_quantity, warnings)
        """
        max_pct = max_position_pct or DEFAULT_RISK_PARAMS["max_position_size_pct"]
        max_position_value = account_balance * (max_pct / 100.0)
        max_quantity = int(max_position_value / entry_price)
        
        warnings = []
        if quantity > max_quantity:
            warnings.append(
                f"Position capped: {quantity} shares → {max_quantity} shares "
                f"(max {max_pct}% of capital)"
            )
            quantity = max_quantity
        
        return quantity, warnings


class FixedFractionalSizer(BasePositionSizer):
    """
    Fixed Fractional position sizing.
    Risks a fixed percentage of capital on each trade.
    """
    
    def __init__(self, risk_pct: float = None):
        """
        Initialize Fixed Fractional sizer.
        
        Args:
            risk_pct: Percentage of capital to risk per trade (default from config)
        """
        super().__init__()
        self.risk_pct = risk_pct or DEFAULT_RISK_PARAMS["fixed_fractional_risk_pct"]
    
    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        symbol_data: Dict[str, Any] = None
    ) -> PositionSizeResult:
        """
        Calculate position size using Fixed Fractional method.
        
        Formula: Quantity = (Account Balance * Risk %) / Risk per Share
        
        Args:
            entry_price: Entry price per share
            stop_loss: Stop loss price per share
            account_balance: Total account balance
            symbol_data: Not used for this method
        
        Returns:
            PositionSizeResult
        """
        # Validate inputs
        if not self._validate_inputs(entry_price, stop_loss, account_balance):
            return PositionSizeResult(
                quantity=0,
                position_value=0.0,
                risk_amount=0.0,
                position_pct=0.0,
                method="fixed_fractional",
                metadata={},
                warnings=["Invalid inputs"]
            )
        
        # Calculate risk amounts
        risk_per_share = self._calculate_risk_per_share(entry_price, stop_loss)
        risk_amount = account_balance * (self.risk_pct / 100.0)
        
        # Calculate quantity
        quantity = int(risk_amount / risk_per_share)
        
        # Ensure minimum position size
        min_shares = DEFAULT_RISK_PARAMS["min_position_size_shares"]
        if quantity < min_shares:
            quantity = 0  # Position too small
        
        # Cap at maximum position size
        quantity, warnings = self._cap_position_size(quantity, entry_price, account_balance)
        
        # Calculate final metrics
        position_value = quantity * entry_price
        position_pct = (position_value / account_balance) * 100.0 if account_balance > 0 else 0.0
        actual_risk = quantity * risk_per_share
        
        self.logger.info(
            f"Fixed Fractional: {quantity} shares @ ${entry_price:.2f} "
            f"= ${position_value:.2f} ({position_pct:.2f}% of capital), "
            f"Risk: ${actual_risk:.2f}"
        )
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=actual_risk,
            position_pct=position_pct,
            method="fixed_fractional",
            metadata={
                "risk_pct": self.risk_pct,
                "risk_per_share": risk_per_share,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
            },
            warnings=warnings
        )


class KellyCriterionSizer(BasePositionSizer):
    """
    Kelly Criterion position sizing.
    Optimal position size based on win probability and payoff ratio.
    """
    
    def __init__(
        self,
        kelly_fraction: float = None,
        default_win_rate: float = None,
        default_win_loss_ratio: float = None
    ):
        """
        Initialize Kelly Criterion sizer.
        
        Args:
            kelly_fraction: Fraction of full Kelly to use (0.25 = 25%)
            default_win_rate: Default win rate if no history
            default_win_loss_ratio: Default win/loss ratio if no history
        """
        super().__init__()
        self.kelly_fraction = kelly_fraction or DEFAULT_RISK_PARAMS["kelly_fraction"]
        self.default_win_rate = default_win_rate or DEFAULT_RISK_PARAMS["kelly_default_win_rate"]
        self.default_win_loss_ratio = default_win_loss_ratio or DEFAULT_RISK_PARAMS["kelly_default_win_loss_ratio"]
    
    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        symbol_data: Dict[str, Any] = None
    ) -> PositionSizeResult:
        """
        Calculate position size using Kelly Criterion.
        
        Kelly % = W - [(1 - W) / R]
        Where: W = win probability, R = win/loss ratio
        
        Args:
            entry_price: Entry price per share
            stop_loss: Stop loss price per share
            account_balance: Total account balance
            symbol_data: Must contain 'win_rate' and 'win_loss_ratio' or defaults used
        
        Returns:
            PositionSizeResult
        """
        # Validate inputs
        if not self._validate_inputs(entry_price, stop_loss, account_balance):
            return PositionSizeResult(
                quantity=0,
                position_value=0.0,
                risk_amount=0.0,
                position_pct=0.0,
                method="kelly_criterion",
                metadata={},
                warnings=["Invalid inputs"]
            )
        
        # Get win rate and win/loss ratio from symbol data or use defaults
        symbol_data = symbol_data or {}
        win_rate = symbol_data.get('win_rate', self.default_win_rate)
        win_loss_ratio = symbol_data.get('win_loss_ratio', self.default_win_loss_ratio)
        
        warnings = []
        
        # Validate probabilities
        if not 0 < win_rate < 1:
            warnings.append(f"Invalid win rate {win_rate}, using default {self.default_win_rate}")
            win_rate = self.default_win_rate
        
        if win_loss_ratio <= 0:
            warnings.append(f"Invalid win/loss ratio {win_loss_ratio}, using default {self.default_win_loss_ratio}")
            win_loss_ratio = self.default_win_loss_ratio
        
        # Calculate Kelly percentage
        kelly_pct = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Apply Kelly fraction (conservative scaling)
        kelly_pct = kelly_pct * self.kelly_fraction
        
        # Ensure non-negative
        kelly_pct = max(0.0, kelly_pct)
        
        # Cap at maximum
        max_kelly = DEFAULT_RISK_PARAMS["kelly_max_position_pct"] / 100.0
        if kelly_pct > max_kelly:
            warnings.append(f"Kelly {kelly_pct:.2%} capped at {max_kelly:.2%}")
            kelly_pct = max_kelly
        
        # Calculate position size
        position_value = account_balance * kelly_pct
        quantity = int(position_value / entry_price)
        
        # Ensure minimum position size
        min_shares = DEFAULT_RISK_PARAMS["min_position_size_shares"]
        if quantity < min_shares:
            quantity = 0
        
        # Calculate metrics
        position_value = quantity * entry_price
        position_pct = (position_value / account_balance) * 100.0 if account_balance > 0 else 0.0
        risk_per_share = self._calculate_risk_per_share(entry_price, stop_loss)
        risk_amount = quantity * risk_per_share
        
        self.logger.info(
            f"Kelly Criterion: {quantity} shares @ ${entry_price:.2f} "
            f"= ${position_value:.2f} ({position_pct:.2f}% of capital), "
            f"Kelly %: {kelly_pct:.2%}, Win Rate: {win_rate:.2%}"
        )
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=risk_amount,
            position_pct=position_pct,
            method="kelly_criterion",
            metadata={
                "kelly_pct": kelly_pct * 100,
                "kelly_fraction": self.kelly_fraction,
                "win_rate": win_rate,
                "win_loss_ratio": win_loss_ratio,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
            },
            warnings=warnings
        )


class RiskParitySizer(BasePositionSizer):
    """
    Risk Parity position sizing.
    Sizes positions to equalize volatility contribution.
    """
    
    def __init__(
        self,
        target_volatility: float = None,
        lookback_days: int = None
    ):
        """
        Initialize Risk Parity sizer.
        
        Args:
            target_volatility: Target portfolio volatility (annual)
            lookback_days: Days for volatility calculation
        """
        super().__init__()
        self.target_volatility = target_volatility or DEFAULT_RISK_PARAMS["risk_parity_target_volatility"]
        self.lookback_days = lookback_days or DEFAULT_RISK_PARAMS["risk_parity_lookback_days"]
    
    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        symbol_data: Dict[str, Any] = None
    ) -> PositionSizeResult:
        """
        Calculate position size using Risk Parity method.
        
        Position Weight = Target Volatility / Asset Volatility
        
        Args:
            entry_price: Entry price per share
            stop_loss: Stop loss price per share
            account_balance: Total account balance
            symbol_data: Must contain 'volatility' (annual) or 'price_history'
        
        Returns:
            PositionSizeResult
        """
        # Validate inputs
        if not self._validate_inputs(entry_price, stop_loss, account_balance):
            return PositionSizeResult(
                quantity=0,
                position_value=0.0,
                risk_amount=0.0,
                position_pct=0.0,
                method="risk_parity",
                metadata={},
                warnings=["Invalid inputs"]
            )
        
        symbol_data = symbol_data or {}
        warnings = []
        
        # Get or calculate volatility
        volatility = symbol_data.get('volatility')
        
        if volatility is None:
            # Try to calculate from price history
            price_history = symbol_data.get('price_history')
            if price_history is not None and len(price_history) >= self.lookback_days:
                returns = price_history.pct_change().dropna()
                volatility = returns.std() * math.sqrt(252)  # Annualize
            else:
                # Use default
                volatility = 0.25  # 25% default annual volatility
                warnings.append(f"No volatility data, using default {volatility:.2%}")
        
        # Ensure minimum volatility
        min_vol = DEFAULT_RISK_PARAMS["risk_parity_min_volatility"]
        if volatility < min_vol:
            warnings.append(f"Volatility {volatility:.2%} < minimum {min_vol:.2%}, using minimum")
            volatility = min_vol
        
        # Calculate position weight
        position_weight = self.target_volatility / volatility
        
        # Cap at maximum
        max_weight = DEFAULT_RISK_PARAMS["max_position_size_pct"] / 100.0
        if position_weight > max_weight:
            warnings.append(f"Position weight {position_weight:.2%} capped at {max_weight:.2%}")
            position_weight = max_weight
        
        # Calculate position size
        position_value = account_balance * position_weight
        quantity = int(position_value / entry_price)
        
        # Ensure minimum position size
        min_shares = DEFAULT_RISK_PARAMS["min_position_size_shares"]
        if quantity < min_shares:
            quantity = 0
        
        # Calculate metrics
        position_value = quantity * entry_price
        position_pct = (position_value / account_balance) * 100.0 if account_balance > 0 else 0.0
        risk_per_share = self._calculate_risk_per_share(entry_price, stop_loss)
        risk_amount = quantity * risk_per_share
        
        self.logger.info(
            f"Risk Parity: {quantity} shares @ ${entry_price:.2f} "
            f"= ${position_value:.2f} ({position_pct:.2f}% of capital), "
            f"Volatility: {volatility:.2%}, Target: {self.target_volatility:.2%}"
        )
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=risk_amount,
            position_pct=position_pct,
            method="risk_parity",
            metadata={
                "position_weight": position_weight * 100,
                "asset_volatility": volatility,
                "target_volatility": self.target_volatility,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
            },
            warnings=warnings
        )


class ATRBasedSizer(BasePositionSizer):
    """
    ATR-based position sizing.
    Sizes positions based on Average True Range volatility.
    """
    
    def __init__(
        self,
        atr_period: int = None,
        atr_multiplier: float = None,
        risk_pct: float = None
    ):
        """
        Initialize ATR-based sizer.
        
        Args:
            atr_period: ATR calculation period
            atr_multiplier: Multiplier for ATR
            risk_pct: Percentage of capital to risk
        """
        super().__init__()
        self.atr_period = atr_period or DEFAULT_RISK_PARAMS["atr_period"]
        self.atr_multiplier = atr_multiplier or DEFAULT_RISK_PARAMS["atr_multiplier"]
        self.risk_pct = risk_pct or DEFAULT_RISK_PARAMS["atr_risk_per_trade_pct"]
    
    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        account_balance: float,
        symbol_data: Dict[str, Any] = None
    ) -> PositionSizeResult:
        """
        Calculate position size using ATR method.
        
        Quantity = (Account Balance * Risk %) / (ATR * Multiplier)
        
        Args:
            entry_price: Entry price per share
            stop_loss: Stop loss price per share
            account_balance: Total account balance
            symbol_data: Must contain 'atr' value or price history to calculate
        
        Returns:
            PositionSizeResult
        """
        # Validate inputs
        if not self._validate_inputs(entry_price, stop_loss, account_balance):
            return PositionSizeResult(
                quantity=0,
                position_value=0.0,
                risk_amount=0.0,
                position_pct=0.0,
                method="atr_based",
                metadata={},
                warnings=["Invalid inputs"]
            )
        
        symbol_data = symbol_data or {}
        warnings = []
        
        # Get ATR
        atr = symbol_data.get('atr')
        
        if atr is None or atr <= 0:
            # Fallback to using stop loss distance as proxy
            atr = abs(entry_price - stop_loss) / self.atr_multiplier
            warnings.append(f"No ATR data, using stop distance as proxy: {atr:.2f}")
        
        # Calculate risk amount
        risk_amount = account_balance * (self.risk_pct / 100.0)
        
        # Calculate risk per share using ATR
        risk_per_share = atr * self.atr_multiplier
        
        # Ensure risk per share is reasonable
        if risk_per_share < 0.01:
            risk_per_share = 0.01
            warnings.append("ATR risk too small, using minimum")
        
        # Calculate quantity
        quantity = int(risk_amount / risk_per_share)
        
        # Ensure minimum position size
        min_shares = DEFAULT_RISK_PARAMS["min_position_size_shares"]
        if quantity < min_shares:
            quantity = 0
        
        # Cap at maximum position size
        quantity, cap_warnings = self._cap_position_size(quantity, entry_price, account_balance)
        warnings.extend(cap_warnings)
        
        # Calculate metrics
        position_value = quantity * entry_price
        position_pct = (position_value / account_balance) * 100.0 if account_balance > 0 else 0.0
        actual_risk = quantity * risk_per_share
        
        self.logger.info(
            f"ATR-Based: {quantity} shares @ ${entry_price:.2f} "
            f"= ${position_value:.2f} ({position_pct:.2f}% of capital), "
            f"ATR: {atr:.2f}, Risk per share: ${risk_per_share:.2f}"
        )
        
        return PositionSizeResult(
            quantity=quantity,
            position_value=position_value,
            risk_amount=actual_risk,
            position_pct=position_pct,
            method="atr_based",
            metadata={
                "atr": atr,
                "atr_multiplier": self.atr_multiplier,
                "risk_per_share": risk_per_share,
                "risk_pct": self.risk_pct,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
            },
            warnings=warnings
        )
