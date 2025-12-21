# api/routes/positions.py
"""
Position management endpoints for StockJarvis API.
Handles position tracking, updates, and portfolio management.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from datetime import datetime, timedelta

from api.dependencies import get_db, require_active_user
from api.schemas import (
    PositionResponse,
    PositionWithDetails,
    PositionUpdate,
    PositionClose,
    TradingModeEnum,
    SuccessResponse
)
from data.models import Position, Symbol, TradingMode
from core.position_tracker import PositionTracker
from core.logger import get_logger
from config import settings

logger = get_logger(__name__)

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/", response_model=List[PositionWithDetails])
async def list_positions(
    is_open: Optional[bool] = Query(None, description="Filter by open/closed status"),
    trading_mode: Optional[TradingModeEnum] = Query(None, description="Filter by trading mode"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    min_pnl: Optional[float] = Query(None, description="Minimum P&L filter"),
    max_pnl: Optional[float] = Query(None, description="Maximum P&L filter"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get list of positions with optional filters.
    
    Returns all positions matching the specified filters with full details including
    symbol information and current P&L calculations.
    
    **Query Parameters:**
    - is_open: Filter by position status (true=open, false=closed, null=all)
    - trading_mode: Filter by paper or live trading
    - symbol: Filter by specific stock symbol
    - min_pnl: Minimum P&L threshold (for open: unrealized, for closed: realized)
    - max_pnl: Maximum P&L threshold
    - skip: Pagination offset
    - limit: Maximum results to return
    
    **Example Response:**
    ```json
    [
        {
            "id": 123,
            "symbol_id": 45,
            "symbol": "RELIANCE",
            "company_name": "Reliance Industries Ltd",
            "quantity": 100,
            "entry_price": 2450.50,
            "current_price": 2485.75,
            "stop_loss": 2380.00,
            "target": 2590.00,
            "realized_pnl": 0.0,
            "unrealized_pnl": 3525.00,
            "is_open": true,
            "trading_mode": "paper",
            "entry_time": "2025-12-18T09:30:00Z",
            "exit_time": null,
            "updated_at": "2025-12-20T10:15:00Z"
        }
    ]
    ```
    """
    try:
        # Build query with joins
        query = db.query(Position).join(Symbol)
        
        # Apply filters
        if is_open is not None:
            query = query.filter(Position.is_open == is_open)
        
        if trading_mode:
            query = query.filter(Position.trading_mode == TradingMode[trading_mode.upper()])
        
        if symbol:
            query = query.filter(Symbol.symbol == symbol.upper())
        
        if min_pnl is not None:
            if is_open:
                query = query.filter(Position.unrealized_pnl >= min_pnl)
            else:
                query = query.filter(Position.realized_pnl >= min_pnl)
        
        if max_pnl is not None:
            if is_open:
                query = query.filter(Position.unrealized_pnl <= max_pnl)
            else:
                query = query.filter(Position.realized_pnl <= max_pnl)
        
        # Order by entry time (most recent first)
        query = query.order_by(Position.entry_time.desc())
        
        # Pagination
        positions = query.offset(skip).limit(limit).all()
        
        # Build response with symbol details
        result = []
        for pos in positions:
            pos_dict = {
                "id": pos.id,
                "symbol_id": pos.symbol_id,
                "symbol": pos.symbol.symbol,
                "company_name": pos.symbol.company_name,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "stop_loss": pos.stop_loss,
                "target": pos.target,
                "realized_pnl": pos.realized_pnl,
                "unrealized_pnl": pos.unrealized_pnl,
                "is_open": pos.is_open,
                "trading_mode": pos.trading_mode.value,
                "entry_time": pos.entry_time,
                "exit_time": pos.exit_time,
                "updated_at": pos.updated_at
            }
            result.append(pos_dict)
        
        logger.info(
            f"Retrieved {len(result)} positions "
            f"(is_open={is_open}, trading_mode={trading_mode}, symbol={symbol})"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error listing positions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve positions: {str(e)}"
        )


