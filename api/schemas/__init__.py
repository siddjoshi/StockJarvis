# api/schemas/__init__.py
"""
Pydantic schemas for API request/response validation.
Centralizes all data validation schemas for the StockJarvis API.
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator, ConfigDict
from enum import Enum


# ==================== Enums ====================

class OrderActionEnum(str, Enum):
    """Order action types."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatusEnum(str, Enum):
    """Order status types."""
    PENDING = "PENDING"
    PLACED = "PLACED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class TradingModeEnum(str, Enum):
    """Trading mode types."""
    PAPER = "paper"
    LIVE = "live"


class TimeframeEnum(str, Enum):
    """Price data timeframe."""
    MINUTE_1 = "1min"
    MINUTE_5 = "5min"
    MINUTE_15 = "15min"
    HOUR_1 = "1hour"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# ==================== Base Schemas ====================

class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(from_attributes=True)


# ==================== Symbol Schemas ====================

class SymbolBase(BaseSchema):
    """Base symbol schema."""
    symbol: str = Field(..., min_length=1, max_length=20)
    company_name: str = Field(..., min_length=1, max_length=255)
    exchange: Optional[str] = Field(default="NSE")
    sector: Optional[str] = Field(default=None, max_length=100)
    industry: Optional[str] = Field(default=None, max_length=100)
    is_nifty50: bool = Field(default=False)
    is_fno: bool = Field(default=False)
    is_active: bool = Field(default=True)


class SymbolCreate(SymbolBase):
    """Schema for creating a new symbol."""
    pass


class SymbolUpdate(BaseSchema):
    """Schema for updating symbol information."""
    company_name: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    is_nifty50: Optional[bool] = None
    is_fno: Optional[bool] = None
    is_active: Optional[bool] = None


class SymbolResponse(SymbolBase):
    """Symbol response schema."""
    id: int
    created_at: datetime
    updated_at: datetime


# ==================== Price Schemas ====================

class PriceBase(BaseSchema):
    """Base price schema."""
    timestamp: datetime
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: float = Field(..., ge=0)
    timeframe: TimeframeEnum = Field(default=TimeframeEnum.DAILY)


class PriceCreate(PriceBase):
    """Schema for creating price data."""
    symbol: str


class PriceResponse(PriceBase):
    """Price response schema."""
    id: int
    symbol_id: int


class PriceBulkCreate(BaseSchema):
    """Schema for bulk price data upload."""
    symbol: str
    timeframe: TimeframeEnum
    prices: List[PriceBase]


# ==================== Strategy Schemas ====================

