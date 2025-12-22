# api/routes/signals.py
"""
Trading signal endpoints for StockJarvis API.
Handles signal retrieval, filtering, and manual signal generation.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta

from api.dependencies import get_db, require_active_user
from api.schemas import (
    SignalResponse,
    SignalWithDetails,
    SignalCreate,
    OrderActionEnum
)
from data.models import Signal, Symbol, Strategy, OrderAction
from data.repository import repository
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/", response_model=List[SignalWithDetails])
async def list_signals(
    is_executed: Optional[bool] = Query(None, description="Filter by execution status"),
    strategy_id: Optional[int] = Query(None, description="Filter by strategy ID"),
    strategy_name: Optional[str] = Query(None, description="Filter by strategy name"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    action: Optional[OrderActionEnum] = Query(None, description="Filter by action (BUY/SELL)"),
    min_confidence: Optional[float] = Query(None, ge=0, le=1, description="Minimum confidence score"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get list of trading signals with optional filters.
    
    Returns all signals matching the specified criteria with strategy and symbol details.
    
    **Query Parameters:**
    - is_executed: Filter by execution status (true=executed, false=pending, null=all)
    - strategy_id: Filter by specific strategy ID
    - strategy_name: Filter by strategy name (alternative to strategy_id)
    - symbol: Filter by stock symbol
    - action: Filter by BUY or SELL signals
    - min_confidence: Minimum confidence threshold (0.0 to 1.0)
    - start_date: Filter signals created after this date
    - end_date: Filter signals created before this date
    - skip: Pagination offset
    - limit: Maximum results to return
    
    **Example Response:**
    ```json
    [
        {
            "id": 456,
            "strategy_id": 1,
            "strategy_name": "RSI_MACD_Strategy",
            "symbol_id": 45,
            "symbol": "RELIANCE",
            "action": "BUY",
            "price": 2450.50,
            "stop_loss": 2380.00,
            "target": 2590.00,
            "confidence": 0.72,
            "reason": "RSI oversold (28.5) with MACD bullish crossover",
            "is_executed": false,
            "executed_at": null,
            "created_at": "2025-12-20T09:30:00Z"
        }
    ]
    ```
    """
    try:
        # Build query with joins
        query = db.query(Signal).join(Strategy).join(Symbol)
        
        # Apply filters
        if is_executed is not None:
            query = query.filter(Signal.is_executed == is_executed)
        
        if strategy_id is not None:
            query = query.filter(Signal.strategy_id == strategy_id)
        
        if strategy_name:
            query = query.filter(Strategy.name == strategy_name)
        
        if symbol:
            query = query.filter(Symbol.symbol == symbol.upper())
        
        if action:
            query = query.filter(Signal.action == OrderAction[action.upper()])
        
        if min_confidence is not None:
            query = query.filter(Signal.confidence >= min_confidence)
        
        # Date filters
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Signal.created_at >= start_dt)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD"
                )
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # Add one day to include the entire end date
                end_dt = end_dt + timedelta(days=1)
                query = query.filter(Signal.created_at < end_dt)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD"
                )
        
        # Order by creation time (most recent first)
        query = query.order_by(Signal.created_at.desc())
        
        # Pagination
        signals = query.offset(skip).limit(limit).all()
        
        # Build response with details
        result = []
        for sig in signals:
            sig_dict = {
                "id": sig.id,
                "strategy_id": sig.strategy_id,
                "strategy_name": sig.strategy.name,
                "symbol_id": sig.symbol_id,
                "symbol": sig.symbol.symbol,
                "action": sig.action.value,
                "price": sig.price,
                "stop_loss": sig.stop_loss,
                "target": sig.target,
                "confidence": sig.confidence,
                "reason": sig.reason,
                "is_executed": sig.is_executed,
                "executed_at": sig.executed_at,
                "created_at": sig.created_at
            }
            result.append(sig_dict)
        
        logger.info(
            f"Retrieved {len(result)} signals "
            f"(is_executed={is_executed}, symbol={symbol}, action={action})"
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing signals: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve signals: {str(e)}"
        )


