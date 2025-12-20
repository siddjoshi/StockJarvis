"""
Data repository for database operations using SQLAlchemy.
Single point of access for all database queries.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, date
from sqlalchemy import create_engine, and_, or_, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import pandas as pd

from config import settings
from core.logger import get_logger
from data.models import (
    Base, Symbol, Price, Strategy, Signal, Order, Position,
    BacktestResult, Alert, Timeframe, OrderAction, OrderStatus, TradingMode
)

logger = get_logger(__name__)


class DatabaseRepository:
    """Repository pattern for database access."""
    
    def __init__(self, connection_string: str = None):
        """
        Initialize database connection.
        
        Args:
            connection_string: SQLAlchemy connection URL (uses settings if not provided)
        """
        self.connection_string = connection_string or settings.db.url
        
        # Create engine with connection pooling
        self.engine = create_engine(
            self.connection_string,
            poolclass=QueuePool,
            pool_size=settings.db.pool_size,
            pool_recycle=settings.db.pool_recycle,
            echo=settings.app.debug
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        logger.info(f"Database connection initialized: {settings.db.host}/{settings.db.database}")
    
    @contextmanager
    def get_session(self) -> Session:
        """
        Context manager for database sessions.
        
        Yields:
            Database session
        
        Example:
            with repo.get_session() as session:
                symbol = session.query(Symbol).first()
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            session.close()
    
    def create_tables(self):
        """Create all tables in the database."""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created successfully")
    
    def drop_tables(self):
        """Drop all tables (use with caution!)."""
        Base.metadata.drop_all(self.engine)
        logger.warning("All database tables dropped")
    
    # ==================== Symbol Operations ====================
    
    def get_symbol(self, symbol: str) -> Optional[Symbol]:
        """Get symbol by ticker."""
        with self.get_session() as session:
            return session.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
    
    def get_symbol_by_id(self, symbol_id: int) -> Optional[Symbol]:
        """Get symbol by ID."""
        with self.get_session() as session:
            return session.query(Symbol).filter(Symbol.id == symbol_id).first()
    
    def get_all_symbols(self, active_only: bool = True) -> List[Symbol]:
        """Get all symbols."""
        with self.get_session() as session:
            query = session.query(Symbol)
            if active_only:
                query = query.filter(Symbol.is_active == True)
            return query.all()
    
    def get_fno_symbols(self) -> List[Symbol]:
        """Get all F&O symbols."""
        with self.get_session() as session:
            return session.query(Symbol).filter(
                Symbol.is_fno == True,
                Symbol.is_active == True
            ).all()
    
    def add_symbol(self, symbol: str, company_name: str, **kwargs) -> Symbol:
        """Add new symbol."""
        with self.get_session() as session:
            new_symbol = Symbol(
                symbol=symbol.upper(),
                company_name=company_name,
                **kwargs
            )
            session.add(new_symbol)
            session.flush()
            session.refresh(new_symbol)
            logger.info(f"Added new symbol: {symbol}")
            return new_symbol
    
    # ==================== Price Operations ====================
    
    def get_prices(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: Timeframe = Timeframe.DAILY
    ) -> pd.DataFrame:
        """
        Get price data as pandas DataFrame.
        
        Args:
            symbol: Stock ticker
            start_date: Start date
            end_date: End date
            timeframe: Data timeframe
        
        Returns:
            DataFrame with OHLCV data
        """
        with self.get_session() as session:
            symbol_obj = session.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
            if not symbol_obj:
                logger.warning(f"Symbol not found: {symbol}")
                return pd.DataFrame()
            
            query = session.query(Price).filter(
                Price.symbol_id == symbol_obj.id,
                Price.timeframe == timeframe,
                Price.timestamp.between(start_date, end_date)
            ).order_by(Price.timestamp)
            
            prices = query.all()
            
            if not prices:
                return pd.DataFrame()
            
            # Convert to DataFrame
            data = {
                'timestamp': [p.timestamp for p in prices],
                'open': [p.open for p in prices],
                'high': [p.high for p in prices],
                'low': [p.low for p in prices],
                'close': [p.close for p in prices],
                'volume': [p.volume for p in prices]
            }
            
            df = pd.DataFrame(data)
            df.set_index('timestamp', inplace=True)
            return df
    
    def get_latest_price(self, symbol: str, timeframe: Timeframe = Timeframe.DAILY) -> Optional[Price]:
        """Get latest price for a symbol."""
        with self.get_session() as session:
            symbol_obj = session.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
            if not symbol_obj:
                return None
            
            return session.query(Price).filter(
                Price.symbol_id == symbol_obj.id,
                Price.timeframe == timeframe
            ).order_by(Price.timestamp.desc()).first()
    
    def add_prices_bulk(self, symbol: str, df: pd.DataFrame, timeframe: Timeframe = Timeframe.DAILY):
        """
        Add multiple price records from DataFrame.
        
        Args:
            symbol: Stock ticker
            df: DataFrame with columns: timestamp, open, high, low, close, volume
            timeframe: Data timeframe
        """
        with self.get_session() as session:
            symbol_obj = session.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
            if not symbol_obj:
                raise ValueError(f"Symbol not found: {symbol}")
            
            prices = []
            for idx, row in df.iterrows():
                price = Price(
                    symbol_id=symbol_obj.id,
                    timestamp=idx if isinstance(idx, datetime) else row['timestamp'],
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['volume'],
                    timeframe=timeframe,
                    turnover=row.get('turnover')
                )
                prices.append(price)
            
            session.bulk_save_objects(prices)
            logger.info(f"Added {len(prices)} price records for {symbol}")
    
    # ==================== Strategy Operations ====================
    
    def get_strategy(self, name: str) -> Optional[Strategy]:
        """Get strategy by name."""
        with self.get_session() as session:
            return session.query(Strategy).filter(Strategy.name == name).first()
    
    def get_active_strategies(self) -> List[Strategy]:
        """Get all active and validated strategies."""
        with self.get_session() as session:
            return session.query(Strategy).filter(
                Strategy.is_active == True,
                Strategy.is_validated == True
            ).all()
    
    def add_strategy(self, name: str, description: str = None, **kwargs) -> Strategy:
        """Add new strategy."""
        with self.get_session() as session:
            strategy = Strategy(
                name=name,
                description=description,
                **kwargs
            )
            session.add(strategy)
            session.flush()
            session.refresh(strategy)
            logger.info(f"Added new strategy: {name}")
            return strategy
    
    # ==================== Signal Operations ====================
    
    def add_signal(
        self,
        strategy_name: str,
        symbol: str,
        action: OrderAction,
        price: float,
        stop_loss: float,
        target: float,
        confidence: float = None,
        reason: str = None
    ) -> Signal:
        """Add new trading signal."""
        with self.get_session() as session:
            strategy = session.query(Strategy).filter(Strategy.name == strategy_name).first()
            symbol_obj = session.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
            
            if not strategy or not symbol_obj:
                raise ValueError("Strategy or symbol not found")
            
            signal = Signal(
                strategy_id=strategy.id,
                symbol_id=symbol_obj.id,
                action=action,
                price=price,
                stop_loss=stop_loss,
                target=target,
                confidence=confidence,
                reason=reason
            )
            session.add(signal)
            session.flush()
            session.refresh(signal)
            logger.info(f"New signal: {action.value} {symbol} @ {price}")
            return signal
    
    def get_unexecuted_signals(self) -> List[Signal]:
        """Get all signals that haven't been executed."""
        with self.get_session() as session:
            return session.query(Signal).filter(Signal.is_executed == False).all()
    
    # ==================== Order Operations ====================
    
    def add_order(
        self,
        symbol: str,
        action: OrderAction,
        quantity: int,
        price: float,
        signal_id: int = None,
        trading_mode: TradingMode = None
    ) -> Order:
        """Add new order."""
        trading_mode = trading_mode or TradingMode(settings.trading.mode)
        
        with self.get_session() as session:
            symbol_obj = session.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
            if not symbol_obj:
                raise ValueError(f"Symbol not found: {symbol}")
            
            order = Order(
                signal_id=signal_id,
                symbol_id=symbol_obj.id,
                action=action,
                quantity=quantity,
                price=price,
                trading_mode=trading_mode
            )
            session.add(order)
            session.flush()
            session.refresh(order)
            logger.info(f"New order: {action.value} {quantity} {symbol} @ {price}")
            return order
    
    def update_order_status(
        self,
        order_id: int,
        status: OrderStatus,
        broker_order_id: str = None,
        **kwargs
    ):
        """Update order status."""
        with self.get_session() as session:
            order = session.query(Order).filter(Order.id == order_id).first()
            if order:
                order.status = status
                if broker_order_id:
                    order.broker_order_id = broker_order_id
                for key, value in kwargs.items():
                    setattr(order, key, value)
                logger.info(f"Order {order_id} status updated to {status.value}")
    
    # ==================== Position Operations ====================
    
    def get_open_positions(self, trading_mode: TradingMode = None) -> List[Position]:
        """Get all open positions."""
        trading_mode = trading_mode or TradingMode(settings.trading.mode)
        
        with self.get_session() as session:
            return session.query(Position).filter(
                Position.is_open == True,
                Position.trading_mode == trading_mode
            ).all()
    
    def add_position(
        self,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_loss: float = None,
        target: float = None,
        trading_mode: TradingMode = None
    ) -> Position:
        """Add new position."""
        trading_mode = trading_mode or TradingMode(settings.trading.mode)
        
        with self.get_session() as session:
            symbol_obj = session.query(Symbol).filter(Symbol.symbol == symbol.upper()).first()
            if not symbol_obj:
                raise ValueError(f"Symbol not found: {symbol}")
            
            position = Position(
                symbol_id=symbol_obj.id,
                quantity=quantity,
                entry_price=entry_price,
                current_price=entry_price,
                stop_loss=stop_loss,
                target=target,
                trading_mode=trading_mode
            )
            session.add(position)
            session.flush()
            session.refresh(position)
            logger.info(f"New position: {quantity} {symbol} @ {entry_price}")
            return position
    
    def update_position_price(self, position_id: int, current_price: float):
        """Update position's current price and unrealized P&L."""
        with self.get_session() as session:
            position = session.query(Position).filter(Position.id == position_id).first()
            if position:
                position.current_price = current_price
                position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
    
    def close_position(self, position_id: int, exit_price: float):
        """Close a position."""
        with self.get_session() as session:
            position = session.query(Position).filter(Position.id == position_id).first()
            if position:
                position.is_open = False
                position.current_price = exit_price
                position.exit_time = datetime.utcnow()
                position.realized_pnl = (exit_price - position.entry_price) * position.quantity
                logger.info(f"Position {position_id} closed with P&L: {position.realized_pnl}")
    
    # ==================== Backtest Operations ====================
    
    def add_backtest_result(self, strategy_name: str, **metrics) -> BacktestResult:
        """Add backtest result."""
        with self.get_session() as session:
            strategy = session.query(Strategy).filter(Strategy.name == strategy_name).first()
            if not strategy:
                raise ValueError(f"Strategy not found: {strategy_name}")
            
            result = BacktestResult(
                strategy_id=strategy.id,
                **metrics
            )
            session.add(result)
            session.flush()
            
            # Update strategy metrics
            strategy.backtest_accuracy = metrics.get('accuracy')
            strategy.backtest_sharpe = metrics.get('sharpe_ratio')
            strategy.backtest_max_drawdown = metrics.get('max_drawdown')
            strategy.is_validated = metrics.get('accuracy', 0) >= settings.trading.min_strategy_accuracy
            
            logger.info(f"Backtest result added for {strategy_name}: accuracy={metrics.get('accuracy')}")
            return result
    
    # ==================== Alert Operations ====================
    
    def add_alert(
        self,
        alert_type: str,
        title: str,
        message: str,
        metadata: Dict[str, Any] = None
    ) -> Alert:
        """Add new alert."""
        import json
        
        with self.get_session() as session:
            alert = Alert(
                type=alert_type,
                title=title,
                message=message,
                metadata=json.dumps(metadata) if metadata else None
            )
            session.add(alert)
            session.flush()
            session.refresh(alert)
            logger.info(f"New alert: {alert_type} - {title}")
            return alert


# Global repository instance
repository = DatabaseRepository()
