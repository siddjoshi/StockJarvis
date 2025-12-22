# api/routes/risk.py
"""
Risk management endpoints for StockJarvis API.
Handles portfolio risk metrics, position sizing, and circuit breaker management.
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from api.dependencies import get_db, require_active_user
from api.schemas import OrderActionEnum, SuccessResponse
from data.models import Position, TradingMode
from core.risk_manager import RiskManager
from core.logger import get_logger
from config import settings

logger = get_logger(__name__)

router = APIRouter()


@router.get("/portfolio", response_model=Dict[str, Any])
async def get_portfolio_risk_metrics(
    trading_mode: Optional[str] = Query(None, description="Filter by trading mode (paper/live)"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get comprehensive portfolio risk metrics.
    
    Returns portfolio-level risk metrics including exposure, drawdown, win rate,
    position counts, and circuit breaker status.
    
    **Query Parameters:**
    - trading_mode: Filter by paper or live trading (default: all)
    
    **Example Response:**
    ```json
    {
        "num_open_positions": 5,
        "total_position_value": 125000.50,
        "exposure_pct": 62.5,
        "unrealized_pnl": 5000.50,
        "realized_pnl": 12500.75,
        "total_pnl": 17501.25,
        "total_trades": 28,
        "winning_trades": 18,
        "losing_trades": 10,
        "win_rate": 0.64,
        "circuit_breaker_active": false,
        "circuit_breaker_reason": null,
        "risk_limits": {
            "max_single_position_pct": 10.0,
            "max_total_exposure_pct": 80.0,
            "max_open_positions": 10,
            "max_daily_drawdown_pct": 5.0,
            "max_total_drawdown_pct": 15.0
        },
        "current_metrics": {
            "largest_position_pct": 8.5,
            "total_exposure_pct": 62.5,
            "daily_drawdown_pct": 0.0,
            "total_drawdown_pct": 0.0
        }
    }
    ```
    """
    try:
        # Create risk manager instance
        risk_manager = RiskManager(db)
        
        # Get portfolio metrics
        metrics = risk_manager.get_portfolio_metrics()
        
        # Get risk limits from config
        from config.risk_config import get_portfolio_limit, get_circuit_breaker_threshold
        
        risk_limits = {
            "max_single_position_pct": get_portfolio_limit("max_single_position_pct"),
            "max_total_exposure_pct": get_portfolio_limit("max_total_exposure_pct"),
            "max_open_positions": get_portfolio_limit("max_open_positions"),
            "max_daily_drawdown_pct": get_circuit_breaker_threshold("max_daily_drawdown_pct"),
            "max_total_drawdown_pct": get_circuit_breaker_threshold("max_total_drawdown_pct"),
            "max_consecutive_losses": get_circuit_breaker_threshold("max_consecutive_losses")
        }
        
        # Calculate current drawdown
        account_balance = settings.trading.capital
        initial_capital = settings.trading.capital
        total_drawdown_pct = 0.0
        
        if metrics.get("total_pnl", 0) < 0:
            total_drawdown_pct = abs(metrics["total_pnl"] / initial_capital) * 100.0
        
        # Calculate largest position percentage
        positions = db.query(Position).filter(
            Position.is_open == True,
            Position.trading_mode == TradingMode.LIVE
        ).all()
        
        largest_position_pct = 0.0
        if positions:
            largest_position_value = max(
                abs(pos.current_price * pos.quantity) for pos in positions
            )
            largest_position_pct = (largest_position_value / account_balance) * 100.0 if account_balance > 0 else 0.0
        
        current_metrics = {
            "largest_position_pct": round(largest_position_pct, 2),
            "total_exposure_pct": round(metrics.get("exposure_pct", 0.0), 2),
            "daily_drawdown_pct": 0.0,  # TODO: Implement daily tracking
            "total_drawdown_pct": round(total_drawdown_pct, 2)
        }
        
        response = {
            **metrics,
            "risk_limits": risk_limits,
            "current_metrics": current_metrics
        }
        
        logger.info(
            f"Retrieved portfolio risk metrics: "
            f"{metrics['num_open_positions']} positions, "
            f"Exposure: {metrics.get('exposure_pct', 0):.2f}%, "
            f"Circuit breaker: {metrics['circuit_breaker_active']}"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error retrieving portfolio risk metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve risk metrics: {str(e)}"
        )