@router.get("/recent", response_model=List[SignalWithDetails])
async def get_recent_signals(
    hours: int = Query(24, ge=1, le=168, description="Number of hours to look back (max 168=7 days)"),
    is_executed: Optional[bool] = Query(None, description="Filter by execution status"),
    min_confidence: Optional[float] = Query(0.5, ge=0, le=1, description="Minimum confidence threshold"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get recent trading signals from the last N hours.
    
    Convenience endpoint for retrieving the most recent signals without specifying
    exact dates. Useful for monitoring latest signal generation.
    
    **Query Parameters:**
    - hours: Number of hours to look back (default: 24, max: 168)
    - is_executed: Filter by execution status
    - min_confidence: Minimum confidence threshold (default: 0.5)
    
    **Example Request:**
    ```
    GET /signals/recent?hours=24&is_executed=false&min_confidence=0.65
    ```
    
    **Example Response:**
    ```json
    [
        {
            "id": 456,
            "strategy_id": 1,
            "strategy_name": "RSI_MACD_Strategy",
            "symbol_id": 45,
            "symbol": "RELIANCE",
            "action": "BUY",
            "price": 2450.50,
            "stop_loss": 2380.00,
            "target": 2590.00,
            "confidence": 0.72,
            "reason": "RSI oversold (28.5) with MACD bullish crossover",
            "is_executed": false,
            "executed_at": null,
            "created_at": "2025-12-20T09:30:00Z"
        },
        {
            "id": 457,
            "strategy_id": 2,
            "strategy_name": "BollingerBands_Breakout",
            "symbol_id": 52,
            "symbol": "TCS",
            "action": "SELL",
            "price": 3650.25,
            "stop_loss": 3710.00,
            "target": 3520.00,
            "confidence": 0.68,
            "reason": "Price broke below lower Bollinger Band with high volume",
            "is_executed": false,
            "executed_at": null,
            "created_at": "2025-12-20T10:15:00Z"
        }
    ]
    ```
    """
    try:
        # Calculate cutoff time
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Build query
        query = db.query(Signal).join(Strategy).join(Symbol)
        
        # Apply filters
        query = query.filter(Signal.created_at >= cutoff_time)
        
        if is_executed is not None:
            query = query.filter(Signal.is_executed == is_executed)
        
        if min_confidence is not None:
            query = query.filter(Signal.confidence >= min_confidence)
        
        # Order by creation time (most recent first)
        query = query.order_by(Signal.created_at.desc())
        
        signals = query.all()
        
        # Build response
        result = []
        for sig in signals:
            sig_dict = {
                "id": sig.id,
                "strategy_id": sig.strategy_id,
                "strategy_name": sig.strategy.name,
                "symbol_id": sig.symbol_id,
                "symbol": sig.symbol.symbol,
                "action": sig.action.value,
                "price": sig.price,
                "stop_loss": sig.stop_loss,
                "target": sig.target,
                "confidence": sig.confidence,
                "reason": sig.reason,
                "is_executed": sig.is_executed,
                "executed_at": sig.executed_at,
                "created_at": sig.created_at
            }
            result.append(sig_dict)
        
        logger.info(
            f"Retrieved {len(result)} signals from last {hours} hours "
            f"(is_executed={is_executed}, min_confidence={min_confidence})"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving recent signals: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve recent signals: {str(e)}"
        )


@router.post("/generate", response_model=SignalResponse, status_code=status.HTTP_201_CREATED)
async def generate_manual_signal(
    signal: SignalCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Manually create a trading signal.
    
    Allows manual signal creation for scenarios where automated strategy execution
    isn't used, such as manual trading, external signal sources, or testing.
    
    **Request Body:**
    ```json
    {
        "strategy_name": "Manual_Entry",
        "symbol": "RELIANCE",
        "action": "BUY",
        "price": 2450.50,
        "stop_loss": 2380.00,
        "target": 2590.00,
        "confidence": 0.75,
        "reason": "Manual analysis: Strong support at 2400, RSI oversold"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "id": 458,
        "strategy_id": 5,
        "symbol_id": 45,
        "action": "BUY",
        "price": 2450.50,
        "stop_loss": 2380.00,
        "target": 2590.00,
        "confidence": 0.75,
        "reason": "Manual analysis: Strong support at 2400, RSI oversold",
        "is_executed": false,
        "executed_at": null,
        "created_at": "2025-12-20T11:00:00Z"
    }
    ```
    """
    try:
        # Validate strategy exists
        strategy = db.query(Strategy).filter(
            Strategy.name == signal.strategy_name
        ).first()
        
        if not strategy:
            # Create a "Manual" strategy if it doesn't exist
            strategy = Strategy(
                name=signal.strategy_name,
                description="Manual signal entry",
                is_active=True,
                is_validated=False
            )
            db.add(strategy)
            db.flush()
            logger.info(f"Created new strategy: {signal.strategy_name}")
        
        # Validate symbol exists
        symbol = db.query(Symbol).filter(
            Symbol.symbol == signal.symbol.upper()
        ).first()
        
        if not symbol:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{signal.symbol}' not found in database"
            )
        
        if not symbol.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Symbol '{signal.symbol}' is not active"
            )
        
        # Validate signal parameters
        if signal.action == OrderActionEnum.BUY:
            if signal.stop_loss >= signal.price:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Stop loss must be below entry price for BUY signal"
                )
            if signal.target <= signal.price:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Target must be above entry price for BUY signal"
                )
        else:  # SELL
            if signal.stop_loss <= signal.price:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Stop loss must be above entry price for SELL signal"
                )
            if signal.target >= signal.price:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Target must be below entry price for SELL signal"
                )
        
        # Calculate risk:reward ratio
        if signal.action == OrderActionEnum.BUY:
            risk = signal.price - signal.stop_loss
            reward = signal.target - signal.price
        else:
            risk = signal.stop_loss - signal.price
            reward = signal.price - signal.target
        
        rr_ratio = reward / risk if risk > 0 else 0.0
        
        if rr_ratio < 1.0:
            logger.warning(
                f"Poor risk:reward ratio {rr_ratio:.2f} for signal: "
                f"{signal.action.value} {signal.symbol}"
            )
        
        # Create signal
        db_signal = Signal(
            strategy_id=strategy.id,
            symbol_id=symbol.id,
            action=OrderAction[signal.action.upper()],
            price=signal.price,
            stop_loss=signal.stop_loss,
            target=signal.target,
            confidence=signal.confidence,
            reason=signal.reason,
            is_executed=False
        )
        
        db.add(db_signal)
        db.commit()
        db.refresh(db_signal)
        
        logger.info(
            f"Manual signal created: {signal.action.value} {signal.symbol} @ {signal.price:.2f} "
            f"(ID: {db_signal.id}, R:R: {rr_ratio:.2f})"
        )
        
        return db_signal
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating manual signal: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create signal: {str(e)}"
        )