class StrategyBase(BaseSchema):
    """Base strategy schema."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class StrategyCreate(StrategyBase):
    """Schema for creating a new strategy."""
    pass


class StrategyUpdate(BaseSchema):
    """Schema for updating strategy."""
    description: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_validated: Optional[bool] = None


class StrategyResponse(StrategyBase):
    """Strategy response schema."""
    id: int
    backtest_accuracy: Optional[float] = None
    backtest_sharpe: Optional[float] = None
    backtest_max_drawdown: Optional[float] = None
    is_active: bool
    is_validated: bool
    created_at: datetime
    updated_at: datetime


# ==================== Signal Schemas ====================

class SignalBase(BaseSchema):
    """Base signal schema."""
    action: OrderActionEnum
    price: float = Field(..., gt=0)
    stop_loss: float = Field(..., gt=0)
    target: float = Field(..., gt=0)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    reason: Optional[str] = None


class SignalCreate(SignalBase):
    """Schema for creating a signal."""
    strategy_name: str
    symbol: str


class SignalResponse(SignalBase):
    """Signal response schema."""
    id: int
    strategy_id: int
    symbol_id: int
    is_executed: bool
    executed_at: Optional[datetime] = None
    created_at: datetime


class SignalWithDetails(SignalResponse):
    """Signal with related details."""
    symbol: str
    strategy_name: str


# ==================== Order Schemas ====================

class OrderBase(BaseSchema):
    """Base order schema."""
    action: OrderActionEnum
    quantity: int = Field(..., gt=0)
    price: float = Field(..., gt=0)


class OrderCreate(OrderBase):
    """Schema for creating an order."""
    symbol: str
    signal_id: Optional[int] = None
    trading_mode: TradingModeEnum = Field(default=TradingModeEnum.PAPER)


class OrderUpdate(BaseSchema):
    """Schema for updating order status."""
    status: OrderStatusEnum
    broker_order_id: Optional[str] = None
    filled_quantity: Optional[int] = None
    average_price: Optional[float] = None
    error_message: Optional[str] = None


class OrderResponse(OrderBase):
    """Order response schema."""
    id: int
    symbol_id: int
    signal_id: Optional[int] = None
    broker_order_id: Optional[str] = None
    status: OrderStatusEnum
    filled_quantity: int
    average_price: Optional[float] = None
    trading_mode: TradingModeEnum
    error_message: Optional[str] = None
    created_at: datetime
    executed_at: Optional[datetime] = None


class OrderWithDetails(OrderResponse):
    """Order with symbol details."""
    symbol: str


# ==================== Position Schemas ====================

class PositionBase(BaseSchema):
    """Base position schema."""
    quantity: int = Field(..., gt=0)
    entry_price: float = Field(..., gt=0)
    stop_loss: Optional[float] = Field(default=None, gt=0)
    target: Optional[float] = Field(default=None, gt=0)


class PositionCreate(PositionBase):
    """Schema for creating a position."""
    symbol: str
    trading_mode: TradingModeEnum = Field(default=TradingModeEnum.PAPER)


class PositionUpdate(BaseSchema):
    """Schema for updating position."""
    current_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None


class PositionClose(BaseSchema):
    """Schema for closing position."""
    exit_price: float = Field(..., gt=0)


class PositionResponse(PositionBase):
    """Position response schema."""
    id: int
    symbol_id: int
    current_price: float
    realized_pnl: float
    unrealized_pnl: float
    is_open: bool
    trading_mode: TradingModeEnum
    entry_time: datetime
    exit_time: Optional[datetime] = None
    updated_at: datetime


class PositionWithDetails(PositionResponse):
    """Position with symbol details."""
    symbol: str
    company_name: str


# ==================== Backtest Schemas ====================

class BacktestParameters(BaseSchema):
    """Backtest parameters schema."""
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float = Field(default=100000.0, gt=0)
    symbols: Optional[List[str]] = None  # None means all active symbols


class BacktestResultBase(BaseSchema):
    """Base backtest result schema."""
    start_date: date
    end_date: date
    initial_capital: float
    final_capital: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    accuracy: float
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    max_drawdown_duration: Optional[int] = None
    total_return: Optional[float] = None
    annual_return: Optional[float] = None


class BacktestResultResponse(BacktestResultBase):
    """Backtest result response schema."""
    id: int
    strategy_id: int
    created_at: datetime


class BacktestResultWithDetails(BacktestResultResponse):
    """Backtest result with strategy details."""
    strategy_name: str


# ==================== Alert Schemas ====================

class AlertBase(BaseSchema):
    """Base alert schema."""
    type: str = Field(..., max_length=50)
    title: str = Field(..., max_length=255)
    message: str


class AlertCreate(AlertBase):
    """Schema for creating an alert."""
    metadata: Optional[Dict[str, Any]] = None


class AlertResponse(AlertBase):
    """Alert response schema."""
    id: int
    email_sent: bool
    sms_sent: bool
    metadata: Optional[str] = None
    created_at: datetime


# ==================== Statistics Schemas ====================

class TradingStatistics(BaseSchema):
    """Trading statistics response."""
    total_positions: int
    open_positions: int
    closed_positions: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    unrealized_pnl: float
    realized_pnl: float


class StrategyStatistics(BaseSchema):
    """Strategy performance statistics."""
    strategy_id: int
    strategy_name: str
    total_signals: int
    executed_signals: int
    execution_rate: float
    avg_confidence: Optional[float] = None


# ==================== Response Wrappers ====================

class PaginatedResponse(BaseSchema):
    """Paginated response wrapper."""
    items: List[Any]
    total: int
    skip: int
    limit: int
    
    @validator('items', pre=True)
    def validate_items(cls, v):
        """Ensure items is a list."""
        return v if isinstance(v, list) else []


class SuccessResponse(BaseSchema):
    """Generic success response."""
    success: bool = True
    message: str
    data: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseSchema):
    """Generic error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None


# ==================== Export All Schemas ====================

__all__ = [
    # Enums
    "OrderActionEnum",
    "OrderStatusEnum",
    "TradingModeEnum",
    "TimeframeEnum",
    
    # Symbol
    "SymbolBase",
    "SymbolCreate",
    "SymbolUpdate",
    "SymbolResponse",
    
    # Price
    "PriceBase",
    "PriceCreate",
    "PriceResponse",
    "PriceBulkCreate",
    
    # Strategy
    "StrategyBase",
    "StrategyCreate",
    "StrategyUpdate",
    "StrategyResponse",
    
    # Signal
    "SignalBase",
    "SignalCreate",
    "SignalResponse",
    "SignalWithDetails",
    
    # Order
    "OrderBase",
    "OrderCreate",
    "OrderUpdate",
    "OrderResponse",
    "OrderWithDetails",
    
    # Position
    "PositionBase",
    "PositionCreate",
    "PositionUpdate",
    "PositionClose",
    "PositionResponse",
    "PositionWithDetails",
    
    # Backtest
    "BacktestParameters",
    "BacktestResultBase",
    "BacktestResultResponse",
    "BacktestResultWithDetails",
    
    # Alert
    "AlertBase",
    "AlertCreate",
    "AlertResponse",
    
    # Statistics
    "TradingStatistics",
    "StrategyStatistics",
    
    # Wrappers
    "PaginatedResponse",
    "SuccessResponse",
    "ErrorResponse",
]