@router.get("/position-size", response_model=Dict[str, Any])
async def calculate_position_size(
    symbol: str = Query(..., description="Stock symbol"),
    action: OrderActionEnum = Query(..., description="BUY or SELL"),
    entry_price: float = Query(..., gt=0, description="Entry price"),
    stop_loss: Optional[float] = Query(None, gt=0, description="Stop loss price (optional)"),
    target: Optional[float] = Query(None, gt=0, description="Target price (optional)"),
    method: Optional[str] = Query(None, description="Position sizing method (fixed_fractional, kelly, etc.)"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Calculate recommended position size for a trade.
    
    Uses risk management rules to determine optimal position size based on
    account balance, risk tolerance, and trade parameters.
    
    **Query Parameters:**
    - symbol: Stock symbol to trade
    - action: BUY or SELL
    - entry_price: Planned entry price
    - stop_loss: Stop loss price (optional, will be calculated if not provided)
    - target: Target price (optional, will be calculated if not provided)
    - method: Position sizing method (default: fixed_fractional)
    
    **Available Methods:**
    - fixed_fractional: Risk a fixed percentage of capital per trade
    - kelly_criterion: Kelly formula based on win rate and R:R
    - risk_parity: Equal risk allocation across positions
    - atr_based: ATR-based position sizing
    
    **Example Request:**
    ```
    GET /risk/position-size?symbol=RELIANCE&action=BUY&entry_price=2450.50&stop_loss=2380.00&target=2590.00
    ```
    
    **Example Response:**
    ```json
    {
        "symbol": "RELIANCE",
        "quantity": 40,
        "entry_price": 2450.50,
        "stop_loss": 2380.00,
        "target": 2590.00,
        "position_value": 98020.00,
        "risk_amount": 2820.00,
        "position_pct": 9.8,
        "sizing_method": "fixed_fractional",
        "stop_method": "signal_provided",
        "risk_reward_ratio": 1.98,
        "passed_checks": true,
        "warnings": [],
        "metadata": {
            "account_balance": 100000.0,
            "risk_per_trade_pct": 2.0,
            "max_position_size_pct": 10.0
        }
    }
    ```
    """
    try:
        # Validate symbol exists
        from data.models import Symbol
        symbol_obj = db.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
        
        if not symbol_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{symbol}' not found"
            )
        
        # Create risk manager
        risk_manager = RiskManager(db)
        
        # Prepare signal data
        signal_data = {
            "action": action.upper(),
            "price": entry_price,
            "stop_loss": stop_loss if stop_loss else 0,
            "target": target if target else 0
        }
        
        # Get account info
        account_info = {
            "balance": settings.trading.capital
        }
        
        # Calculate position size
        recommendation = risk_manager.calculate_position_size(
            symbol=symbol.upper(),
            signal_data=signal_data,
            account_info=account_info,
            method=method,
            symbol_data=None  # TODO: Add symbol-specific data (ATR, volatility, etc.)
        )
        
        # Build response
        response = {
            "symbol": recommendation.symbol,
            "quantity": recommendation.quantity,
            "entry_price": recommendation.entry_price,
            "stop_loss": recommendation.stop_loss,
            "target": recommendation.target,
            "position_value": recommendation.position_value,
            "risk_amount": recommendation.risk_amount,
            "position_pct": recommendation.position_pct,
            "sizing_method": recommendation.sizing_method,
            "stop_method": recommendation.stop_method,
            "risk_reward_ratio": recommendation.risk_reward_ratio,
            "passed_checks": recommendation.passed_checks,
            "warnings": recommendation.warnings,
            "metadata": recommendation.metadata
        }
        
        logger.info(
            f"Calculated position size for {symbol}: {recommendation.quantity} shares "
            f"@ ${entry_price:.2f}, Risk: ${recommendation.risk_amount:.2f} "
            f"({recommendation.position_pct:.2f}%), Passed: {recommendation.passed_checks}"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating position size: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate position size: {str(e)}"
        )


@router.get("/circuit-breaker", response_model=Dict[str, Any])
async def get_circuit_breaker_status(
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get current circuit breaker status.
    
    Circuit breakers automatically halt trading when risk thresholds are exceeded,
    such as daily/total drawdown limits or consecutive losses.
    
    **Example Response:**
    ```json
    {
        "active": false,
        "reason": null,
        "triggered_at": null,
        "can_reset": true,
        "thresholds": {
            "max_daily_drawdown_pct": 5.0,
            "max_total_drawdown_pct": 15.0,
            "max_consecutive_losses": 5,
            "cooldown_hours": 24,
            "require_manual_reset": true
        },
        "current_status": {
            "daily_drawdown_pct": 0.0,
            "total_drawdown_pct": 0.0,
            "consecutive_losses": 0
        }
    }
    ```
    """
    try:
        # Create risk manager
        risk_manager = RiskManager(db)
        
        # Get circuit breaker thresholds
        from config.risk_config import get_circuit_breaker_threshold
        
        thresholds = {
            "max_daily_drawdown_pct": get_circuit_breaker_threshold("max_daily_drawdown_pct"),
            "max_total_drawdown_pct": get_circuit_breaker_threshold("max_total_drawdown_pct"),
            "max_consecutive_losses": get_circuit_breaker_threshold("max_consecutive_losses"),
            "cooldown_hours": get_circuit_breaker_threshold("circuit_breaker_cooldown_hours"),
            "require_manual_reset": get_circuit_breaker_threshold("require_manual_reset")
        }
        
        # Calculate current status
        from datetime import datetime, timedelta
        
        # Get recent closed positions for consecutive losses
        recent_positions = db.query(Position).filter(
            Position.is_open == False,
            Position.trading_mode == TradingMode.LIVE
        ).order_by(Position.exit_time.desc()).limit(10).all()
        
        consecutive_losses = 0
        for pos in recent_positions:
            if pos.realized_pnl < 0:
                consecutive_losses += 1
            else:
                break
        
        current_status = {
            "daily_drawdown_pct": 0.0,  # TODO: Implement daily tracking
            "total_drawdown_pct": 0.0,  # TODO: Calculate from total P&L
            "consecutive_losses": consecutive_losses
        }
        
        # Check if can reset
        can_reset = True
        if risk_manager.circuit_breaker_active and risk_manager.circuit_breaker_triggered_at:
            elapsed = datetime.utcnow() - risk_manager.circuit_breaker_triggered_at
            cooldown = timedelta(hours=thresholds["cooldown_hours"])
            can_reset = elapsed >= cooldown
        
        response = {
            "active": risk_manager.circuit_breaker_active,
            "reason": risk_manager.circuit_breaker_reason,
            "triggered_at": risk_manager.circuit_breaker_triggered_at,
            "can_reset": can_reset,
            "thresholds": thresholds,
            "current_status": current_status
        }
        
        logger.info(
            f"Circuit breaker status: Active={risk_manager.circuit_breaker_active}, "
            f"Consecutive losses={consecutive_losses}"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error retrieving circuit breaker status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve circuit breaker status: {str(e)}"
        )


@router.post("/circuit-breaker/reset", response_model=SuccessResponse)
async def reset_circuit_breaker(
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Manually reset the circuit breaker to resume trading.
    
    This endpoint allows authorized users to reset the circuit breaker after
    it has been triggered, subject to cooldown period and manual reset requirements.
    
    **Requirements:**
    - Circuit breaker must be active
    - Cooldown period must have elapsed
    - User must have appropriate permissions
    
    **Example Response:**
    ```json
    {
        "success": true,
        "message": "Circuit breaker reset successfully. Trading resumed.",
        "data": {
            "previous_reason": "Daily drawdown 5.2%",
            "triggered_at": "2025-12-20T10:00:00Z",
            "reset_at": "2025-12-21T10:00:00Z",
            "cooldown_elapsed_hours": 24.0
        }
    }
    ```
    """
    try:
        # Create risk manager
        risk_manager = RiskManager(db)
        
        # Check if circuit breaker is active
        if not risk_manager.circuit_breaker_active:
            return SuccessResponse(
                success=True,
                message="Circuit breaker is not active. No reset needed.",
                data={"active": False}
            )
        
        # Attempt reset
        previous_reason = risk_manager.circuit_breaker_reason
        triggered_at = risk_manager.circuit_breaker_triggered_at
        
        success = risk_manager.reset_circuit_breaker(manual=True)
        
        if not success:
            # Get reason why reset failed
            from datetime import datetime, timedelta
            from config.risk_config import get_circuit_breaker_threshold
            
            cooldown_hours = get_circuit_breaker_threshold("circuit_breaker_cooldown_hours")
            
            if triggered_at:
                elapsed = datetime.utcnow() - triggered_at
                remaining = timedelta(hours=cooldown_hours) - elapsed
                remaining_hours = remaining.total_seconds() / 3600.0
                
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot reset circuit breaker yet. "
                           f"Cooldown period: {remaining_hours:.1f} hours remaining."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Circuit breaker reset failed. Check cooldown period and permissions."
                )
        
        # Calculate elapsed time
        from datetime import datetime
        reset_at = datetime.utcnow()
        cooldown_elapsed_hours = 0.0
        
        if triggered_at:
            cooldown_elapsed_hours = (reset_at - triggered_at).total_seconds() / 3600.0
        
        logger.warning(
            f"Circuit breaker RESET by user {current_user.username}. "
            f"Previous reason: {previous_reason}, "
            f"Elapsed: {cooldown_elapsed_hours:.1f} hours"
        )
        
        return SuccessResponse(
            success=True,
            message="Circuit breaker reset successfully. Trading resumed.",
            data={
                "previous_reason": previous_reason,
                "triggered_at": triggered_at,
                "reset_at": reset_at,
                "cooldown_elapsed_hours": round(cooldown_elapsed_hours, 1)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting circuit breaker: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset circuit breaker: {str(e)}"
        )


@router.post("/circuit-breaker/trigger", response_model=SuccessResponse)
async def trigger_circuit_breaker_manually(
    reason: str = Query(..., description="Reason for triggering circuit breaker"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Manually trigger the circuit breaker to halt trading.
    
    This emergency endpoint allows authorized users to immediately halt all trading
    activity for risk management purposes.
    
    **Query Parameters:**
    - reason: Reason for manually triggering the circuit breaker
    
    **Example Request:**
    ```
    POST /risk/circuit-breaker/trigger?reason=Market%20volatility%20too%20high
    ```
    
    **Example Response:**
    ```json
    {
        "success": true,
        "message": "Circuit breaker triggered manually. All trading halted.",
        "data": {
            "reason": "Market volatility too high",
            "triggered_by": "admin_user",
            "triggered_at": "2025-12-20T14:30:00Z"
        }
    }
    ```
    """
    try:
        # Create risk manager
        risk_manager = RiskManager(db)
        
        # Check if already active
        if risk_manager.circuit_breaker_active:
            return SuccessResponse(
                success=True,
                message="Circuit breaker is already active.",
                data={
                    "already_active": True,
                    "reason": risk_manager.circuit_breaker_reason,
                    "triggered_at": risk_manager.circuit_breaker_triggered_at
                }
            )
        
        # Trigger circuit breaker
        from datetime import datetime
        
        risk_manager.circuit_breaker_active = True
        risk_manager.circuit_breaker_reason = f"Manual trigger by {current_user.username}: {reason}"
        risk_manager.circuit_breaker_triggered_at = datetime.utcnow()
        
        logger.critical(
            f"Circuit breaker MANUALLY TRIGGERED by {current_user.username}. "
            f"Reason: {reason}"
        )
        
        return SuccessResponse(
            success=True,
            message="Circuit breaker triggered manually. All trading halted.",
            data={
                "reason": reason,
                "triggered_by": current_user.username,
                "triggered_at": risk_manager.circuit_breaker_triggered_at
            }
        )
        
    except Exception as e:
        logger.error(f"Error triggering circuit breaker: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger circuit breaker: {str(e)}"
        )


@router.get("/correlation/{symbol1}/{symbol2}", response_model=Dict[str, Any])
async def get_position_correlation(
    symbol1: str,
    symbol2: str,
    days: int = Query(60, ge=7, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Calculate correlation between two symbols.
    
    Useful for portfolio diversification and understanding position relationships.
    
    **Path Parameters:**
    - symbol1: First stock symbol
    - symbol2: Second stock symbol
    
    **Query Parameters:**
    - days: Lookback period for correlation calculation (default: 60)
    
    **Example Response:**
    ```json
    {
        "symbol1": "RELIANCE",
        "symbol2": "TCS",
        "correlation": 0.45,
        "lookback_days": 60,
        "interpretation": "moderate positive correlation",
        "recommendation": "Positions show moderate positive correlation. Consider diversification."
    }
    ```
    """
    try:
        # Validate symbols
        from data.models import Symbol
        
        sym1 = db.query(Symbol).filter(Symbol.symbol == symbol1.upper()).first()
        sym2 = db.query(Symbol).filter(Symbol.symbol == symbol2.upper()).first()
        
        if not sym1 or not sym2:
            missing = []
            if not sym1:
                missing.append(symbol1)
            if not sym2:
                missing.append(symbol2)
            
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbols not found: {', '.join(missing)}"
            )
        
        # Create risk manager
        risk_manager = RiskManager(db)
        
        # Calculate correlation
        correlation = risk_manager.get_position_correlation(
            symbol1.upper(),
            symbol2.upper(),
            days=days
        )
        
        # For now, return placeholder since implementation is not complete
        if correlation is None:
            correlation = 0.0  # Placeholder
            logger.warning(
                f"Correlation calculation not fully implemented. "
                f"Returning placeholder for {symbol1}-{symbol2}"
            )
        
        # Interpret correlation
        abs_corr = abs(correlation)
        if abs_corr < 0.3:
            interpretation = "weak correlation"
            recommendation = "Positions are relatively independent. Good for diversification."
        elif abs_corr < 0.7:
            interpretation = "moderate correlation"
            recommendation = "Positions show moderate correlation. Consider diversification."
        else:
            interpretation = "strong correlation"
            recommendation = "Positions are highly correlated. May increase portfolio risk."
        
        if correlation < 0:
            interpretation = f"negative {interpretation}"
        elif correlation > 0:
            interpretation = f"positive {interpretation}"
        
        response = {
            "symbol1": symbol1.upper(),
            "symbol2": symbol2.upper(),
            "correlation": round(correlation, 3),
            "lookback_days": days,
            "interpretation": interpretation,
            "recommendation": recommendation
        }
        
        logger.info(
            f"Calculated correlation between {symbol1}-{symbol2}: {correlation:.3f} "
            f"(lookback: {days} days)"
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error calculating correlation for {symbol1}-{symbol2}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate correlation: {str(e)}"
        )
