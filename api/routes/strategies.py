# api/routes/strategies.py
"""
Strategy management endpoints for StockJarvis API.
Handles strategy registration, execution, and retrieval of available strategies.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime

from api.dependencies import get_db, require_active_user
from api.schemas import (
    StrategyResponse,
    StrategyCreate,
    StrategyUpdate,
    SignalResponse,
    SuccessResponse
)
from data.models import Strategy, Symbol, Signal, OrderAction
from data.repository import repository
from core.strategy_engine import registry, Strategy as StrategyClass
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("/", response_model=List[StrategyResponse])
async def list_all_strategies(
    active_only: bool = Query(True, description="Filter for active strategies only"),
    validated_only: bool = Query(False, description="Filter for validated strategies only"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get list of all registered strategies.
    
    Returns strategies from database with performance metrics and validation status.
    
    **Query Parameters:**
    - active_only: Only return active strategies (default: true)
    - validated_only: Only return validated strategies (default: false)
    - skip: Pagination offset
    - limit: Maximum results to return
    
    **Example Response:**
    ```json
    [
        {
            "id": 1,
            "name": "RSI_MACD_Strategy",
            "description": "Combined RSI and MACD momentum strategy",
            "parameters": {"rsi_period": 14, "macd_fast": 12},
            "backtest_accuracy": 0.68,
            "backtest_sharpe": 1.85,
            "backtest_max_drawdown": 0.12,
            "is_active": true,
            "is_validated": true,
            "created_at": "2025-01-15T10:30:00Z",
            "updated_at": "2025-01-20T14:22:00Z"
        }
    ]
    ```
    """
    try:
        query = db.query(Strategy)
        
        if active_only:
            query = query.filter(Strategy.is_active == True)
        
        if validated_only:
            query = query.filter(Strategy.is_validated == True)
        
        strategies = query.offset(skip).limit(limit).all()
        
        logger.info(
            f"Retrieved {len(strategies)} strategies "
            f"(active_only={active_only}, validated_only={validated_only})"
        )
        
        return strategies
        
    except Exception as e:
        logger.error(f"Error listing strategies: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve strategies: {str(e)}"
        )


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy_details(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get detailed information about a specific strategy.
    
    **Path Parameters:**
    - strategy_id: Unique strategy identifier
    
    **Example Response:**
    ```json
    {
        "id": 1,
        "name": "RSI_MACD_Strategy",
        "description": "Combined RSI and MACD momentum strategy for swing trading",
        "parameters": {
            "rsi_period": 14,
            "rsi_overbought": 70,
            "rsi_oversold": 30,
            "macd_fast": 12,
            "macd_slow": 26,
            "macd_signal": 9
        },
        "backtest_accuracy": 0.68,
        "backtest_sharpe": 1.85,
        "backtest_max_drawdown": 0.12,
        "is_active": true,
        "is_validated": true,
        "created_at": "2025-01-15T10:30:00Z",
        "updated_at": "2025-01-20T14:22:00Z"
    }
    ```
    """
    try:
        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with ID {strategy_id} not found"
            )
        
        logger.info(f"Retrieved strategy details: {strategy.name} (ID: {strategy_id})")
        
        return strategy
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve strategy: {str(e)}"
        )


@router.post("/execute", response_model=List[SignalResponse])
async def execute_strategy(
    strategy_name: str = Query(..., description="Name of strategy to execute"),
    symbols: List[str] = Query(..., description="List of symbols to scan"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Execute a strategy on specified symbols to generate trading signals.
    
    Runs the strategy analysis on provided symbols and returns generated signals.
    
    **Query Parameters:**
    - strategy_name: Name of the strategy to execute (must be registered)
    - symbols: List of stock symbols to analyze (e.g., ["RELIANCE", "TCS", "INFY"])
    
    **Example Request:**
    ```
    POST /strategies/execute?strategy_name=RSI_MACD_Strategy&symbols=RELIANCE&symbols=TCS
    ```
    
    **Example Response:**
    ```json
    [
        {
            "id": 123,
            "strategy_id": 1,
            "symbol_id": 45,
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
        # Validate strategy exists in database
        strategy_db = db.query(Strategy).filter(Strategy.name == strategy_name).first()
        
        if not strategy_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy '{strategy_name}' not found in database"
            )
        
        if not strategy_db.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Strategy '{strategy_name}' is not active"
            )
        
        if not strategy_db.is_validated:
            logger.warning(f"Executing unvalidated strategy: {strategy_name}")
        
        # Get strategy instance from registry
        strategy_instance = registry.get(strategy_name)
        
        if not strategy_instance:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy '{strategy_name}' not found in registry. "
                       f"It may not be loaded or initialized."
            )
        
        # Validate symbols exist
        symbol_objs = db.query(Symbol).filter(
            Symbol.symbol.in_([s.upper() for s in symbols]),
            Symbol.is_active == True
        ).all()
        
        if not symbol_objs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No valid active symbols found"
            )
        
        # Execute strategy on each symbol
        signals_generated = []
        
        for symbol_obj in symbol_objs:
            try:
                # Get price data for the symbol
                from datetime import timedelta
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=strategy_instance.get_required_history() + 10)
                
                df = repository.get_prices(
                    symbol=symbol_obj.symbol,
                    start_date=start_date,
                    end_date=end_date
                )
                
                if df.empty:
                    logger.warning(f"No price data available for {symbol_obj.symbol}")
                    continue
                
                # Generate signal
                signal = strategy_instance.generate_signal(symbol_obj.symbol, df)
                
                if signal and signal.is_valid():
                    # Save signal to database
                    db_signal = Signal(
                        strategy_id=strategy_db.id,
                        symbol_id=symbol_obj.id,
                        action=signal.action,
                        price=signal.price,
                        stop_loss=signal.stop_loss,
                        target=signal.target,
                        confidence=signal.confidence,
                        reason=signal.reason,
                        is_executed=False
                    )
                    db.add(db_signal)
                    db.flush()
                    db.refresh(db_signal)
                    
                    signals_generated.append(db_signal)
                    
                    logger.info(
                        f"Signal generated: {signal.action.value} {symbol_obj.symbol} "
                        f"@ {signal.price:.2f} (confidence: {signal.confidence:.2f})"
                    )
                
            except Exception as e:
                logger.error(
                    f"Error executing strategy on {symbol_obj.symbol}: {e}",
                    exc_info=True
                )
                continue
        
        db.commit()
        
        logger.info(
            f"Strategy '{strategy_name}' executed on {len(symbol_objs)} symbols, "
            f"generated {len(signals_generated)} signals"
        )
        
        return signals_generated
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error executing strategy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute strategy: {str(e)}"
        )


@router.get("/available", response_model=List[Dict[str, Any]])
async def get_available_strategies(
    current_user = Depends(require_active_user)
):
    """
    Get list of available strategy plugins loaded in the system.
    
    Returns strategies registered in the strategy registry (loaded plugins),
    including runtime information not stored in database.
    
    **Example Response:**
    ```json
    [
        {
            "name": "RSI_MACD_Strategy",
            "description": "Combined RSI and MACD momentum strategy",
            "is_validated": true,
            "is_tradeable": true,
            "backtest_accuracy": 0.68,
            "backtest_sharpe": 1.85,
            "backtest_max_drawdown": 0.12,
            "required_history": 50,
            "parameters": {
                "rsi_period": 14,
                "macd_fast": 12,
                "macd_slow": 26
            }
        },
        {
            "name": "BollingerBands_Breakout",
            "description": "Bollinger Bands breakout strategy",
            "is_validated": true,
            "is_tradeable": true,
            "backtest_accuracy": 0.64,
            "backtest_sharpe": 1.52,
            "backtest_max_drawdown": 0.15,
            "required_history": 20,
            "parameters": {
                "period": 20,
                "std_dev": 2
            }
        }
    ]
    ```
    """
    try:
        strategies = registry.get_all()
        
        result = []
        for strategy in strategies:
            strategy_info = {
                "name": strategy.name,
                "description": strategy.description,
                "is_validated": strategy.is_validated,
                "is_tradeable": strategy.is_tradeable(),
                "backtest_accuracy": strategy.backtest_accuracy,
                "backtest_sharpe": strategy.backtest_sharpe,
                "backtest_max_drawdown": strategy.backtest_max_drawdown,
                "required_history": strategy.get_required_history(),
                "parameters": strategy.parameters
            }
            result.append(strategy_info)
        
        logger.info(f"Retrieved {len(result)} available strategies from registry")
        
        return result
        
    except Exception as e:
        logger.error(f"Error retrieving available strategies: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve available strategies: {str(e)}"
        )


@router.post("/", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    strategy: StrategyCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Register a new strategy in the database.
    
    This creates a database record for the strategy. The actual strategy logic
    must be implemented as a Python class and registered in the strategy registry.
    
    **Request Body:**
    ```json
    {
        "name": "My_Custom_Strategy",
        "description": "Custom momentum strategy with volume filter",
        "parameters": {
            "momentum_period": 20,
            "volume_threshold": 1.5
        }
    }
    ```
    """
    try:
        # Check if strategy already exists
        existing = db.query(Strategy).filter(Strategy.name == strategy.name).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Strategy with name '{strategy.name}' already exists"
            )
        
        # Create new strategy
        db_strategy = Strategy(
            name=strategy.name,
            description=strategy.description,
            parameters=strategy.parameters,
            is_active=False,  # Inactive until validated
            is_validated=False
        )
        
        db.add(db_strategy)
        db.commit()
        db.refresh(db_strategy)
        
        logger.info(f"Created new strategy: {strategy.name} (ID: {db_strategy.id})")
        
        return db_strategy
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating strategy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create strategy: {str(e)}"
        )


