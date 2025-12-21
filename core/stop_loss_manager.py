"""
Stop loss management system.
Implements various stop loss strategies: percentage-based, ATR-based, support/resistance, trailing stops.
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import pandas as pd
import numpy as np

from core.logger import get_logger
from config.risk_config import DEFAULT_RISK_PARAMS, STOP_LOSS_CONFIG
from data.models import OrderAction

logger = get_logger(__name__)


@dataclass
class StopLossResult:
    """Result from stop loss calculation."""
    
    stop_price: float  # Stop loss price
    stop_type: str  # Type of stop (percentage, atr, support, trailing)
    distance_pct: float  # Distance from entry in %
    risk_per_share: float  # Risk amount per share
    metadata: Dict[str, Any]  # Additional calculation details
    warnings: list  # Any warnings generated
    
    def is_valid(self) -> bool:
        """Check if stop loss is valid (price > 0)."""
        return self.stop_price > 0


@dataclass
class TrailingStopState:
    """State of a trailing stop."""
    
    symbol: str
    position_id: int
    entry_price: float
    current_price: float
    stop_price: float
    highest_price: float  # For long positions
    lowest_price: float  # For short positions
    is_activated: bool
    activation_price: float
    distance_pct: float
    last_updated: datetime
    
    def update(self, new_price: float, is_long: bool = True) -> bool:
        """
        Update trailing stop based on new price.
        
        Args:
            new_price: New market price
            is_long: True for long positions, False for short
        
        Returns:
            True if stop was updated, False otherwise
        """
        self.current_price = new_price
        updated = False
        
        if is_long:
            # Update highest price
            if new_price > self.highest_price:
                self.highest_price = new_price
                # Recalculate stop price
                new_stop = new_price * (1 - self.distance_pct / 100.0)
                if new_stop > self.stop_price:
                    self.stop_price = new_stop
                    updated = True
        else:
            # Update lowest price (for short positions)
            if new_price < self.lowest_price:
                self.lowest_price = new_price
                # Recalculate stop price
                new_stop = new_price * (1 + self.distance_pct / 100.0)
                if new_stop < self.stop_price:
                    self.stop_price = new_stop
                    updated = True
        
        if updated:
            self.last_updated = datetime.utcnow()
        
        return updated
    
    def should_trigger(self, current_price: float, is_long: bool = True) -> bool:
        """
        Check if stop should trigger.
        
        Args:
            current_price: Current market price
            is_long: True for long positions, False for short
        
        Returns:
            True if stop should trigger
        """
        if is_long:
            return current_price <= self.stop_price
        else:
            return current_price >= self.stop_price


class StopLossManager:
    """
    Manages stop loss calculations and trailing stops.
    """
    
    def __init__(self):
        """Initialize stop loss manager."""
        self.logger = get_logger(__name__)
        self.trailing_stops: Dict[int, TrailingStopState] = {}  # position_id -> state
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        action: OrderAction,
        signal_data: Dict[str, Any] = None,
        symbol_data: Dict[str, Any] = None,
        stop_type: str = None
    ) -> StopLossResult:
        """
        Calculate stop loss price based on strategy.
        
        Args:
            entry_price: Entry price
            action: BUY or SELL
            signal_data: Signal data (may contain suggested stop_loss)
            symbol_data: Symbol-specific data (ATR, support/resistance, etc.)
            stop_type: Type of stop to calculate (percentage, atr, support_resistance)
        
        Returns:
            StopLossResult with calculated stop price
        """
        signal_data = signal_data or {}
        symbol_data = symbol_data or {}
        
        # Use signal's stop loss if provided
        if 'stop_loss' in signal_data and signal_data['stop_loss'] > 0:
            stop_price = signal_data['stop_loss']
            distance_pct = abs((entry_price - stop_price) / entry_price) * 100.0
            
            return StopLossResult(
                stop_price=stop_price,
                stop_type="signal_provided",
                distance_pct=distance_pct,
                risk_per_share=abs(entry_price - stop_price),
                metadata={"source": "signal"},
                warnings=[]
            )
        
        # Determine stop type
        if stop_type is None:
            stop_type = STOP_LOSS_CONFIG["default_type"]
        
        # Calculate based on type
        if stop_type == "percentage":
            return self._calculate_percentage_stop(entry_price, action, symbol_data)
        elif stop_type == "atr":
            return self._calculate_atr_stop(entry_price, action, symbol_data)
        elif stop_type == "support_resistance":
            return self._calculate_sr_stop(entry_price, action, symbol_data)
        else:
            self.logger.warning(f"Unknown stop type: {stop_type}, using percentage")
            return self._calculate_percentage_stop(entry_price, action, symbol_data)
    
    def _calculate_percentage_stop(
        self,
        entry_price: float,
        action: OrderAction,
        symbol_data: Dict[str, Any]
    ) -> StopLossResult:
        """
        Calculate percentage-based stop loss.
        
        Args:
            entry_price: Entry price
            action: BUY or SELL
            symbol_data: Symbol data (may contain custom stop_pct)
        
        Returns:
            StopLossResult
        """
        # Get stop loss percentage
        stop_pct = symbol_data.get('stop_loss_pct', DEFAULT_RISK_PARAMS["default_stop_loss_pct"])
        
        # Calculate stop price
        if action == OrderAction.BUY:
            stop_price = entry_price * (1 - stop_pct / 100.0)
        else:  # SELL
            stop_price = entry_price * (1 + stop_pct / 100.0)
        
        risk_per_share = abs(entry_price - stop_price)
        
        self.logger.info(
            f"Percentage stop: Entry ${entry_price:.2f}, Stop ${stop_price:.2f} "
            f"({stop_pct:.2f}%), Risk per share: ${risk_per_share:.2f}"
        )
        
        return StopLossResult(
            stop_price=stop_price,
            stop_type="percentage",
            distance_pct=stop_pct,
            risk_per_share=risk_per_share,
            metadata={"stop_pct": stop_pct},
            warnings=[]
        )
    
    def _calculate_atr_stop(
        self,
        entry_price: float,
        action: OrderAction,
        symbol_data: Dict[str, Any]
    ) -> StopLossResult:
        """
        Calculate ATR-based stop loss.
        
        Args:
            entry_price: Entry price
            action: BUY or SELL
            symbol_data: Must contain 'atr' value
        
        Returns:
            StopLossResult
        """
        warnings = []
        
        # Get ATR
        atr = symbol_data.get('atr')
        
        if atr is None or atr <= 0:
            # Fallback to percentage method
            warnings.append("No ATR data, falling back to percentage stop")
            result = self._calculate_percentage_stop(entry_price, action, symbol_data)
            result.warnings.extend(warnings)
            return result
        
        # Get ATR multiplier
        atr_multiplier = symbol_data.get(
            'atr_stop_multiplier',
            STOP_LOSS_CONFIG["atr"]["multiplier"]
        )
        
        # Calculate stop distance
        stop_distance = atr * atr_multiplier
        
        # Apply min/max constraints
        min_stop_pct = STOP_LOSS_CONFIG["atr"]["min_stop_distance_pct"]
        max_stop_pct = STOP_LOSS_CONFIG["atr"]["max_stop_distance_pct"]
        
        stop_distance_pct = (stop_distance / entry_price) * 100.0
        
        if stop_distance_pct < min_stop_pct:
            warnings.append(f"ATR stop {stop_distance_pct:.2f}% < min {min_stop_pct}%, using min")
            stop_distance = entry_price * (min_stop_pct / 100.0)
            stop_distance_pct = min_stop_pct
        elif stop_distance_pct > max_stop_pct:
            warnings.append(f"ATR stop {stop_distance_pct:.2f}% > max {max_stop_pct}%, using max")
            stop_distance = entry_price * (max_stop_pct / 100.0)
            stop_distance_pct = max_stop_pct
        
        # Calculate stop price
        if action == OrderAction.BUY:
            stop_price = entry_price - stop_distance
        else:  # SELL
            stop_price = entry_price + stop_distance
        
        # Ensure positive price
        if stop_price <= 0:
            stop_price = entry_price * 0.5  # 50% stop as safety
            warnings.append("Calculated stop price <= 0, using 50% stop")
        
        risk_per_share = abs(entry_price - stop_price)
        
        self.logger.info(
            f"ATR stop: Entry ${entry_price:.2f}, Stop ${stop_price:.2f}, "
            f"ATR: {atr:.2f}, Multiplier: {atr_multiplier}, Distance: {stop_distance_pct:.2f}%"
        )
        
        return StopLossResult(
            stop_price=stop_price,
            stop_type="atr",
            distance_pct=stop_distance_pct,
            risk_per_share=risk_per_share,
            metadata={
                "atr": atr,
                "atr_multiplier": atr_multiplier,
                "stop_distance": stop_distance,
            },
            warnings=warnings
        )
    
    def _calculate_sr_stop(
        self,
        entry_price: float,
        action: OrderAction,
        symbol_data: Dict[str, Any]
    ) -> StopLossResult:
        """
        Calculate support/resistance-based stop loss.
        
        Args:
            entry_price: Entry price
            action: BUY or SELL
            symbol_data: Must contain 'support' or 'resistance' levels
        
        Returns:
            StopLossResult
        """
        warnings = []
        
        # Get buffer percentage
        buffer_pct = DEFAULT_RISK_PARAMS["support_resistance_buffer_pct"]
        
        if action == OrderAction.BUY:
            # Look for support level below entry
            support = symbol_data.get('support')
            
            if support is None or support >= entry_price:
                warnings.append("No valid support level, falling back to percentage stop")
                result = self._calculate_percentage_stop(entry_price, action, symbol_data)
                result.warnings.extend(warnings)
                return result
            
            # Place stop below support with buffer
            stop_price = support * (1 - buffer_pct / 100.0)
        
        else:  # SELL
            # Look for resistance level above entry
            resistance = symbol_data.get('resistance')
            
            if resistance is None or resistance <= entry_price:
                warnings.append("No valid resistance level, falling back to percentage stop")
                result = self._calculate_percentage_stop(entry_price, action, symbol_data)
                result.warnings.extend(warnings)
                return result
            
            # Place stop above resistance with buffer
            stop_price = resistance * (1 + buffer_pct / 100.0)
        
        distance_pct = abs((entry_price - stop_price) / entry_price) * 100.0
        risk_per_share = abs(entry_price - stop_price)
        
        # Validate stop distance is reasonable
        max_stop_pct = 15.0  # 15% maximum for S/R stops
        if distance_pct > max_stop_pct:
            warnings.append(
                f"S/R stop distance {distance_pct:.2f}% > {max_stop_pct}%, "
                f"falling back to percentage stop"
            )
            result = self._calculate_percentage_stop(entry_price, action, symbol_data)
            result.warnings.extend(warnings)
            return result
        
        self.logger.info(
            f"S/R stop: Entry ${entry_price:.2f}, Stop ${stop_price:.2f}, "
            f"Distance: {distance_pct:.2f}%"
        )
        
        return StopLossResult(
            stop_price=stop_price,
            stop_type="support_resistance",
            distance_pct=distance_pct,
            risk_per_share=risk_per_share,
            metadata={
                "support": symbol_data.get('support'),
                "resistance": symbol_data.get('resistance'),
                "buffer_pct": buffer_pct,
            },
            warnings=warnings
        )
    
    def initialize_trailing_stop(
        self,
        position_id: int,
        symbol: str,
        entry_price: float,
        current_price: float,
        action: OrderAction,
        activation_profit_pct: float = None,
        distance_pct: float = None
    ) -> TrailingStopState:
        """
        Initialize a trailing stop for a position.
        
        Args:
            position_id: Position ID
            symbol: Stock symbol
            entry_price: Entry price
            current_price: Current market price
            action: BUY or SELL
            activation_profit_pct: Profit % to activate trailing stop
            distance_pct: Trailing stop distance %
        
        Returns:
            TrailingStopState
        """
        # Get parameters
        activation_pct = activation_profit_pct or STOP_LOSS_CONFIG["trailing"]["activation_profit_pct"]
        trail_distance = distance_pct or STOP_LOSS_CONFIG["trailing"]["distance_pct"]
        
        # Calculate activation price
        if action == OrderAction.BUY:
            activation_price = entry_price * (1 + activation_pct / 100.0)
            is_activated = current_price >= activation_price
            stop_price = current_price * (1 - trail_distance / 100.0) if is_activated else entry_price * (1 - DEFAULT_RISK_PARAMS["default_stop_loss_pct"] / 100.0)
            highest_price = max(current_price, entry_price)
            lowest_price = 0.0
        else:  # SELL
            activation_price = entry_price * (1 - activation_pct / 100.0)
            is_activated = current_price <= activation_price
            stop_price = current_price * (1 + trail_distance / 100.0) if is_activated else entry_price * (1 + DEFAULT_RISK_PARAMS["default_stop_loss_pct"] / 100.0)
            highest_price = 0.0
            lowest_price = min(current_price, entry_price)
        
        state = TrailingStopState(
            symbol=symbol,
            position_id=position_id,
            entry_price=entry_price,
            current_price=current_price,
            stop_price=stop_price,
            highest_price=highest_price,
            lowest_price=lowest_price,
            is_activated=is_activated,
            activation_price=activation_price,
            distance_pct=trail_distance,
            last_updated=datetime.utcnow()
        )
        
        self.trailing_stops[position_id] = state
        
        self.logger.info(
            f"Trailing stop initialized for {symbol} (ID: {position_id}): "
            f"Entry ${entry_price:.2f}, Current ${current_price:.2f}, "
            f"Stop ${stop_price:.2f}, Activated: {is_activated}"
        )
        
        return state
    
    def update_trailing_stop(
        self,
        position_id: int,
        current_price: float,
        is_long: bool = True
    ) -> Tuple[bool, Optional[TrailingStopState]]:
        """
        Update trailing stop for a position.
        
        Args:
            position_id: Position ID
            current_price: Current market price
            is_long: True for long positions, False for short
        
        Returns:
            Tuple of (was_updated, state)
        """
        if position_id not in self.trailing_stops:
            self.logger.warning(f"No trailing stop found for position {position_id}")
            return False, None
        
        state = self.trailing_stops[position_id]
        
        # Check if should activate
        if not state.is_activated:
            if is_long and current_price >= state.activation_price:
                state.is_activated = True
                self.logger.info(f"Trailing stop activated for position {position_id}")
            elif not is_long and current_price <= state.activation_price:
                state.is_activated = True
                self.logger.info(f"Trailing stop activated for position {position_id}")
        
        # Update stop if activated
        if state.is_activated:
            was_updated = state.update(current_price, is_long)
            if was_updated:
                self.logger.info(
                    f"Trailing stop updated for {state.symbol} (ID: {position_id}): "
                    f"Price ${current_price:.2f}, New stop ${state.stop_price:.2f}"
                )
            return was_updated, state
        
        return False, state
    
    def check_trailing_stop_trigger(
        self,
        position_id: int,
        current_price: float,
        is_long: bool = True
    ) -> bool:
        """
        Check if trailing stop should trigger.
        
        Args:
            position_id: Position ID
            current_price: Current market price
            is_long: True for long positions, False for short
        
        Returns:
            True if stop should trigger
        """
        if position_id not in self.trailing_stops:
            return False
        
        state = self.trailing_stops[position_id]
        should_trigger = state.should_trigger(current_price, is_long)
        
        if should_trigger:
            self.logger.warning(
                f"Trailing stop TRIGGERED for {state.symbol} (ID: {position_id}): "
                f"Price ${current_price:.2f} hit stop ${state.stop_price:.2f}"
            )
        
        return should_trigger
    
    def remove_trailing_stop(self, position_id: int):
        """
        Remove trailing stop for a position.
        
        Args:
            position_id: Position ID
        """
        if position_id in self.trailing_stops:
            del self.trailing_stops[position_id]
            self.logger.info(f"Trailing stop removed for position {position_id}")
    
    def get_trailing_stop(self, position_id: int) -> Optional[TrailingStopState]:
        """
        Get trailing stop state for a position.
        
        Args:
            position_id: Position ID
        
        Returns:
            TrailingStopState or None
        """
        return self.trailing_stops.get(position_id)
    
    def get_all_trailing_stops(self) -> Dict[int, TrailingStopState]:
        """Get all active trailing stops."""
        return self.trailing_stops.copy()
