# api/routes/symbols.py
"""
Symbol management endpoints for StockJarvis API.
Handles symbol retrieval, price data access, and symbol registration.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from api.dependencies import get_db, require_active_user
from api.schemas import (
    SymbolResponse,
    SymbolCreate,
    SymbolUpdate,
    PriceResponse,
    TimeframeEnum
)
from data.models import Symbol, Price, Timeframe
from data.repository import repository
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/symbols", tags=["symbols"])


@router.get("/", response_model=List[SymbolResponse])
async def list_symbols(
    active_only: bool = Query(True, description="Filter for active symbols only"),
    is_fno: Optional[bool] = Query(None, description="Filter for F&O symbols"),
    is_nifty50: Optional[bool] = Query(None, description="Filter for Nifty 50 symbols"),
    exchange: Optional[str] = Query(None, description="Filter by exchange (NSE/BSE)"),
    sector: Optional[str] = Query(None, description="Filter by sector"),
    search: Optional[str] = Query(None, description="Search by symbol or company name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get list of all stock symbols with optional filters.
    
    Returns symbols from the database with company information and categorization.
    
    **Query Parameters:**
    - active_only: Only return active symbols (default: true)
    - is_fno: Filter for F&O available symbols
    - is_nifty50: Filter for Nifty 50 constituents
    - exchange: Filter by exchange (NSE or BSE)
    - sector: Filter by sector
    - search: Search in symbol or company name
    - skip: Pagination offset
    - limit: Maximum results to return
    
    **Example Response:**
    ```json
    [
        {
            "id": 45,
            "symbol": "RELIANCE",
            "company_name": "Reliance Industries Ltd",
            "exchange": "NSE",
            "sector": "Energy",
            "industry": "Oil & Gas",
            "is_nifty50": true,
            "is_fno": true,
            "is_active": true,
            "created_at": "2025-01-10T10:00:00Z",
            "updated_at": "2025-12-15T14:30:00Z"
        }
    ]
    ```
    """
    try:
        query = db.query(Symbol)
        
        # Apply filters
        if active_only:
            query = query.filter(Symbol.is_active == True)
        
        if is_fno is not None:
            query = query.filter(Symbol.is_fno == is_fno)
        
        if is_nifty50 is not None:
            query = query.filter(Symbol.is_nifty50 == is_nifty50)
        
        if exchange:
            from data.models import Exchange
            try:
                exchange_enum = Exchange[exchange.upper()]
                query = query.filter(Symbol.exchange == exchange_enum)
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid exchange: {exchange}. Use NSE or BSE."
                )
        
        if sector:
            query = query.filter(Symbol.sector.ilike(f"%{sector}%"))
        
        if search:
            search_pattern = f"%{search.upper()}%"
            query = query.filter(
                (Symbol.symbol.ilike(search_pattern)) |
                (Symbol.company_name.ilike(search_pattern))
            )
        
        # Order by symbol
        query = query.order_by(Symbol.symbol)
        
        # Pagination
        symbols = query.offset(skip).limit(limit).all()
        
        logger.info(
            f"Retrieved {len(symbols)} symbols "
            f"(active_only={active_only}, is_fno={is_fno}, exchange={exchange})"
        )
        
        return symbols
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing symbols: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve symbols: {str(e)}"
        )


