"""
Main risk management system for StockJarvis.
Coordinates position sizing, stop loss management, portfolio risk checks, and circuit breakers.
"""

from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd
import numpy as np

from core.logger import get_logger
from core.position_sizer import (
    BasePositionSizer,
    FixedFractionalSizer,
    KellyCriterionSizer,
    RiskParitySizer,
    ATRBasedSizer,
    PositionSizeResult
)
from core.stop_loss_manager import StopLossManager, StopLossResult
from data.models import Symbol, Position, Order, OrderAction, OrderStatus, TradingMode
from config.risk_config import (
    PositionSizingMethod,
    DEFAULT_RISK_PARAMS,
    PORTFOLIO_RISK_LIMITS,
    CIRCUIT_BREAKER_THRESHOLDS,
    POSITION_SIZING_METHODS,
    get_risk_param,
    get_portfolio_limit,
    get_circuit_breaker_threshold
)
from config import settings

logger = get_logger(__name__)


@dataclass
class RiskCheckResult:
    """Result from risk validation check."""
    
    passed: bool
    reason: str
    violations: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]


@dataclass
class PositionSizeRecommendation:
    """Complete position sizing recommendation."""
    
    symbol: str
    quantity: int
    entry_price: float
    stop_loss: float
    target: float
    position_value: float
    risk_amount: float
    position_pct: float
    sizing_method: str
    stop_method: str
    risk_reward_ratio: float
    passed_checks: bool
    warnings: List[str]
    metadata: Dict[str, Any]


