# api/routes/data.py
"""
Data API endpoints for StockJarvis.
Provides access to data provider operations, symbol management, and data collection status.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from api.dependencies import get_db, require_active_user
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ==================== Pydantic Schemas ====================

class SymbolInfoResponse(BaseModel):
    """Symbol information from data provider."""
    symbol: str
    company_name: str
    exchange: str
    isin: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_fno: bool = False
    is_index: bool = False
    lot_size: Optional[int] = None
    
    class Config:
        from_attributes = True


class QuoteResponse(BaseModel):
    """Real-time quote response."""
    symbol: str
    last_price: float
    change: float
    change_percent: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    timestamp: Optional[str] = None


class BackfillRequest(BaseModel):
    """Request for historical data backfill."""
    symbols: Optional[List[str]] = Field(
        default=None,
        description="Symbols to backfill (uses F&O symbols if not specified)"
    )
    start_date: Optional[str] = Field(
        default=None,
        description="Start date (YYYY-MM-DD format)"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date (YYYY-MM-DD format)"
    )


class DataStatusResponse(BaseModel):
    """Data collection status response."""
    provider: str
    fallback_provider: str
    cache_enabled: bool
    cache_ttl: int
    stats: Dict[str, Any]


class ProviderStatsResponse(BaseModel):
    """Provider statistics response."""
    primary_requests: int
    fallback_requests: int
    cache_hits: int
    cache_misses: int
    errors: int
    total_requests: int
    fallback_rate: float
    cache_hit_rate: float


class ValidationResult(BaseModel):
    """Cross-validation result."""
    valid: bool
    total_dates: Optional[int] = None
    discrepancy_count: Optional[int] = None
    discrepancies: Optional[List[Dict[str, Any]]] = None
    tolerance_pct: Optional[float] = None
    message: Optional[str] = None


# ==================== Helper Functions ====================

def _get_data_manager():
    """Get data manager instance."""
    from DataCollector.data_manager import get_data_manager
    return get_data_manager()


# ==================== API Endpoints ====================

@router.get("/symbols", response_model=List[SymbolInfoResponse])
async def list_data_provider_symbols(
    index: Optional[str] = Query(None, description="Filter by index (NIFTY50, NIFTY500)"),
    fno_only: bool = Query(False, description="Return only F&O symbols"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get list of symbols from the data provider.
    
    Fetches symbols directly from the configured data provider (Yahoo, NSE, etc.)
    rather than from the local database.
    
    **Query Parameters:**
    - index: Filter by index membership
    - fno_only: Return only F&O enabled symbols
    
    **Example Response:**
    ```json
    [
        {
            "symbol": "RELIANCE",
            "company_name": "Reliance Industries Ltd",
            "exchange": "NSE",
            "is_fno": true,
            "sector": "Energy"
        }
    ]
    ```
    """
    try:
        data_manager = _get_data_manager()
        symbols = data_manager.get_symbols(index=index, fno_only=fno_only)
        
        return [
            SymbolInfoResponse(
                symbol=s.symbol,
                company_name=s.company_name,
                exchange=s.exchange,
                isin=s.isin,
                sector=s.sector,
                industry=s.industry,
                is_fno=s.is_fno,
                is_index=s.is_index,
                lot_size=s.lot_size,
            )
            for s in symbols
        ]
        
    except Exception as e:
        logger.error(f"Error fetching symbols from provider: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch symbols: {str(e)}"
        )