@router.get("/{position_id}", response_model=PositionWithDetails)
async def get_position_details(
    position_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get detailed information about a specific position.
    
    Returns complete position details including current market price,
    unrealized/realized P&L, and symbol information.
    
    **Path Parameters:**
    - position_id: Unique position identifier
    
    **Example Response:**
    ```json
    {
        "id": 123,
        "symbol_id": 45,
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Ltd",
        "quantity": 100,
        "entry_price": 2450.50,
        "current_price": 2485.75,
        "stop_loss": 2380.00,
        "target": 2590.00,
        "realized_pnl": 0.0,
        "unrealized_pnl": 3525.00,
        "is_open": true,
        "trading_mode": "paper",
        "entry_time": "2025-12-18T09:30:00Z",
        "exit_time": null,
        "updated_at": "2025-12-20T10:15:00Z"
    }
    ```
    """
    try:
        position = db.query(Position).join(Symbol).filter(
            Position.id == position_id
        ).first()
        
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position with ID {position_id} not found"
            )
        
        # Build response
        result = {
            "id": position.id,
            "symbol_id": position.symbol_id,
            "symbol": position.symbol.symbol,
            "company_name": position.symbol.company_name,
            "quantity": position.quantity,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "stop_loss": position.stop_loss,
            "target": position.target,
            "realized_pnl": position.realized_pnl,
            "unrealized_pnl": position.unrealized_pnl,
            "is_open": position.is_open,
            "trading_mode": position.trading_mode.value,
            "entry_time": position.entry_time,
            "exit_time": position.exit_time,
            "updated_at": position.updated_at
        }
        
        logger.info(f"Retrieved position details: {position.symbol.symbol} (ID: {position_id})")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving position {position_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve position: {str(e)}"
        )


@router.patch("/{position_id}/stop-loss", response_model=PositionResponse)
async def update_stop_loss(
    position_id: int,
    stop_loss: float = Query(..., gt=0, description="New stop loss price"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Update stop loss for an open position.
    
    Allows manual adjustment of stop loss levels. Validates that the new stop loss
    is logical based on position direction (long/short).
    
    **Path Parameters:**
    - position_id: Position ID to update
    
    **Query Parameters:**
    - stop_loss: New stop loss price (must be > 0)
    
    **Example Request:**
    ```
    PATCH /positions/123/stop-loss?stop_loss=2420.00
    ```
    
    **Example Response:**
    ```json
    {
        "id": 123,
        "symbol_id": 45,
        "quantity": 100,
        "entry_price": 2450.50,
        "current_price": 2485.75,
        "stop_loss": 2420.00,
        "target": 2590.00,
        "realized_pnl": 0.0,
        "unrealized_pnl": 3525.00,
        "is_open": true,
        "trading_mode": "paper",
        "entry_time": "2025-12-18T09:30:00Z",
        "exit_time": null,
        "updated_at": "2025-12-20T10:20:00Z"
    }
    ```
    """
    try:
        position = db.query(Position).filter(Position.id == position_id).first()
        
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position with ID {position_id} not found"
            )
        
        if not position.is_open:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update stop loss for closed position"
            )
        
        # Validate stop loss (basic validation - should be below entry for long positions)
        if position.quantity > 0:  # Long position
            if stop_loss >= position.entry_price:
                logger.warning(
                    f"Stop loss {stop_loss} >= entry price {position.entry_price} "
                    f"for long position {position_id}"
                )
        else:  # Short position
            if stop_loss <= position.entry_price:
                logger.warning(
                    f"Stop loss {stop_loss} <= entry price {position.entry_price} "
                    f"for short position {position_id}"
                )
        
        old_stop_loss = position.stop_loss
        position.stop_loss = stop_loss
        position.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(position)
        
        logger.info(
            f"Updated stop loss for position {position_id}: "
            f"{old_stop_loss:.2f} -> {stop_loss:.2f}"
        )
        
        return position
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating stop loss for position {position_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update stop loss: {str(e)}"
        )


