"""
Backtest execution engine for simulating order execution.
Handles slippage models, commission models, and position management.
"""

from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum
import math

from core.logger import get_logger
from data.models import OrderAction

logger = get_logger(__name__)


class SlippageModel(Enum):
    """Slippage calculation models."""
    FIXED = "fixed"
    PERCENTAGE = "percentage"
    VOLUME_BASED = "volume_based"


class CommissionModel(Enum):
    """Commission calculation models."""
    FIXED = "fixed"
    PERCENTAGE = "percentage"
    TIERED = "tiered"


@dataclass
class SlippageConfig:
    """Configuration for slippage calculation."""
    
    model: SlippageModel = SlippageModel.PERCENTAGE
    
    # Fixed model: absolute amount
    fixed_amount: float = 0.05
    
    # Percentage model: % of price
    percentage: float = 0.001  # 0.1%
    
    # Volume-based model parameters
    volume_impact: float = 0.0001  # Impact per % of avg volume
    avg_volume_lookback: int = 20  # Days to calculate avg volume
    
    def calculate(
        self,
        price: float,
        quantity: int,
        action: OrderAction,
        avg_volume: Optional[float] = None
    ) -> float:
        """
        Calculate slippage amount.
        
        Args:
            price: Order price
            quantity: Order quantity
            action: BUY or SELL
            avg_volume: Average daily volume (for volume-based model)
            
        Returns:
            Slippage amount (always positive)
        """
        if self.model == SlippageModel.FIXED:
            slippage = self.fixed_amount
            
        elif self.model == SlippageModel.PERCENTAGE:
            slippage = price * self.percentage
            
        elif self.model == SlippageModel.VOLUME_BASED:
            if avg_volume is None or avg_volume <= 0:
                # Fall back to percentage if no volume data
                slippage = price * self.percentage
            else:
                # Calculate volume impact
                volume_ratio = quantity / avg_volume
                slippage = price * self.volume_impact * volume_ratio * 100
        else:
            slippage = 0.0
        
        return abs(slippage)
    
    def apply_slippage(
        self,
        price: float,
        quantity: int,
        action: OrderAction,
        is_entry: bool,
        avg_volume: Optional[float] = None
    ) -> float:
        """
        Apply slippage to get execution price.
        
        Slippage always works against the trader:
        - BUY entry: higher price
        - SELL entry: lower price
        - BUY exit (close short): higher price
        - SELL exit (close long): lower price
        
        Args:
            price: Original price
            quantity: Order quantity
            action: BUY or SELL
            is_entry: True for entry, False for exit
            avg_volume: Average daily volume
            
        Returns:
            Execution price with slippage applied
        """
        slippage = self.calculate(price, quantity, action, avg_volume)
        
        # Slippage direction depends on action
        if action == OrderAction.BUY:
            return price + slippage  # Worse for buyer
        else:
            return price - slippage  # Worse for seller


@dataclass
class CommissionConfig:
    """Configuration for commission calculation."""
    
    model: CommissionModel = CommissionModel.PERCENTAGE
    
    # Fixed model: absolute fee per trade
    fixed_fee: float = 20.0
    
    # Percentage model: % of order value
    percentage: float = 0.001  # 0.1%
    
    # Minimum commission
    minimum: float = 0.0
    
    # Tiered model: list of (volume_threshold, rate) tuples
    # Example: [(100000, 0.001), (500000, 0.0008), (float('inf'), 0.0005)]
    tiers: Optional[list] = None
    
    def calculate(
        self,
        price: float,
        quantity: int,
        total_volume: float = 0.0
    ) -> float:
        """
        Calculate commission for an order.
        
        Args:
            price: Execution price
            quantity: Order quantity
            total_volume: Total trading volume (for tiered model)
            
        Returns:
            Commission amount
        """
        order_value = price * quantity
        
        if self.model == CommissionModel.FIXED:
            commission = self.fixed_fee
            
        elif self.model == CommissionModel.PERCENTAGE:
            commission = order_value * self.percentage
            
        elif self.model == CommissionModel.TIERED:
            if self.tiers is None or not self.tiers:
                # Fall back to percentage
                commission = order_value * self.percentage
            else:
                # Find applicable tier
                rate = self.percentage  # Default
                for threshold, tier_rate in sorted(self.tiers, key=lambda x: x[0]):
                    if total_volume < threshold:
                        rate = tier_rate
                        break
                commission = order_value * rate
        else:
            commission = 0.0
        
        return max(commission, self.minimum)


