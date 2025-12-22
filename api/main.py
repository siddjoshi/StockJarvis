# api/main.py
"""
Main FastAPI application for StockJarvis.
Handles app initialization, CORS, middleware, and route registration.
"""

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from typing import Dict, Any
import time

from config.settings import settings
from core.logger import get_logger
from data.repository import repository
from api.routes import (
    auth_router,
    symbols_router,
    strategies_router,
    signals_router,
    positions_router,
    orders_router,
    backtest_router,
    risk_router,
    data_router
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting StockJarvis API...")
    logger.info(f"Environment: {settings.app.env}")
    logger.info(f"Trading Mode: {settings.trading.mode}")
    
    # Initialize database
    try:
        repository.create_tables()
        logger.info("Database tables initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    
    # Additional startup tasks can go here
    # - Start background tasks
    # - Initialize connections to external services
    # - Load models/caches
    
    logger.info("StockJarvis API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down StockJarvis API...")
    # Cleanup tasks
    # - Close database connections
    # - Stop background tasks
    # - Clean up resources
    logger.info("StockJarvis API shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="StockJarvis API",
    description="Automated Stock Trading and Analysis Platform",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)


# ==================== Middleware Configuration ====================

# CORS middleware - allows frontend to call API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React dev server
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8080",  # Alternative frontend
        f"http://localhost:{settings.app.api_port}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# GZip compression for responses
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """
    Add response time tracking and request ID.
    """
    start_time = time.time()
    request_id = f"{int(start_time * 1000)}"
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request_id
    
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log all incoming requests and responses.
    """
    logger.info(f"Request: {request.method} {request.url.path}")
    
    try:
        response = await call_next(request)
        logger.info(f"Response: {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"Request failed: {str(e)}")
        raise


# ==================== Exception Handlers ====================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle validation errors with detailed messages.
    """
    logger.warning(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": exc.body,
            "message": "Request validation failed"
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """
    Handle ValueError exceptions.
    """
    logger.error(f"ValueError: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "message": "Invalid value provided"},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Catch-all exception handler for unhandled errors.
    """
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "message": str(exc) if settings.app.debug else "An unexpected error occurred"
        },
    )


# ==================== Routes ====================

@app.get("/", tags=["Root"])
async def root() -> Dict[str, str]:
    """
    Root endpoint - API information.
    """
    return {
        "name": "StockJarvis API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/api/docs",
        "health": "/health"
    }


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for monitoring.
    Returns application health status and system info.
    """
    try:
        # Check database connectivity
        with repository.get_session() as session:
            session.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "timestamp": time.time(),
        "environment": settings.app.env,
        "trading_mode": settings.trading.mode,
        "components": {
            "database": db_status,
            "api": "healthy"
        }
    }


@app.get("/metrics", tags=["Monitoring"])
async def metrics() -> Dict[str, Any]:
    """
    Basic metrics endpoint for monitoring.
    Returns current system metrics and trading statistics.
    """
    try:
        with repository.get_session() as session:
            from data.models import Position, Signal, Order
            
            open_positions = session.query(Position).filter(
                Position.is_open == True
            ).count()
            
            total_signals_today = session.query(Signal).filter(
                Signal.created_at >= time.strftime('%Y-%m-%d 00:00:00')
            ).count()
            
            pending_orders = session.query(Order).filter(
                Order.status.in_(['PENDING', 'PLACED'])
            ).count()
        
        return {
            "timestamp": time.time(),
            "trading": {
                "mode": settings.trading.mode,
                "open_positions": open_positions,
                "signals_today": total_signals_today,
                "pending_orders": pending_orders,
                "max_positions": settings.trading.max_positions
            }
        }
    except Exception as e:
        logger.error(f"Failed to fetch metrics: {e}")
        return {
            "error": "Failed to fetch metrics",
            "timestamp": time.time()
        }


# ==================== Register API Routes ====================

app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(symbols_router, prefix="/api/symbols", tags=["Symbols"])
app.include_router(strategies_router, prefix="/api/strategies", tags=["Strategies"])
app.include_router(signals_router, prefix="/api/signals", tags=["Signals"])
app.include_router(positions_router, prefix="/api/positions", tags=["Positions"])
app.include_router(orders_router, prefix="/api/orders", tags=["Orders"])
app.include_router(backtest_router, prefix="/api/backtests", tags=["Backtesting"])
app.include_router(risk_router, prefix="/api/risk", tags=["Risk Management"])
app.include_router(data_router, prefix="/api/data", tags=["Data Providers"])


# ==================== Development Entry Point ====================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host=settings.app.api_host,
        port=settings.app.api_port,
        reload=settings.app.debug,
        workers=1 if settings.app.debug else settings.app.api_workers,
        log_level=settings.app.log_level.lower()
    )