@router.post("/{position_id}/close", response_model=PositionResponse)
async def close_position(
    position_id: int,
    exit_data: PositionClose,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Close an open position at specified exit price.
    
    Closes the position, calculates realized P&L, and updates the database.
    
    **Path Parameters:**
    - position_id: Position ID to close
    
    **Request Body:**
    ```json
    {
        "exit_price": 2485.75
    }
    ```
    
    **Example Response:**
    ```json
    {
        "id": 123,
        "symbol_id": 45,
        "quantity": 100,
        "entry_price": 2450.50,
        "current_price": 2485.75,
        "stop_loss": 2380.00,
        "target": 2590.00,
        "realized_pnl": 3525.00,
        "unrealized_pnl": 0.0,
        "is_open": false,
        "trading_mode": "paper",
        "entry_time": "2025-12-18T09:30:00Z",
        "exit_time": "2025-12-20T10:25:00Z",
        "updated_at": "2025-12-20T10:25:00Z"
    }
    ```
    """
    try:
        position = db.query(Position).filter(Position.id == position_id).first()
        
        if not position:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Position with ID {position_id} not found"
            )
        
        if not position.is_open:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Position is already closed"
            )
        
        # Calculate realized P&L
        if position.quantity > 0:  # Long position
            realized_pnl = (exit_data.exit_price - position.entry_price) * position.quantity
        else:  # Short position
            realized_pnl = (position.entry_price - exit_data.exit_price) * abs(position.quantity)
        
        # Update position
        position.is_open = False
        position.current_price = exit_data.exit_price
        position.realized_pnl = realized_pnl
        position.unrealized_pnl = 0.0
        position.exit_time = datetime.utcnow()
        position.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(position)
        
        logger.info(
            f"Closed position {position_id}: "
            f"Entry ${position.entry_price:.2f}, Exit ${exit_data.exit_price:.2f}, "
            f"P&L: ${realized_pnl:.2f}"
        )
        
        return position
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error closing position {position_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to close position: {str(e)}"
        )


@router.get("/portfolio", response_model=Dict[str, Any])
async def get_portfolio_summary(
    trading_mode: Optional[TradingModeEnum] = Query(None, description="Filter by trading mode"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get comprehensive portfolio summary with aggregated metrics.
    
    Returns portfolio-level metrics including total exposure, P&L, number of positions,
    win rate, and detailed breakdown of open positions.
    
    **Query Parameters:**
    - trading_mode: Filter by paper or live trading (default: all modes)
    
    **Example Response:**
    ```json
    {
        "num_open_positions": 5,
        "num_closed_positions": 23,
        "total_position_value": 125000.50,
        "total_investment": 120000.00,
        "exposure_pct": 62.5,
        "unrealized_pnl": 5000.50,
        "realized_pnl": 12500.75,
        "total_pnl": 17501.25,
        "total_pnl_pct": 14.58,
        "total_trades": 28,
        "winning_trades": 18,
        "losing_trades": 10,
        "win_rate": 0.64,
        "avg_win": 1250.50,
        "avg_loss": -650.25,
        "largest_win": 3500.00,
        "largest_loss": -1200.00,
        "positions": [
            {
                "id": 123,
                "symbol": "RELIANCE",
                "quantity": 100,
                "entry_price": 2450.50,
                "current_price": 2485.75,
                "unrealized_pnl": 3525.00,
                "unrealized_pnl_pct": 1.44,
                "position_value": 248575.00
            }
        ],
        "top_gainers": [
            {"symbol": "TCS", "pnl": 4500.00, "pnl_pct": 5.2}
        ],
        "top_losers": [
            {"symbol": "HDFC", "pnl": -1200.00, "pnl_pct": -2.8}
        ]
    }
    ```
    """
    try:
        # Build query
        query = db.query(Position)
        
        if trading_mode:
            query = query.filter(Position.trading_mode == TradingMode[trading_mode.upper()])
        
        # Get open positions
        open_positions = query.filter(Position.is_open == True).all()
        
        # Get closed positions
        closed_positions = query.filter(Position.is_open == False).all()
        
        # Calculate aggregate metrics
        total_investment = sum(
            abs(pos.entry_price * pos.quantity) for pos in open_positions
        )
        
        total_position_value = sum(
            abs(pos.current_price * pos.quantity) for pos in open_positions
        )
        
        unrealized_pnl = sum(pos.unrealized_pnl for pos in open_positions)
        realized_pnl = sum(pos.realized_pnl for pos in closed_positions)
        total_pnl = unrealized_pnl + realized_pnl
        
        # Calculate win rate
        winning_trades = sum(1 for pos in closed_positions if pos.realized_pnl > 0)
        losing_trades = sum(1 for pos in closed_positions if pos.realized_pnl < 0)
        total_trades = len(closed_positions)
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        
        # Calculate average win/loss
        winning_pnls = [pos.realized_pnl for pos in closed_positions if pos.realized_pnl > 0]
        losing_pnls = [pos.realized_pnl for pos in closed_positions if pos.realized_pnl < 0]
        
        avg_win = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0.0
        avg_loss = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0.0
        
        largest_win = max(winning_pnls) if winning_pnls else 0.0
        largest_loss = min(losing_pnls) if losing_pnls else 0.0
        
        # Calculate exposure percentage
        account_balance = settings.trading.capital
        exposure_pct = (total_position_value / account_balance) * 100.0 if account_balance > 0 else 0.0
        
        # Calculate total P&L percentage
        total_pnl_pct = (total_pnl / account_balance) * 100.0 if account_balance > 0 else 0.0
        
        # Build position details
        position_details = []
        for pos in open_positions:
            investment = abs(pos.entry_price * pos.quantity)
            pnl_pct = (pos.unrealized_pnl / investment) * 100.0 if investment > 0 else 0.0
            
            position_details.append({
                "id": pos.id,
                "symbol": pos.symbol.symbol,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": pos.unrealized_pnl,
                "unrealized_pnl_pct": pnl_pct,
                "position_value": abs(pos.current_price * pos.quantity)
            })
        
        # Sort for top gainers/losers
        position_details_sorted = sorted(
            position_details,
            key=lambda x: x["unrealized_pnl"],
            reverse=True
        )
        
        top_gainers = [
            {
                "symbol": p["symbol"],
                "pnl": p["unrealized_pnl"],
                "pnl_pct": p["unrealized_pnl_pct"]
            }
            for p in position_details_sorted[:3] if p["unrealized_pnl"] > 0
        ]
        
        top_losers = [
            {
                "symbol": p["symbol"],
                "pnl": p["unrealized_pnl"],
                "pnl_pct": p["unrealized_pnl_pct"]
            }
            for p in reversed(position_details_sorted[-3:]) if p["unrealized_pnl"] < 0
        ]
        
        result = {
            "num_open_positions": len(open_positions),
            "num_closed_positions": len(closed_positions),
            "total_position_value": total_position_value,
            "total_investment": total_investment,
            "exposure_pct": exposure_pct,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": realized_pnl,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "largest_win": largest_win,
            "largest_loss": largest_loss,
            "positions": position_details,
            "top_gainers": top_gainers,
            "top_losers": top_losers
        }
        
        logger.info(
            f"Retrieved portfolio summary: {len(open_positions)} open positions, "
            f"Total P&L: ${total_pnl:.2f} ({total_pnl_pct:.2f}%)"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving portfolio summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve portfolio summary: {str(e)}"
        )