class RiskManager:
    """
    Main risk management system.
    Handles position sizing, stop loss calculation, portfolio risk checks, and circuit breakers.
    """
    
    def __init__(self, session: Session):
        """
        Initialize risk manager.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.logger = get_logger(__name__)
        self.stop_loss_manager = StopLossManager()
        
        # Initialize position sizers
        self.sizers: Dict[str, BasePositionSizer] = {
            PositionSizingMethod.FIXED_FRACTIONAL: FixedFractionalSizer(),
            PositionSizingMethod.KELLY_CRITERION: KellyCriterionSizer(),
            PositionSizingMethod.RISK_PARITY: RiskParitySizer(),
            PositionSizingMethod.ATR_BASED: ATRBasedSizer(),
        }
        
        # Circuit breaker state
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = None
        self.circuit_breaker_triggered_at = None
        
        self.logger.info("Risk Manager initialized")
    
    def calculate_position_size(
        self,
        symbol: str,
        signal_data: Dict[str, Any],
        account_info: Dict[str, Any],
        method: str = None,
        symbol_data: Dict[str, Any] = None
    ) -> PositionSizeRecommendation:
        """
        Calculate recommended position size for a trade.
        
        Args:
            symbol: Stock symbol
            signal_data: Signal data containing action, price, stop_loss, target
            account_info: Account information with balance
            method: Position sizing method (uses default if None)
            symbol_data: Additional symbol data (ATR, volatility, etc.)
        
        Returns:
            PositionSizeRecommendation
        """
        # Get method
        method = method or get_risk_param("default_sizing_method")
        
        if method not in self.sizers:
            self.logger.error(f"Unknown sizing method: {method}, using fixed_fractional")
            method = PositionSizingMethod.FIXED_FRACTIONAL
        
        # Extract signal data
        entry_price = signal_data.get('price', 0)
        action = signal_data.get('action', OrderAction.BUY)
        
        # Get or calculate stop loss
        if 'stop_loss' in signal_data and signal_data['stop_loss'] > 0:
            stop_loss = signal_data['stop_loss']
            stop_method = "signal_provided"
        else:
            stop_result = self.stop_loss_manager.calculate_stop_loss(
                entry_price=entry_price,
                action=action,
                signal_data=signal_data,
                symbol_data=symbol_data
            )
            stop_loss = stop_result.stop_price
            stop_method = stop_result.stop_type
        
        # Get account balance
        account_balance = account_info.get('balance', settings.trading.capital)
        
        # Calculate position size
        sizer = self.sizers[method]
        size_result = sizer.calculate(
            entry_price=entry_price,
            stop_loss=stop_loss,
            account_balance=account_balance,
            symbol_data=symbol_data
        )
        
        # Get target
        target = signal_data.get('target', 0)
        if target == 0:
            # Calculate target based on risk:reward ratio
            risk_per_share = abs(entry_price - stop_loss)
            reward_multiplier = get_risk_param("default_reward_multiplier")
            if action == OrderAction.BUY:
                target = entry_price + (risk_per_share * reward_multiplier)
            else:
                target = entry_price - (risk_per_share * reward_multiplier)
        
        # Calculate risk:reward ratio
        if action == OrderAction.BUY:
            risk = entry_price - stop_loss
            reward = target - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - target
        
        risk_reward_ratio = reward / risk if risk > 0 else 0.0
        
        # Perform risk checks
        risk_check = self._validate_position_risk(
            symbol=symbol,
            quantity=size_result.quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            action=action,
            account_balance=account_balance
        )
        
        # Combine warnings
        all_warnings = size_result.warnings + risk_check.warnings
        if not risk_check.passed:
            all_warnings.extend(risk_check.violations)
        
        recommendation = PositionSizeRecommendation(
            symbol=symbol,
            quantity=size_result.quantity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            position_value=size_result.position_value,
            risk_amount=size_result.risk_amount,
            position_pct=size_result.position_pct,
            sizing_method=method,
            stop_method=stop_method,
            risk_reward_ratio=risk_reward_ratio,
            passed_checks=risk_check.passed,
            warnings=all_warnings,
            metadata={
                **size_result.metadata,
                **risk_check.metadata,
                "account_balance": account_balance,
            }
        )
        
        self.logger.info(
            f"Position recommendation for {symbol}: {recommendation.quantity} shares "
            f"@ ${entry_price:.2f}, SL: ${stop_loss:.2f}, Target: ${target:.2f}, "
            f"R:R: {risk_reward_ratio:.2f}, Method: {method}, Passed: {risk_check.passed}"
        )
        
        return recommendation
    
    def _validate_position_risk(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        target: float,
        action: OrderAction,
        account_balance: float
    ) -> RiskCheckResult:
        """
        Validate a position against risk rules.
        
        Args:
            symbol: Stock symbol
            quantity: Position quantity
            entry_price: Entry price
            stop_loss: Stop loss price
            target: Target price
            action: BUY or SELL
            account_balance: Account balance
        
        Returns:
            RiskCheckResult
        """
        violations = []
        warnings = []
        metadata = {}
        
        # Check if quantity is valid
        if quantity <= 0:
            violations.append("Quantity is zero or negative")
            return RiskCheckResult(
                passed=False,
                reason="Invalid quantity",
                violations=violations,
                warnings=warnings,
                metadata=metadata
            )
        
        # Check circuit breaker
        if self.circuit_breaker_active:
            violations.append(
                f"Circuit breaker active: {self.circuit_breaker_reason}"
            )
            return RiskCheckResult(
                passed=False,
                reason="Circuit breaker active",
                violations=violations,
                warnings=warnings,
                metadata={"circuit_breaker_since": self.circuit_breaker_triggered_at}
            )
        
        # Calculate position value
        position_value = quantity * entry_price
        position_pct = (position_value / account_balance) * 100.0
        
        # Check maximum position size
        max_position_pct = get_portfolio_limit("max_single_position_pct")
        if position_pct > max_position_pct:
            violations.append(
                f"Position size {position_pct:.2f}% exceeds maximum {max_position_pct}%"
            )
        
        # Check risk:reward ratio
        if action == OrderAction.BUY:
            risk = entry_price - stop_loss
            reward = target - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - target
        
        rr_ratio = reward / risk if risk > 0 else 0.0
        min_rr = get_risk_param("min_risk_reward_ratio")
        
        if rr_ratio < min_rr:
            violations.append(
                f"Risk:Reward ratio {rr_ratio:.2f} below minimum {min_rr}"
            )
        
        metadata["risk_reward_ratio"] = rr_ratio
        
        # Check portfolio exposure
        exposure_check = self._check_portfolio_exposure(position_value, account_balance)
        if not exposure_check.passed:
            violations.extend(exposure_check.violations)
        warnings.extend(exposure_check.warnings)
        metadata.update(exposure_check.metadata)
        
        # Check position limits
        limits_check = self._check_position_limits(symbol)
        if not limits_check.passed:
            violations.extend(limits_check.violations)
        warnings.extend(limits_check.warnings)
        
        # Check drawdown
        drawdown_check = self._check_drawdown_limits(account_balance)
        if not drawdown_check.passed:
            violations.extend(drawdown_check.violations)
        
        passed = len(violations) == 0
        reason = "All checks passed" if passed else f"{len(violations)} violations found"
        
        return RiskCheckResult(
            passed=passed,
            reason=reason,
            violations=violations,
            warnings=warnings,
            metadata=metadata
        )
    
    def _check_portfolio_exposure(
        self,
        new_position_value: float,
        account_balance: float
    ) -> RiskCheckResult:
        """
        Check portfolio-level exposure limits.
        
        Args:
            new_position_value: Value of new position
            account_balance: Account balance
        
        Returns:
            RiskCheckResult
        """
        violations = []
        warnings = []
        metadata = {}
        
        # Get current open positions
        open_positions = self.session.query(Position).filter(
            Position.is_open == True,
            Position.trading_mode == TradingMode.LIVE
        ).all()
        
        # Calculate current exposure
        current_exposure = sum(
            pos.quantity * pos.current_price for pos in open_positions
        )
        
        total_exposure = current_exposure + new_position_value
        exposure_pct = (total_exposure / account_balance) * 100.0
        
        metadata["current_exposure"] = current_exposure
        metadata["new_exposure"] = total_exposure
        metadata["exposure_pct"] = exposure_pct
        
        # Check maximum total exposure
        max_exposure = get_portfolio_limit("max_total_exposure_pct")
        if exposure_pct > max_exposure:
            violations.append(
                f"Total exposure {exposure_pct:.2f}% exceeds maximum {max_exposure}%"
            )
        elif exposure_pct > max_exposure * 0.9:
            warnings.append(
                f"Total exposure {exposure_pct:.2f}% approaching limit {max_exposure}%"
            )
        
        passed = len(violations) == 0
        
        return RiskCheckResult(
            passed=passed,
            reason="Exposure check" if passed else "Exposure limit exceeded",
            violations=violations,
            warnings=warnings,
            metadata=metadata
        )
    
    def _check_position_limits(self, symbol: str) -> RiskCheckResult:
        """
        Check position count limits.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            RiskCheckResult
        """
        violations = []
        warnings = []
        
        # Get symbol from database
        symbol_obj = self.session.query(Symbol).filter(
            Symbol.symbol == symbol
        ).first()
        
        if not symbol_obj:
            violations.append(f"Symbol {symbol} not found in database")
            return RiskCheckResult(
                passed=False,
                reason="Symbol not found",
                violations=violations,
                warnings=warnings,
                metadata={}
            )
        
        # Check total open positions
        total_positions = self.session.query(Position).filter(
            Position.is_open == True,
            Position.trading_mode == TradingMode.LIVE
        ).count()
        
        max_positions = get_portfolio_limit("max_open_positions")
        if total_positions >= max_positions:
            violations.append(
                f"Already at maximum positions: {total_positions}/{max_positions}"
            )
        elif total_positions >= max_positions * 0.9:
            warnings.append(
                f"Approaching maximum positions: {total_positions}/{max_positions}"
            )
        
        # Check positions in same symbol
        symbol_positions = self.session.query(Position).filter(
            Position.symbol_id == symbol_obj.id,
            Position.is_open == True,
            Position.trading_mode == TradingMode.LIVE
        ).count()
        
        max_per_symbol = get_portfolio_limit("max_positions_per_symbol")
        if symbol_positions >= max_per_symbol:
            violations.append(
                f"Already at maximum positions for {symbol}: {symbol_positions}/{max_per_symbol}"
            )
        
        passed = len(violations) == 0
        
        return RiskCheckResult(
            passed=passed,
            reason="Position limits OK" if passed else "Position limits exceeded",
            violations=violations,
            warnings=warnings,
            metadata={
                "total_positions": total_positions,
                "symbol_positions": symbol_positions,
            }
        )
    
    def _check_drawdown_limits(self, current_balance: float) -> RiskCheckResult:
        """
        Check drawdown limits and trigger circuit breakers if needed.
        
        Args:
            current_balance: Current account balance
        
        Returns:
            RiskCheckResult
        """
        violations = []
        warnings = []
        metadata = {}
        
        # Get initial capital
        initial_capital = settings.trading.capital
        
        # Calculate total drawdown
        total_drawdown_pct = ((initial_capital - current_balance) / initial_capital) * 100.0
        metadata["total_drawdown_pct"] = total_drawdown_pct
        
        # Check total drawdown
        max_total_dd = get_circuit_breaker_threshold("max_total_drawdown_pct")
        if total_drawdown_pct >= max_total_dd:
            violations.append(
                f"Total drawdown {total_drawdown_pct:.2f}% >= limit {max_total_dd}%"
            )
            self._trigger_circuit_breaker(f"Total drawdown {total_drawdown_pct:.2f}%")
        
        # Calculate daily drawdown
        today = datetime.utcnow().date()
        start_of_day = datetime.combine(today, datetime.min.time())
        
        # Get starting balance for today (from first position/order of the day)
        daily_orders = self.session.query(Order).filter(
            Order.created_at >= start_of_day,
            Order.status == OrderStatus.COMPLETED
        ).all()
        
        if daily_orders:
            # Calculate P&L for today
            daily_pnl = sum(
                (order.average_price - order.price) * order.filled_quantity
                if order.action == OrderAction.SELL else 0
                for order in daily_orders
            )
            
            daily_drawdown_pct = abs(daily_pnl / current_balance) * 100.0 if daily_pnl < 0 else 0.0
            metadata["daily_drawdown_pct"] = daily_drawdown_pct
            
            # Check daily drawdown
            max_daily_dd = get_circuit_breaker_threshold("max_daily_drawdown_pct")
            if daily_drawdown_pct >= max_daily_dd:
                violations.append(
                    f"Daily drawdown {daily_drawdown_pct:.2f}% >= limit {max_daily_dd}%"
                )
                self._trigger_circuit_breaker(f"Daily drawdown {daily_drawdown_pct:.2f}%")
        
        # Check consecutive losses
        recent_positions = self.session.query(Position).filter(
            Position.is_open == False,
            Position.trading_mode == TradingMode.LIVE
        ).order_by(Position.exit_time.desc()).limit(10).all()
        
        consecutive_losses = 0
        for pos in recent_positions:
            if pos.realized_pnl < 0:
                consecutive_losses += 1
            else:
                break
        
        metadata["consecutive_losses"] = consecutive_losses
        max_consecutive = get_circuit_breaker_threshold("max_consecutive_losses")
        
        if consecutive_losses >= max_consecutive:
            violations.append(
                f"Consecutive losses {consecutive_losses} >= limit {max_consecutive}"
            )
            self._trigger_circuit_breaker(f"{consecutive_losses} consecutive losses")
        
        passed = len(violations) == 0
        
        return RiskCheckResult(
            passed=passed,
            reason="Drawdown OK" if passed else "Drawdown limits exceeded",
            violations=violations,
            warnings=warnings,
            metadata=metadata
        )
    
    def _trigger_circuit_breaker(self, reason: str):
        """
        Trigger circuit breaker to halt trading.
        
        Args:
            reason: Reason for triggering
        """
        if not self.circuit_breaker_active:
            self.circuit_breaker_active = True
            self.circuit_breaker_reason = reason
            self.circuit_breaker_triggered_at = datetime.utcnow()
            
            self.logger.critical(
                f"CIRCUIT BREAKER TRIGGERED: {reason} at {self.circuit_breaker_triggered_at}"
            )
            
            # TODO: Send emergency alerts via email/SMS
            # TODO: Close all open positions if configured
    
    def reset_circuit_breaker(self, manual: bool = True) -> bool:
        """
        Reset circuit breaker to resume trading.
        
        Args:
            manual: True if manual reset, False if auto-reset
        
        Returns:
            True if reset successful
        """
        if not self.circuit_breaker_active:
            self.logger.warning("Circuit breaker is not active")
            return False
        
        # Check if manual reset is required
        require_manual = get_circuit_breaker_threshold("require_manual_reset")
        if require_manual and not manual:
            self.logger.warning("Circuit breaker requires manual reset")
            return False
        
        # Check cooldown period
        cooldown_hours = get_circuit_breaker_threshold("circuit_breaker_cooldown_hours")
        if self.circuit_breaker_triggered_at:
            elapsed = datetime.utcnow() - self.circuit_breaker_triggered_at
            if elapsed < timedelta(hours=cooldown_hours):
                self.logger.warning(
                    f"Circuit breaker cooldown not elapsed: "
                    f"{elapsed.total_seconds()/3600:.1f}h / {cooldown_hours}h"
                )
                return False
        
        # Reset
        self.circuit_breaker_active = False
        reset_reason = self.circuit_breaker_reason
        self.circuit_breaker_reason = None
        self.circuit_breaker_triggered_at = None
        
        self.logger.info(
            f"Circuit breaker RESET ({'manual' if manual else 'auto'}). "
            f"Previous reason: {reset_reason}"
        )
        
        return True
    
    def get_portfolio_metrics(self) -> Dict[str, Any]:
        """
        Calculate current portfolio metrics.
        
        Returns:
            Dictionary of portfolio metrics
        """
        # Get open positions
        open_positions = self.session.query(Position).filter(
            Position.is_open == True,
            Position.trading_mode == TradingMode.LIVE
        ).all()
        
        # Calculate metrics
        total_value = sum(pos.quantity * pos.current_price for pos in open_positions)
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in open_positions)
        
        # Get account balance
        account_balance = settings.trading.capital
        
        # Calculate exposure
        exposure_pct = (total_value / account_balance) * 100.0 if account_balance > 0 else 0.0
        
        # Count positions
        num_positions = len(open_positions)
        
        # Get closed positions for performance metrics
        closed_positions = self.session.query(Position).filter(
            Position.is_open == False,
            Position.trading_mode == TradingMode.LIVE
        ).all()
        
        total_realized_pnl = sum(pos.realized_pnl for pos in closed_positions)
        winning_trades = sum(1 for pos in closed_positions if pos.realized_pnl > 0)
        total_trades = len(closed_positions)
        win_rate = (winning_trades / total_trades) if total_trades > 0 else 0.0
        
        return {
            "num_open_positions": num_positions,
            "total_position_value": total_value,
            "exposure_pct": exposure_pct,
            "unrealized_pnl": total_unrealized_pnl,
            "realized_pnl": total_realized_pnl,
            "total_pnl": total_unrealized_pnl + total_realized_pnl,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "win_rate": win_rate,
            "circuit_breaker_active": self.circuit_breaker_active,
            "circuit_breaker_reason": self.circuit_breaker_reason,
        }
    
    def get_position_correlation(self, symbol1: str, symbol2: str, days: int = 60) -> Optional[float]:
        """
        Calculate correlation between two positions.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
            days: Lookback period in days
        
        Returns:
            Correlation coefficient or None if insufficient data
        """
        # This is a placeholder - would need price history
        # In production, fetch price history and calculate correlation
        self.logger.warning("Position correlation calculation not fully implemented")
        return None