@dataclass
class OrderExecution:
    """Result of order execution."""
    
    filled: bool
    execution_price: float
    quantity: int
    commission: float
    slippage: float
    total_cost: float  # For buys: price * qty + commission. For sells: price * qty - commission
    
    @property
    def net_value(self) -> float:
        """Net value after costs for the trader."""
        return self.total_cost


class BacktestExecutor:
    """
    Simulates order execution for backtesting.
    
    Handles:
    - Slippage calculation and application
    - Commission calculation
    - Order fill simulation
    - Position value calculations
    """
    
    def __init__(
        self,
        slippage_config: Optional[SlippageConfig] = None,
        commission_config: Optional[CommissionConfig] = None
    ):
        """
        Initialize executor.
        
        Args:
            slippage_config: Slippage calculation config
            commission_config: Commission calculation config
        """
        self.slippage = slippage_config or SlippageConfig()
        self.commission = commission_config or CommissionConfig()
        self._total_volume = 0.0  # Track for tiered commissions
        
        logger.info(
            f"BacktestExecutor initialized: slippage={self.slippage.model.value}, "
            f"commission={self.commission.model.value}"
        )
    
    def execute_entry(
        self,
        price: float,
        quantity: int,
        action: OrderAction,
        avg_volume: Optional[float] = None
    ) -> OrderExecution:
        """
        Execute an entry order.
        
        Args:
            price: Target price
            quantity: Order quantity
            action: BUY or SELL
            avg_volume: Average daily volume for slippage calculation
            
        Returns:
            OrderExecution with fill details
        """
        # Calculate execution price with slippage
        slippage_amount = self.slippage.calculate(price, quantity, action, avg_volume)
        
        if action == OrderAction.BUY:
            execution_price = price + slippage_amount
        else:
            execution_price = price - slippage_amount
        
        # Calculate commission
        commission = self.commission.calculate(execution_price, quantity, self._total_volume)
        
        # Calculate total cost
        order_value = execution_price * quantity
        if action == OrderAction.BUY:
            total_cost = order_value + commission  # Pay for shares + commission
        else:
            total_cost = -order_value + commission  # Receive for shares, pay commission (for shorts)
        
        # Update volume tracking
        self._total_volume += order_value
        
        return OrderExecution(
            filled=True,
            execution_price=execution_price,
            quantity=quantity,
            commission=commission,
            slippage=slippage_amount,
            total_cost=total_cost
        )
    
    def execute_exit(
        self,
        price: float,
        quantity: int,
        action: OrderAction,
        avg_volume: Optional[float] = None
    ) -> OrderExecution:
        """
        Execute an exit order.
        
        Args:
            price: Target price
            quantity: Order quantity
            action: Original position action (BUY for long, SELL for short)
            avg_volume: Average daily volume for slippage calculation
            
        Returns:
            OrderExecution with fill details
        """
        # Exit action is opposite of position action
        exit_action = OrderAction.SELL if action == OrderAction.BUY else OrderAction.BUY
        
        # Calculate execution price with slippage
        slippage_amount = self.slippage.calculate(price, quantity, exit_action, avg_volume)
        
        if exit_action == OrderAction.SELL:
            execution_price = price - slippage_amount  # Worse for seller
        else:
            execution_price = price + slippage_amount  # Worse for buyer
        
        # Calculate commission
        commission = self.commission.calculate(execution_price, quantity, self._total_volume)
        
        # Calculate proceeds
        order_value = execution_price * quantity
        if exit_action == OrderAction.SELL:
            total_cost = order_value - commission  # Receive for shares - commission
        else:
            total_cost = -order_value - commission  # Pay for shares + commission (closing short)
        
        # Update volume tracking
        self._total_volume += order_value
        
        return OrderExecution(
            filled=True,
            execution_price=execution_price,
            quantity=quantity,
            commission=commission,
            slippage=slippage_amount,
            total_cost=total_cost
        )
    
    def calculate_position_size(
        self,
        capital: float,
        risk_per_trade: float,
        entry_price: float,
        stop_loss: float,
        action: OrderAction
    ) -> int:
        """
        Calculate position size based on risk parameters.
        
        Uses fixed fractional position sizing:
        Quantity = (Capital * Risk%) / (Entry - Stop)
        
        Args:
            capital: Available capital
            risk_per_trade: Risk as decimal (e.g., 0.02 for 2%)
            entry_price: Entry price
            stop_loss: Stop loss price
            action: BUY or SELL
            
        Returns:
            Quantity to trade
        """
        risk_amount = capital * risk_per_trade
        
        if action == OrderAction.BUY:
            risk_per_share = entry_price - stop_loss
        else:
            risk_per_share = stop_loss - entry_price
        
        if risk_per_share <= 0:
            return 0
        
        quantity = int(risk_amount / risk_per_share)
        return max(0, quantity)
    
    def check_stop_loss(
        self,
        action: OrderAction,
        stop_loss: float,
        current_high: float,
        current_low: float
    ) -> tuple[bool, float]:
        """
        Check if stop loss is hit.
        
        Args:
            action: Position action (BUY for long, SELL for short)
            stop_loss: Stop loss price
            current_high: Current bar high
            current_low: Current bar low
            
        Returns:
            Tuple of (hit, execution_price)
        """
        if action == OrderAction.BUY:
            # Long position: stop hit if low <= stop
            if current_low <= stop_loss:
                return True, stop_loss
        else:
            # Short position: stop hit if high >= stop
            if current_high >= stop_loss:
                return True, stop_loss
        
        return False, 0.0
    
    def check_target(
        self,
        action: OrderAction,
        target: float,
        current_high: float,
        current_low: float
    ) -> tuple[bool, float]:
        """
        Check if target is hit.
        
        Args:
            action: Position action (BUY for long, SELL for short)
            target: Target price
            current_high: Current bar high
            current_low: Current bar low
            
        Returns:
            Tuple of (hit, execution_price)
        """
        if action == OrderAction.BUY:
            # Long position: target hit if high >= target
            if current_high >= target:
                return True, target
        else:
            # Short position: target hit if low <= target
            if current_low <= target:
                return True, target
        
        return False, 0.0
    
    def reset_volume_tracking(self) -> None:
        """Reset volume tracking for new backtest period."""
        self._total_volume = 0.0


def create_default_executor() -> BacktestExecutor:
    """Create executor with default settings."""
    return BacktestExecutor(
        slippage_config=SlippageConfig(
            model=SlippageModel.PERCENTAGE,
            percentage=0.001  # 0.1%
        ),
        commission_config=CommissionConfig(
            model=CommissionModel.PERCENTAGE,
            percentage=0.001,  # 0.1%
            minimum=20.0
        )
    )


def create_zero_cost_executor() -> BacktestExecutor:
    """Create executor with no costs (for testing)."""
    return BacktestExecutor(
        slippage_config=SlippageConfig(
            model=SlippageModel.FIXED,
            fixed_amount=0.0
        ),
        commission_config=CommissionConfig(
            model=CommissionModel.FIXED,
            fixed_fee=0.0,
            minimum=0.0
        )
    )
