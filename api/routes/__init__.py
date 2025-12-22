# api/routes/__init__.py
"""
API route modules for StockJarvis.
Exports all route routers for registration in main.py.

This file imports the actual router implementations from the individual
route modules and re-exports them for use in main.py.
"""

from core.logger import get_logger

logger = get_logger(__name__)

# Import routers from individual route modules
from api.routes.strategies import router as strategies_router
from api.routes.positions import router as positions_router
from api.routes.signals import router as signals_router
from api.routes.symbols import router as symbols_router
from api.routes.backtests import router as backtest_router
from api.routes.risk import router as risk_router
from api.routes.data import router as data_router
from api.routes.broker import router as broker_router

# Auth router is defined inline since it requires special OAuth2 handling
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta

from api.dependencies import get_db
from api.auth import (
    authenticate_user,
    create_access_token,
    Token,
    UserCreate,
    UserResponse,
    create_user,
    update_last_login,
    get_current_active_user,
    User,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

auth_router = APIRouter()


@auth_router.post("/token", response_model=Token, summary="Login and get access token")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    OAuth2 compatible token login endpoint.
    
    Get an access token for future authenticated requests.
    
    **Form Data:**
    - username: Username
    - password: Password
    
    **Example Response:**
    ```json
    {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "token_type": "bearer",
        "expires_in": 86400
    }
    ```
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    
    if not user:
        logger.warning(f"Failed login attempt for user: {form_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )
    
    # Update last login timestamp
    update_last_login(db, user.id)
    
    logger.info(f"User logged in: {user.username}")
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@auth_router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="Register new user")
async def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """
    Register a new user account.
    
    **Request Body:**
    ```json
    {
        "username": "newuser",
        "email": "user@example.com",
        "password": "securepassword123",
        "full_name": "John Doe"
    }
    ```
    
    **Example Response:**
    ```json
    {
        "id": 1,
        "username": "newuser",
        "email": "user@example.com",
        "full_name": "John Doe",
        "is_active": true,
        "is_superuser": false,
        "created_at": "2025-12-20T12:00:00Z",
        "last_login": null
    }
    ```
    """
    try:
        user = create_user(db, user_data)
        logger.info(f"New user registered: {user.username}")
        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@auth_router.get("/me", response_model=UserResponse, summary="Get current user")
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get the current authenticated user's information.
    
    **Example Response:**
    ```json
    {
        "id": 1,
        "username": "admin",
        "email": "admin@stockjarvis.local",
        "full_name": "Administrator",
        "is_active": true,
        "is_superuser": true,
        "created_at": "2025-12-20T10:00:00Z",
        "last_login": "2025-12-20T12:00:00Z"
    }
    ```
    """
    return current_user


# Orders router - placeholder for now, can be expanded
orders_router = APIRouter()


@orders_router.get("/", summary="Get orders")
async def get_orders(
    current_user: User = Depends(get_current_active_user)
):
    """Get order history."""
    return {"detail": "Orders endpoint - implement full functionality in routes/orders.py"}


# ==================== Export Routers ====================

__all__ = [
    "auth_router",
    "symbols_router",
    "strategies_router",
    "signals_router",
    "positions_router",
    "orders_router",
    "backtest_router",
    "risk_router",
    "data_router",
    "broker_router",
]