@router.get("/{symbol}", response_model=SymbolResponse)
async def get_symbol_details(
    symbol: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get detailed information about a specific symbol.
    
    **Path Parameters:**
    - symbol: Stock symbol (e.g., RELIANCE, TCS, INFY)
    
    **Example Response:**
    ```json
    {
        "id": 45,
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Ltd",
        "exchange": "NSE",
        "sector": "Energy",
        "industry": "Oil & Gas",
        "is_nifty50": true,
        "is_fno": true,
        "is_active": true,
        "created_at": "2025-01-10T10:00:00Z",
        "updated_at": "2025-12-15T14:30:00Z"
    }
    ```
    """
    try:
        symbol_obj = db.query(Symbol).filter(
            Symbol.symbol == symbol.upper()
        ).first()
        
        if not symbol_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{symbol}' not found"
            )
        
        logger.info(f"Retrieved symbol details: {symbol}")
        
        return symbol_obj
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving symbol {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve symbol: {str(e)}"
        )


@router.get("/{symbol}/prices", response_model=List[PriceResponse])
async def get_symbol_price_history(
    symbol: str,
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    timeframe: TimeframeEnum = Query(TimeframeEnum.DAILY, description="Price data timeframe"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get historical price data for a symbol.
    
    Returns OHLCV (Open, High, Low, Close, Volume) data for the specified symbol
    and time range.
    
    **Path Parameters:**
    - symbol: Stock symbol (e.g., RELIANCE, TCS)
    
    **Query Parameters:**
    - start_date: Start date in YYYY-MM-DD format (default: 90 days ago)
    - end_date: End date in YYYY-MM-DD format (default: today)
    - timeframe: Data granularity (daily, 1min, 5min, 15min, 1hour, weekly, monthly)
    - limit: Maximum number of records to return (default: 100, max: 1000)
    
    **Example Request:**
    ```
    GET /symbols/RELIANCE/prices?start_date=2025-11-01&end_date=2025-12-20&timeframe=daily
    ```
    
    **Example Response:**
    ```json
    [
        {
            "id": 12345,
            "symbol_id": 45,
            "timestamp": "2025-12-20T09:15:00Z",
            "open": 2445.50,
            "high": 2492.75,
            "low": 2438.25,
            "close": 2485.75,
            "volume": 5823450.0,
            "timeframe": "daily"
        },
        {
            "id": 12344,
            "symbol_id": 45,
            "timestamp": "2025-12-19T09:15:00Z",
            "open": 2430.00,
            "high": 2455.50,
            "low": 2425.75,
            "close": 2448.25,
            "volume": 4921340.0,
            "timeframe": "daily"
        }
    ]
    ```
    """
    try:
        # Validate symbol exists
        symbol_obj = db.query(Symbol).filter(
            Symbol.symbol == symbol.upper()
        ).first()
        
        if not symbol_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{symbol}' not found"
            )
        
        # Parse dates
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use YYYY-MM-DD"
                )
        else:
            # Default: 90 days ago
            start_dt = datetime.utcnow() - timedelta(days=90)
        
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
                # Add one day to include the entire end date
                end_dt = end_dt + timedelta(days=1)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use YYYY-MM-DD"
                )
        else:
            # Default: today
            end_dt = datetime.utcnow()
        
        # Validate date range
        if start_dt > end_dt:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before end_date"
            )
        
        # Convert timeframe enum to model enum
        timeframe_model = Timeframe[timeframe.value.upper().replace("MIN", "_MINUTE").replace("HOUR", "_HOUR")]
        
        # Query prices
        query = db.query(Price).filter(
            Price.symbol_id == symbol_obj.id,
            Price.timeframe == timeframe_model,
            Price.timestamp >= start_dt,
            Price.timestamp < end_dt
        ).order_by(Price.timestamp.desc())
        
        prices = query.limit(limit).all()
        
        if not prices:
            logger.warning(
                f"No price data found for {symbol} "
                f"(timeframe={timeframe}, start={start_date}, end={end_date})"
            )
        
        logger.info(
            f"Retrieved {len(prices)} price records for {symbol} "
            f"(timeframe={timeframe}, {start_dt.date()} to {end_dt.date()})"
        )
        
        return prices
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving prices for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve price data: {str(e)}"
        )


