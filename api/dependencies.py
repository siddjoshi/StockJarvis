# api/dependencies.py
"""
Shared dependencies for FastAPI routes.
Provides reusable dependency injection for database sessions, authentication, and query parameters.
"""

from typing import Optional, Generator, List
from fastapi import Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from data.repository import repository
from api.auth import get_current_user, get_current_active_user, get_current_superuser, User
from core.logger import get_logger

logger = get_logger(__name__)


# ==================== Database Dependencies ====================

def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get database session.
    Automatically handles session lifecycle with commit/rollback.
    
    Yields:
        Database session
    
    Example:
        @app.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    with repository.get_session() as session:
        try:
            yield session
        except Exception as e:
            logger.error(f"Database session error: {e}")
            raise


# ==================== Authentication Dependencies ====================

# Re-export auth dependencies for convenience
CurrentUser = Depends(get_current_user)
CurrentActiveUser = Depends(get_current_active_user)
CurrentSuperUser = Depends(get_current_superuser)


def require_active_user(current_user: User = Depends(get_current_active_user)) -> User:
    """
    Dependency that requires an active authenticated user.
    
    Args:
        current_user: Current user from authentication
    
    Returns:
        Active user object
    
    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    return current_user


def require_superuser(current_user: User = Depends(get_current_superuser)) -> User:
    """
    Dependency that requires a superuser.
    
    Args:
        current_user: Current user from authentication
    
    Returns:
        Superuser object
    
    Raises:
        HTTPException: If user is not a superuser
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required"
        )
    return current_user


# ==================== Pagination Dependencies ====================

class PaginationParams:
    """
    Common pagination parameters for list endpoints.
    """
    
    def __init__(
        self,
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return")
    ):
        self.skip = skip
        self.limit = limit


def get_pagination_params(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return")
) -> dict:
    """
    Dependency for pagination parameters.
    
    Args:
        skip: Number of records to skip (offset)
        limit: Maximum number of records to return
    
    Returns:
        Dictionary with skip and limit
    """
    return {"skip": skip, "limit": limit}


# ==================== Query Parameter Dependencies ====================

def get_symbol_filter(
    symbols: Optional[str] = Query(None, description="Comma-separated list of symbols to filter")
) -> Optional[List[str]]:
    """
    Dependency to parse and validate symbol filter.
    
    Args:
        symbols: Comma-separated symbol list
    
    Returns:
        List of uppercase symbols or None
    """
    if not symbols:
        return None
    
    return [s.strip().upper() for s in symbols.split(",") if s.strip()]


def get_date_range(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)")
) -> dict:
    """
    Dependency for date range parameters.
    
    Args:
        start_date: Start date string
        end_date: End date string
    
    Returns:
        Dictionary with start_date and end_date
    
    Raises:
        HTTPException: If date format is invalid
    """
    from datetime import datetime
    
    result = {"start_date": None, "end_date": None}
    
    if start_date:
        try:
            result["start_date"] = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            result["end_date"] = datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use YYYY-MM-DD"
            )
    
    # Validate date range
    if result["start_date"] and result["end_date"]:
        if result["start_date"] > result["end_date"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date must be before end_date"
            )
    
    return result


def get_active_only_filter(
    active_only: bool = Query(True, description="Filter for active records only")
) -> bool:
    """
    Dependency for active/inactive filtering.
    
    Args:
        active_only: Whether to filter for active records
    
    Returns:
        Boolean filter value
    """
    return active_only


# ==================== Sorting and Ordering Dependencies ====================

def get_sort_params(
    sort_by: Optional[str] = Query(None, description="Field to sort by"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order: asc or desc")
) -> dict:
    """
    Dependency for sorting parameters.
    
    Args:
        sort_by: Field name to sort by
        order: Sort order (asc or desc)
    
    Returns:
        Dictionary with sort_by and order
    """
    return {
        "sort_by": sort_by,
        "order": order.lower()
    }


# ==================== Trading Mode Dependencies ====================

def get_trading_mode(
    mode: Optional[str] = Query(None, regex="^(paper|live)$", description="Trading mode: paper or live")
) -> Optional[str]:
    """
    Dependency for trading mode filter.
    
    Args:
        mode: Trading mode (paper or live)
    
    Returns:
        Trading mode string or None
    """
    return mode


# ==================== Validation Dependencies ====================

def validate_symbol(symbol: str) -> str:
    """
    Dependency to validate and normalize stock symbol.
    
    Args:
        symbol: Stock symbol
    
    Returns:
        Uppercase normalized symbol
    
    Raises:
        HTTPException: If symbol format is invalid
    """
    symbol = symbol.strip().upper()
    
    if not symbol:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Symbol cannot be empty"
        )
    
    if len(symbol) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Symbol too long (max 20 characters)"
        )
    
    # Basic validation - alphanumeric and some special characters
    if not all(c.isalnum() or c in ['-', '_', '&', '.'] for c in symbol):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Symbol contains invalid characters"
        )
    
    return symbol


def validate_strategy_name(strategy: str) -> str:
    """
    Dependency to validate strategy name.
    
    Args:
        strategy: Strategy name
    
    Returns:
        Validated strategy name
    
    Raises:
        HTTPException: If strategy name is invalid
    """
    strategy = strategy.strip()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strategy name cannot be empty"
        )
    
    if len(strategy) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strategy name too long (max 100 characters)"
        )
    
    return strategy


# ==================== Resource Existence Dependencies ====================

def verify_symbol_exists(symbol: str, db: Session = Depends(get_db)):
    """
    Dependency to verify that a symbol exists in the database.
    
    Args:
        symbol: Stock symbol
        db: Database session
    
    Returns:
        Symbol object
    
    Raises:
        HTTPException: If symbol not found
    """
    from data.models import Symbol
    
    symbol_obj = db.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
    
    if not symbol_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found"
        )
    
    return symbol_obj


def verify_strategy_exists(strategy_id: int, db: Session = Depends(get_db)):
    """
    Dependency to verify that a strategy exists.
    
    Args:
        strategy_id: Strategy ID
        db: Database session
    
    Returns:
        Strategy object
    
    Raises:
        HTTPException: If strategy not found
    """
    from data.models import Strategy
    
    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    
    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Strategy with ID {strategy_id} not found"
        )
    
    return strategy


# ==================== Helper Functions ====================

def check_trading_permissions(user: User, trading_mode: str = "paper"):
    """
    Check if user has permissions for the requested trading mode.
    
    Args:
        user: Current user
        trading_mode: Requested trading mode (paper or live)
    
    Raises:
        HTTPException: If user doesn't have required permissions
    """
    if trading_mode == "live" and not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Live trading requires superuser privileges"
        )


def rate_limit_check(user: User):
    """
    Basic rate limiting check (placeholder for future implementation).
    
    Args:
        user: Current user
    
    Note:
        This is a placeholder. Implement proper rate limiting using Redis or similar.
    """
    # TODO: Implement rate limiting logic
    # - Track requests per user
    # - Different limits for different user types
    # - Use Redis for distributed rate limiting
    pass