@router.patch("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    strategy_update: StrategyUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Update strategy information.
    
    **Path Parameters:**
    - strategy_id: Strategy ID to update
    
    **Request Body:**
    ```json
    {
        "description": "Updated description",
        "parameters": {"new_param": "value"},
        "is_active": true,
        "is_validated": true
    }
    ```
    """
    try:
        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with ID {strategy_id} not found"
            )
        
        # Update fields
        update_data = strategy_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(strategy, field, value)
        
        strategy.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(strategy)
        
        logger.info(f"Updated strategy: {strategy.name} (ID: {strategy_id})")
        
        return strategy
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update strategy: {str(e)}"
        )


@router.delete("/{strategy_id}", response_model=SuccessResponse)
async def delete_strategy(
    strategy_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Delete a strategy from the database.
    
    This only removes the database record. If the strategy is registered
    in the strategy registry, it must be unregistered separately.
    
    **Path Parameters:**
    - strategy_id: Strategy ID to delete
    """
    try:
        strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
        
        if not strategy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Strategy with ID {strategy_id} not found"
            )
        
        strategy_name = strategy.name
        
        db.delete(strategy)
        db.commit()
        
        logger.info(f"Deleted strategy: {strategy_name} (ID: {strategy_id})")
        
        return SuccessResponse(
            success=True,
            message=f"Strategy '{strategy_name}' deleted successfully",
            data={"strategy_id": strategy_id}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting strategy {strategy_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete strategy: {str(e)}"
        )