@router.get("/{signal_id}", response_model=SignalWithDetails)
async def get_signal_details(
    signal_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get detailed information about a specific signal.
    
    **Path Parameters:**
    - signal_id: Unique signal identifier
    
    **Example Response:**
    ```json
    {
        "id": 456,
        "strategy_id": 1,
        "strategy_name": "RSI_MACD_Strategy",
        "symbol_id": 45,
        "symbol": "RELIANCE",
        "action": "BUY",
        "price": 2450.50,
        "stop_loss": 2380.00,
        "target": 2590.00,
        "confidence": 0.72,
        "reason": "RSI oversold (28.5) with MACD bullish crossover",
        "is_executed": false,
        "executed_at": null,
        "created_at": "2025-12-20T09:30:00Z"
    }
    ```
    """
    try:
        signal = db.query(Signal).join(Strategy).join(Symbol).filter(
            Signal.id == signal_id
        ).first()
        
        if not signal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal with ID {signal_id} not found"
            )
        
        # Build response
        result = {
            "id": signal.id,
            "strategy_id": signal.strategy_id,
            "strategy_name": signal.strategy.name,
            "symbol_id": signal.symbol_id,
            "symbol": signal.symbol.symbol,
            "action": signal.action.value,
            "price": signal.price,
            "stop_loss": signal.stop_loss,
            "target": signal.target,
            "confidence": signal.confidence,
            "reason": signal.reason,
            "is_executed": signal.is_executed,
            "executed_at": signal.executed_at,
            "created_at": signal.created_at
        }
        
        logger.info(f"Retrieved signal details: {signal.symbol.symbol} (ID: {signal_id})")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving signal {signal_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve signal: {str(e)}"
        )


@router.delete("/{signal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signal(
    signal_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Delete a signal.
    
    Only unexecuted signals can be deleted. Executed signals are preserved for
    historical tracking.
    
    **Path Parameters:**
    - signal_id: Signal ID to delete
    
    **Returns:** 204 No Content on success
    """
    try:
        signal = db.query(Signal).filter(Signal.id == signal_id).first()
        
        if not signal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal with ID {signal_id} not found"
            )
        
        if signal.is_executed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete executed signal. Executed signals are preserved for history."
            )
        
        db.delete(signal)
        db.commit()
        
        logger.info(f"Deleted signal {signal_id}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting signal {signal_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete signal: {str(e)}"
        )