@router.get("/symbols/{symbol}", response_model=SymbolInfoResponse)
async def get_symbol_from_provider(
    symbol: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get symbol metadata from data provider.
    
    **Path Parameters:**
    - symbol: Stock symbol
    
    **Example Response:**
    ```json
    {
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Ltd",
        "exchange": "NSE",
        "is_fno": true,
        "sector": "Energy"
    }
    ```
    """
    try:
        data_manager = _get_data_manager()
        symbols = data_manager.get_symbols()
        
        # Find the symbol
        for s in symbols:
            if s.symbol.upper() == symbol.upper():
                return SymbolInfoResponse(
                    symbol=s.symbol,
                    company_name=s.company_name,
                    exchange=s.exchange,
                    isin=s.isin,
                    sector=s.sector,
                    industry=s.industry,
                    is_fno=s.is_fno,
                    is_index=s.is_index,
                    lot_size=s.lot_size,
                )
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found in provider"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching symbol {symbol}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch symbol: {str(e)}"
        )


@router.get("/quote/{symbol}", response_model=QuoteResponse)
async def get_quote(
    symbol: str,
    use_cache: bool = Query(True, description="Use cached quote if available"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get real-time quote for a symbol.
    
    **Path Parameters:**
    - symbol: Stock symbol
    
    **Query Parameters:**
    - use_cache: Use cached quote if within TTL
    
    **Example Response:**
    ```json
    {
        "symbol": "RELIANCE",
        "last_price": 2485.50,
        "change": 35.25,
        "change_percent": 1.44,
        "open": 2450.00,
        "high": 2492.75,
        "low": 2445.00,
        "volume": 5823450
    }
    ```
    """
    try:
        data_manager = _get_data_manager()
        quote = data_manager.get_quote(symbol, use_cache=use_cache)
        
        return QuoteResponse(
            symbol=quote.symbol,
            last_price=quote.last_price,
            change=quote.change,
            change_percent=quote.change_percent,
            open=quote.open,
            high=quote.high,
            low=quote.low,
            close=quote.close,
            volume=quote.volume,
            bid=quote.bid,
            ask=quote.ask,
            timestamp=quote.timestamp.isoformat() if quote.timestamp else None,
        )
        
    except Exception as e:
        logger.error(f"Error fetching quote for {symbol}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch quote: {str(e)}"
        )


@router.post("/quotes", response_model=Dict[str, QuoteResponse])
async def get_quotes_batch(
    symbols: List[str],
    use_cache: bool = Query(True, description="Use cached quotes"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get quotes for multiple symbols in batch.
    
    **Request Body:**
    ```json
    ["RELIANCE", "TCS", "INFY"]
    ```
    
    **Query Parameters:**
    - use_cache: Use cached quotes if within TTL
    
    **Example Response:**
    ```json
    {
        "RELIANCE": {
            "symbol": "RELIANCE",
            "last_price": 2485.50,
            "change": 35.25,
            "change_percent": 1.44
        },
        "TCS": {
            "symbol": "TCS",
            "last_price": 3650.00,
            "change": -25.50,
            "change_percent": -0.69
        }
    }
    ```
    """
    try:
        data_manager = _get_data_manager()
        quotes = data_manager.get_quotes(symbols, use_cache=use_cache)
        
        return {
            symbol: QuoteResponse(
                symbol=quote.symbol,
                last_price=quote.last_price,
                change=quote.change,
                change_percent=quote.change_percent,
                open=quote.open,
                high=quote.high,
                low=quote.low,
                close=quote.close,
                volume=quote.volume,
                bid=quote.bid,
                ask=quote.ask,
                timestamp=quote.timestamp.isoformat() if quote.timestamp else None,
            )
            for symbol, quote in quotes.items()
        }
        
    except Exception as e:
        logger.error(f"Error fetching batch quotes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch quotes: {str(e)}"
        )


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
async def trigger_backfill(
    request: BackfillRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Trigger historical data backfill task.
    
    Starts a background task to download historical data for specified symbols.
    
    **Request Body:**
    ```json
    {
        "symbols": ["RELIANCE", "TCS"],
        "start_date": "2024-01-01",
        "end_date": "2024-12-20"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "status": "accepted",
        "message": "Backfill task started",
        "task_id": "abc123"
    }
    ```
    """
    try:
        from workers.tasks.data_collection import backfill_historical_data
        
        # Start the celery task
        task = backfill_historical_data.delay(
            symbols=request.symbols,
            start_date=request.start_date,
            end_date=request.end_date
        )
        
        logger.info(f"Started backfill task: {task.id}")
        
        return {
            "status": "accepted",
            "message": "Backfill task started",
            "task_id": task.id,
            "symbols_count": len(request.symbols) if request.symbols else "all F&O",
            "date_range": f"{request.start_date or 'default'} to {request.end_date or 'today'}"
        }
        
    except Exception as e:
        logger.error(f"Error starting backfill task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start backfill: {str(e)}"
        )


@router.get("/status", response_model=DataStatusResponse)
async def get_data_collection_status(
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Get data collection status and provider statistics.
    
    **Example Response:**
    ```json
    {
        "provider": "yahoo",
        "fallback_provider": "nse",
        "cache_enabled": true,
        "cache_ttl": 60,
        "stats": {
            "primary_requests": 100,
            "fallback_requests": 5,
            "cache_hits": 80,
            "cache_misses": 25,
            "errors": 2
        }
    }
    ```
    """
    try:
        data_manager = _get_data_manager()
        stats = data_manager.get_stats()
        
        return DataStatusResponse(
            provider=stats["primary_provider"],
            fallback_provider=stats["fallback_provider"],
            cache_enabled=stats["cache_enabled"],
            cache_ttl=stats["cache_ttl"],
            stats={
                "primary_requests": stats["primary_requests"],
                "fallback_requests": stats["fallback_requests"],
                "cache_hits": stats["cache_hits"],
                "cache_misses": stats["cache_misses"],
                "errors": stats["errors"],
                "total_requests": stats["total_requests"],
                "fallback_rate": round(stats["fallback_rate"], 2),
                "cache_hit_rate": round(stats["cache_hit_rate"], 2),
            }
        )
        
    except Exception as e:
        logger.error(f"Error fetching data status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch status: {str(e)}"
        )


@router.post("/validate/{symbol}", response_model=ValidationResult)
async def validate_symbol_data(
    symbol: str,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    tolerance: float = Query(0.02, description="Price difference tolerance (0.02 = 2%)"),
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Cross-validate symbol data between providers.
    
    Compares data from primary and fallback providers to detect discrepancies.
    
    **Path Parameters:**
    - symbol: Stock symbol
    
    **Query Parameters:**
    - start_date: Start date (YYYY-MM-DD)
    - end_date: End date (YYYY-MM-DD)
    - tolerance: Maximum price difference (as percentage)
    
    **Example Response:**
    ```json
    {
        "valid": true,
        "total_dates": 22,
        "discrepancy_count": 0,
        "discrepancies": [],
        "tolerance_pct": 2.0
    }
    ```
    """
    try:
        data_manager = _get_data_manager()
        result = data_manager.cross_validate_data(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            tolerance=tolerance
        )
        
        return ValidationResult(**result)
        
    except Exception as e:
        logger.error(f"Error validating {symbol}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate data: {str(e)}"
        )


@router.post("/cache/clear")
async def clear_data_cache(
    db: Session = Depends(get_db),
    current_user = Depends(require_active_user)
):
    """
    Clear the data manager cache.
    
    Clears all cached quotes and symbol lists.
    
    **Example Response:**
    ```json
    {
        "status": "success",
        "message": "Cache cleared successfully"
    }
    ```
    """
    try:
        data_manager = _get_data_manager()
        data_manager.clear_cache()
        
        return {
            "status": "success",
            "message": "Cache cleared successfully"
        }
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.get("/providers")
async def list_providers(
    current_user = Depends(require_active_user)
):
    """
    List available data providers.
    
    **Example Response:**
    ```json
    {
        "providers": [
            {
                "name": "yahoo",
                "description": "Yahoo Finance - Free historical and real-time data",
                "features": ["historical", "quotes", "symbols"]
            },
            {
                "name": "nse",
                "description": "NSE India - Official NSE data",
                "features": ["historical", "quotes", "symbols", "indices"]
            }
        ]
    }
    ```
    """
    return {
        "providers": [
            {
                "name": "yahoo",
                "description": "Yahoo Finance - Free historical and real-time data",
                "features": ["historical", "quotes", "symbols"],
                "supported_exchanges": ["NSE", "BSE"],
                "rate_limit": "Low",
            },
            {
                "name": "nse",
                "description": "NSE India - Official NSE data",
                "features": ["historical", "quotes", "symbols", "indices", "market_status"],
                "supported_exchanges": ["NSE"],
                "rate_limit": "Medium",
            },
            {
                "name": "bse",
                "description": "BSE India - Official BSE data",
                "features": ["historical", "quotes", "indices"],
                "supported_exchanges": ["BSE"],
                "rate_limit": "Medium",
            },
            {
                "name": "zerodha",
                "description": "Zerodha Kite Connect - Premium data via API",
                "features": ["historical", "quotes", "symbols", "positions", "holdings"],
                "supported_exchanges": ["NSE", "BSE", "NFO", "MCX"],
                "rate_limit": "Low",
                "requires_subscription": True,
            },
        ]
    }