@router.post("/", response_model=SymbolResponse, status_code=status.HTTP_201_CREATED)
async def add_symbol(
    symbol_data: SymbolCreate,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Add a new symbol to the database.
    
    Registers a new stock symbol with company information and categorization.
    
    **Request Body:**
    ```json
    {
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Ltd",
        "exchange": "NSE",
        "sector": "Energy",
        "industry": "Oil & Gas",
        "is_nifty50": true,
        "is_fno": true,
        "is_active": true
    }
    ```
    
    **Example Response:**
    ```json
    {
        "id": 45,
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Ltd",
        "exchange": "NSE",
        "sector": "Energy",
        "industry": "Oil & Gas",
        "is_nifty50": true,
        "is_fno": true,
        "is_active": true,
        "created_at": "2025-12-20T11:30:00Z",
        "updated_at": "2025-12-20T11:30:00Z"
    }
    ```
    """
    try:
        # Check if symbol already exists
        existing = db.query(Symbol).filter(
            Symbol.symbol == symbol_data.symbol.upper()
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Symbol '{symbol_data.symbol}' already exists"
            )
        
        # Convert exchange string to enum
        from data.models import Exchange
        try:
            exchange_enum = Exchange[symbol_data.exchange.upper()]
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid exchange: {symbol_data.exchange}. Use NSE or BSE."
            )
        
        # Create new symbol
        new_symbol = Symbol(
            symbol=symbol_data.symbol.upper(),
            company_name=symbol_data.company_name,
            exchange=exchange_enum,
            sector=symbol_data.sector,
            industry=symbol_data.industry,
            is_nifty50=symbol_data.is_nifty50,
            is_fno=symbol_data.is_fno,
            is_active=symbol_data.is_active
        )
        
        db.add(new_symbol)
        db.commit()
        db.refresh(new_symbol)
        
        logger.info(
            f"Added new symbol: {new_symbol.symbol} - {new_symbol.company_name} "
            f"(ID: {new_symbol.id})"
        )
        
        return new_symbol
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error adding symbol: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add symbol: {str(e)}"
        )


@router.patch("/{symbol}", response_model=SymbolResponse)
async def update_symbol(
    symbol: str,
    symbol_update: SymbolUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Update symbol information.
    
    **Path Parameters:**
    - symbol: Stock symbol to update
    
    **Request Body:**
    ```json
    {
        "company_name": "Updated Company Name",
        "sector": "Technology",
        "is_active": false
    }
    ```
    """
    try:
        symbol_obj = db.query(Symbol).filter(
            Symbol.symbol == symbol.upper()
        ).first()
        
        if not symbol_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{symbol}' not found"
            )
        
        # Update fields
        update_data = symbol_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(symbol_obj, field, value)
        
        symbol_obj.updated_at = datetime.utcnow()
        
        db.commit()
        db.refresh(symbol_obj)
        
        logger.info(f"Updated symbol: {symbol}")
        
        return symbol_obj
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating symbol {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update symbol: {str(e)}"
        )


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_symbol(
    symbol: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Delete a symbol from the database.
    
    **Warning:** This will cascade delete all related data (prices, signals, positions).
    Consider marking the symbol as inactive instead.
    
    **Path Parameters:**
    - symbol: Stock symbol to delete
    
    **Returns:** 204 No Content on success
    """
    try:
        symbol_obj = db.query(Symbol).filter(
            Symbol.symbol == symbol.upper()
        ).first()
        
        if not symbol_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{symbol}' not found"
            )
        
        # Check for open positions
        from data.models import Position
        open_positions = db.query(Position).filter(
            Position.symbol_id == symbol_obj.id,
            Position.is_open == True
        ).count()
        
        if open_positions > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete symbol with {open_positions} open positions. "
                       f"Close all positions first or mark symbol as inactive."
            )
        
        db.delete(symbol_obj)
        db.commit()
        
        logger.info(f"Deleted symbol: {symbol}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting symbol {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete symbol: {str(e)}"
        )


@router.get("/{symbol}/latest-price", response_model=PriceResponse)
async def get_latest_price(
    symbol: str,
    timeframe: TimeframeEnum = Query(TimeframeEnum.DAILY, description="Price data timeframe"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get the latest/most recent price data for a symbol.
    
    Returns the most recent OHLCV data point for the specified symbol and timeframe.
    
    **Path Parameters:**
    - symbol: Stock symbol
    
    **Query Parameters:**
    - timeframe: Data timeframe (default: daily)
    
    **Example Response:**
    ```json
    {
        "id": 12345,
        "symbol_id": 45,
        "timestamp": "2025-12-20T09:15:00Z",
        "open": 2445.50,
        "high": 2492.75,
        "low": 2438.25,
        "close": 2485.75,
        "volume": 5823450.0,
        "timeframe": "daily"
    }
    ```
    """
    try:
        # Validate symbol
        symbol_obj = db.query(Symbol).filter(
            Symbol.symbol == symbol.upper()
        ).first()
        
        if not symbol_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol '{symbol}' not found"
            )
        
        # Convert timeframe
        timeframe_model = Timeframe[timeframe.value.upper().replace("MIN", "_MINUTE").replace("HOUR", "_HOUR")]
        
        # Get latest price
        latest_price = db.query(Price).filter(
            Price.symbol_id == symbol_obj.id,
            Price.timeframe == timeframe_model
        ).order_by(Price.timestamp.desc()).first()
        
        if not latest_price:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No price data found for {symbol} (timeframe={timeframe})"
            )
        
        logger.info(
            f"Retrieved latest price for {symbol}: ${latest_price.close:.2f} "
            f"@ {latest_price.timestamp}"
        )
        
        return latest_price
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving latest price for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve latest price: {str(e)}"
        )
