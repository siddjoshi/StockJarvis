"""
Main BacktestEngine class for running backtests on trading strategies.
Executes strategies against historical data and tracks performance.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any
import pandas as pd

from core.strategy_engine import Strategy, SignalOutput
from core.logger import get_logger
from data.models import OrderAction, Timeframe
from data.repository import repository
from config import settings

logger = get_logger(__name__)


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    
    # Date range
    start_date: date
    end_date: date
    
    # Capital
    initial_capital: float = 100000.0
    
    # Risk parameters
    risk_per_trade: float = 0.02  # 2% risk per trade
    max_positions: int = 5
    
    # Costs
    slippage_pct: float = 0.001  # 0.1% slippage
    commission_pct: float = 0.001  # 0.1% commission
    
    # Execution
    timeframe: Timeframe = Timeframe.DAILY
    
    def __post_init__(self):
        """Validate configuration."""
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.risk_per_trade <= 0 or self.risk_per_trade > 1:
            raise ValueError("risk_per_trade must be between 0 and 1")


@dataclass
class BacktestTrade:
    """Represents a single trade in a backtest."""
    
    trade_id: int
    symbol: str
    action: OrderAction
    
    # Entry details
    entry_date: datetime
    entry_price: float
    quantity: int
    
    # Exit details
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    
    # Calculated fields
    @property
    def pnl(self) -> float:
        """Calculate profit/loss."""
        if self.exit_price is None:
            return 0.0
        if self.action == OrderAction.BUY:
            return (self.exit_price - self.entry_price) * self.quantity
        else:  # SELL (short)
            return (self.entry_price - self.exit_price) * self.quantity
    
    @property
    def pnl_pct(self) -> float:
        """Calculate profit/loss percentage."""
        if self.exit_price is None or self.entry_price == 0:
            return 0.0
        if self.action == OrderAction.BUY:
            return ((self.exit_price - self.entry_price) / self.entry_price) * 100
        else:
            return ((self.entry_price - self.exit_price) / self.entry_price) * 100
    
    @property
    def holding_days(self) -> int:
        """Calculate holding period in days."""
        if self.exit_date is None:
            return 0
        return (self.exit_date - self.entry_date).days
    
    @property
    def is_winner(self) -> bool:
        """Check if trade was profitable."""
        return self.pnl > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert trade to dictionary."""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "action": self.action.value,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "entry_price": round(self.entry_price, 2),
            "exit_date": self.exit_date.isoformat() if self.exit_date else None,
            "exit_price": round(self.exit_price, 2) if self.exit_price else None,
            "quantity": self.quantity,
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 2),
            "holding_days": self.holding_days,
            "exit_reason": self.exit_reason
        }


@dataclass
class BacktestPosition:
    """Represents an open position during backtest."""
    
    symbol: str
    action: OrderAction
    entry_date: datetime
    entry_price: float
    quantity: int
    stop_loss: float
    target: float
    trade_id: int


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    
    # Configuration
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float
    
    # Final state
    final_capital: float
    
    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    
    # Performance metrics (calculated later by analyzer)
    accuracy: float = 0.0
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    total_return: float = 0.0
    annual_return: float = 0.0
    profit_factor: float = 0.0
    
    # Detailed data
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    equity_dates: List[datetime] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for API response."""
        return {
            "strategy_name": self.strategy_name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": self.initial_capital,
            "final_capital": round(self.final_capital, 2),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "accuracy": round(self.accuracy, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4) if self.sharpe_ratio else None,
            "sortino_ratio": round(self.sortino_ratio, 4) if self.sortino_ratio else None,
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_duration": self.max_drawdown_duration,
            "total_return": round(self.total_return, 4),
            "annual_return": round(self.annual_return, 4),
            "profit_factor": round(self.profit_factor, 4)
        }


class BacktestEngine:
    """
    Engine for running backtests on trading strategies.
    
    Executes strategies bar-by-bar against historical data,
    simulates order execution with slippage and commissions,
    and tracks positions and P&L.
    """
    
    def __init__(
        self,
        strategy: Strategy,
        config: BacktestConfig,
        symbols: Optional[List[str]] = None
    ):
        """
        Initialize backtest engine.
        
        Args:
            strategy: Trading strategy to backtest
            config: Backtest configuration
            symbols: List of symbols to trade (None = all FNO symbols)
        """
        self.strategy = strategy
        self.config = config
        self.symbols = symbols
        
        # State tracking
        self.capital = config.initial_capital
        self.positions: Dict[str, BacktestPosition] = {}
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[float] = []
        self.equity_dates: List[datetime] = []
        self._trade_counter = 0
        
        # Performance tracking
        self._daily_returns: List[float] = []
        self._prev_equity = config.initial_capital
        
        logger.info(
            f"BacktestEngine initialized: strategy={strategy.name}, "
            f"period={config.start_date} to {config.end_date}, "
            f"capital={config.initial_capital}"
        )
    
    def run(self) -> BacktestResult:
        """
        Run the backtest.
        
        Returns:
            BacktestResult with all metrics and trades
        """
        logger.info(f"Starting backtest for strategy: {self.strategy.name}")
        
        # Get symbols to trade
        if self.symbols:
            symbols_to_trade = self.symbols
        else:
            # Use all FNO symbols from database
            fno_symbols = repository.get_fno_symbols()
            symbols_to_trade = [s.symbol for s in fno_symbols]
        
        if not symbols_to_trade:
            logger.warning("No symbols to trade")
            return self._create_empty_result()
        
        # Load and process historical data
        self._run_simulation(symbols_to_trade)
        
        # Calculate results
        result = self._calculate_results()
        
        logger.info(
            f"Backtest completed: {result.total_trades} trades, "
            f"accuracy={result.accuracy:.2%}, "
            f"return={result.total_return:.2%}"
        )
        
        return result
    
    def _run_simulation(self, symbols: List[str]) -> None:
        """
        Run bar-by-bar simulation across all symbols.
        
        Args:
            symbols: List of symbols to trade
        """
        # Convert dates to datetime
        start_dt = datetime.combine(self.config.start_date, datetime.min.time())
        end_dt = datetime.combine(self.config.end_date, datetime.max.time())
        
        # Load data for all symbols
        symbol_data: Dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            data = repository.get_prices(
                symbol=symbol,
                start_date=start_dt,
                end_date=end_dt,
                timeframe=self.config.timeframe
            )
            if not data.empty and len(data) >= self.strategy.get_required_history():
                symbol_data[symbol] = data
        
        if not symbol_data:
            logger.warning("No historical data available for any symbol")
            return
        
        # Get all unique dates across symbols
        all_dates = set()
        for data in symbol_data.values():
            all_dates.update(data.index.tolist())
        all_dates = sorted(all_dates)
        
        # Simulate bar by bar
        for current_date in all_dates:
            self._process_bar(current_date, symbol_data)
            
            # Record equity
            current_equity = self._calculate_equity(current_date, symbol_data)
            self.equity_curve.append(current_equity)
            self.equity_dates.append(current_date)
            
            # Track daily return
            if self._prev_equity > 0:
                daily_return = (current_equity - self._prev_equity) / self._prev_equity
                self._daily_returns.append(daily_return)
            self._prev_equity = current_equity
        
        # Close any remaining open positions at end
        self._close_all_positions(all_dates[-1] if all_dates else end_dt, symbol_data)
    
    def _process_bar(
        self,
        current_date: datetime,
        symbol_data: Dict[str, pd.DataFrame]
    ) -> None:
        """
        Process a single bar for all symbols.
        
        Args:
            current_date: Current simulation date
            symbol_data: Historical data for all symbols
        """
        # Check existing positions for stop loss / target hits
        self._check_exits(current_date, symbol_data)
        
        # Generate new signals if we have capacity
        if len(self.positions) < self.config.max_positions:
            self._generate_entries(current_date, symbol_data)
    
    def _check_exits(
        self,
        current_date: datetime,
        symbol_data: Dict[str, pd.DataFrame]
    ) -> None:
        """
        Check if any positions should be exited.
        
        Args:
            current_date: Current simulation date
            symbol_data: Historical data for all symbols
        """
        positions_to_close = []
        
        for symbol, position in self.positions.items():
            if symbol not in symbol_data:
                continue
            
            data = symbol_data[symbol]
            if current_date not in data.index:
                continue
            
            current_bar = data.loc[current_date]
            high = current_bar['high']
            low = current_bar['low']
            open_price = current_bar['open']
            
            exit_price = None
            exit_reason = None
            
            # Determine whether stop loss and/or target are hit on this bar
            stop_hit = False
            target_hit = False
            
            if position.action == OrderAction.BUY:
                # For long positions:
                # - Stop loss is hit if the bar's low trades at or below the stop.
                # - Target is hit if the bar's high trades at or above the target.
                stop_hit = low <= position.stop_loss
                target_hit = high >= position.target
            else:  # SELL (short)
                # For short positions:
                # - Stop loss is hit if the bar's high trades at or above the stop.
                # - Target is hit if the bar's low trades at or below the target.
                stop_hit = high >= position.stop_loss
                target_hit = low <= position.target
            
            if stop_hit and target_hit:
                # Both stop loss and target are within the bar's range.
                # Approximate intrabar order by assuming the level closer to the bar's
                # open is hit first. This reduces the bias of always prioritizing the stop.
                stop_distance = abs(open_price - position.stop_loss)
                target_distance = abs(open_price - position.target)
                
                if stop_distance < target_distance:
                    exit_price = position.stop_loss
                    exit_reason = "stop_loss_hit"
                elif target_distance < stop_distance:
                    exit_price = position.target
                    exit_reason = "target_hit"
                else:
                    # Equal distance: fall back to previous behavior, which
                    # effectively prioritized the stop loss in a tie.
                    exit_price = position.stop_loss
                    exit_reason = "stop_loss_hit"
            elif stop_hit:
                exit_price = position.stop_loss
                exit_reason = "stop_loss_hit"
            elif target_hit:
                exit_price = position.target
                exit_reason = "target_hit"
            
            if exit_price is not None:
                positions_to_close.append((symbol, exit_price, exit_reason, current_date))
        
        # Close positions
        for symbol, exit_price, exit_reason, exit_date in positions_to_close:
            self._close_position(symbol, exit_price, exit_reason, exit_date)
    
    def _generate_entries(
        self,
        current_date: datetime,
        symbol_data: Dict[str, pd.DataFrame]
    ) -> None:
        """
        Generate entry signals for symbols without positions.
        
        Args:
            current_date: Current simulation date
            symbol_data: Historical data for all symbols
        """
        for symbol, data in symbol_data.items():
            # Skip if already have position
            if symbol in self.positions:
                continue
            
            # Skip if at max positions
            if len(self.positions) >= self.config.max_positions:
                break
            
            # Get data up to current date
            historical_data = data[data.index <= current_date]
            if len(historical_data) < self.strategy.get_required_history():
                continue
            
            # Validate data
            if not self.strategy.validate_data(historical_data):
                continue
            
            # Generate signal
            try:
                signal = self.strategy.generate_signal(symbol, historical_data)
            except Exception as e:
                logger.warning(f"Error generating signal for {symbol}: {e}")
                continue
            
            if signal is None or not signal.is_valid():
                continue
            
            # Execute entry
            self._execute_entry(symbol, signal, current_date)
    
    def _execute_entry(
        self,
        symbol: str,
        signal: SignalOutput,
        entry_date: datetime
    ) -> None:
        """
        Execute a trade entry.
        
        Args:
            symbol: Symbol to trade
            signal: Trading signal
            entry_date: Entry date
        """
        # Apply slippage to entry
        slippage = signal.price * self.config.slippage_pct
        if signal.action == OrderAction.BUY:
            entry_price = signal.price + slippage
        else:
            entry_price = signal.price - slippage
        
        # Calculate position size based on risk
        risk_amount = self.capital * self.config.risk_per_trade
        risk_per_share = abs(entry_price - signal.stop_loss)
        
        if risk_per_share <= 0:
            return
        
        # Initial position size based on risk
        risk_quantity = int(risk_amount / risk_per_share)
        if risk_quantity <= 0:
            return
        
        # Maximum quantity allowed by available capital, including commission
        effective_price_per_share = entry_price * (1 + self.config.commission_pct)
        if effective_price_per_share <= 0:
            return
        max_capital_qty = int(self.capital / effective_price_per_share)
        
        # Final quantity is limited by both risk and capital constraints
        quantity = min(risk_quantity, max_capital_qty)
        if quantity <= 0:
            return
        
        # Apply commission based on final quantity
        commission = entry_price * quantity * self.config.commission_pct
        
        # Total position cost (entry + commission) - guaranteed <= self.capital
        position_cost = entry_price * quantity + commission
        
        # Deduct from capital
        self.capital -= position_cost
        
        # Create trade and position
        self._trade_counter += 1
        trade = BacktestTrade(
            trade_id=self._trade_counter,
            symbol=symbol,
            action=signal.action,
            entry_date=entry_date,
            entry_price=entry_price,
            quantity=quantity
        )
        
        position = BacktestPosition(
            symbol=symbol,
            action=signal.action,
            entry_date=entry_date,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=signal.stop_loss,
            target=signal.target,
            trade_id=self._trade_counter
        )
        
        self.trades.append(trade)
        self.positions[symbol] = position
        
        logger.debug(
            f"Entered {signal.action.value} {quantity} {symbol} @ {entry_price:.2f}, "
            f"SL={signal.stop_loss:.2f}, Target={signal.target:.2f}"
        )
    
    def _close_position(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
        exit_date: datetime
    ) -> None:
        """
        Close an open position.
        
        Args:
            symbol: Symbol to close
            exit_price: Exit price
            exit_reason: Reason for exit
            exit_date: Exit date
        """
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        # Apply slippage to exit
        slippage = exit_price * self.config.slippage_pct
        if position.action == OrderAction.BUY:
            actual_exit_price = exit_price - slippage  # Worse price for closing long
        else:
            actual_exit_price = exit_price + slippage  # Worse price for closing short
        
        # Calculate commission
        commission = actual_exit_price * position.quantity * self.config.commission_pct
        
        # Add proceeds to capital
        if position.action == OrderAction.BUY:
            proceeds = actual_exit_price * position.quantity - commission
        else:  # Short: return original amount plus/minus P&L
            pnl = (position.entry_price - actual_exit_price) * position.quantity
            proceeds = position.entry_price * position.quantity + pnl - commission
        
        self.capital += proceeds
        
        # Update trade record
        for trade in self.trades:
            if trade.trade_id == position.trade_id:
                trade.exit_date = exit_date
                trade.exit_price = actual_exit_price
                trade.exit_reason = exit_reason
                break
        
        # Remove position
        del self.positions[symbol]
        
        logger.debug(
            f"Closed {position.action.value} {position.quantity} {symbol} @ {actual_exit_price:.2f}, "
            f"reason={exit_reason}"
        )
    
    def _close_all_positions(
        self,
        exit_date: datetime,
        symbol_data: Dict[str, pd.DataFrame]
    ) -> None:
        """
        Close all remaining open positions at end of backtest.
        
        Args:
            exit_date: Exit date
            symbol_data: Historical data for all symbols
        """
        for symbol in list(self.positions.keys()):
            if symbol in symbol_data:
                data = symbol_data[symbol]
                # Get the last available close price
                if not data.empty:
                    exit_price = data['close'].iloc[-1]
                    self._close_position(symbol, exit_price, "backtest_end", exit_date)
    
    def _calculate_equity(
        self,
        current_date: datetime,
        symbol_data: Dict[str, pd.DataFrame]
    ) -> float:
        """
        Calculate current equity including open positions.
        
        Args:
            current_date: Current date
            symbol_data: Historical data for all symbols
            
        Returns:
            Current equity value
        """
        equity = self.capital
        
        for symbol, position in self.positions.items():
            if symbol not in symbol_data:
                continue
            
            data = symbol_data[symbol]
            if current_date not in data.index:
                # Use entry price if no data for this date
                current_price = position.entry_price
            else:
                current_price = data.loc[current_date, 'close']
            
            # Calculate unrealized P&L
            if position.action == OrderAction.BUY:
                unrealized_pnl = (current_price - position.entry_price) * position.quantity
            else:
                unrealized_pnl = (position.entry_price - current_price) * position.quantity
            
            # Add position contribution to equity
            if position.action == OrderAction.BUY:
                # For long positions, equity gets the current market value
                equity += current_price * position.quantity
            else:
                # For short positions, cash already includes entry proceeds,
                # so the contribution to equity is just the unrealized P&L
                equity += unrealized_pnl
        
        return equity
    
    def _calculate_results(self) -> BacktestResult:
        """
        Calculate final backtest results.
        
        Returns:
            BacktestResult with all metrics
        """
        from core.backtest_analyzer import BacktestAnalyzer
        
        # Basic trade statistics
        closed_trades = [t for t in self.trades if t.exit_price is not None]
        winning_trades = len([t for t in closed_trades if t.is_winner])
        losing_trades = len(closed_trades) - winning_trades
        accuracy = winning_trades / len(closed_trades) if closed_trades else 0.0
        
        # Create initial result
        result = BacktestResult(
            strategy_name=self.strategy.name,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=self.config.initial_capital,
            final_capital=self._prev_equity,  # Use last equity value
            total_trades=len(closed_trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            accuracy=accuracy,
            trades=self.trades,
            equity_curve=self.equity_curve,
            equity_dates=self.equity_dates
        )
        
        # Use analyzer for advanced metrics
        analyzer = BacktestAnalyzer(result, self._daily_returns)
        analyzer.calculate_all_metrics()
        
        return result
    
    def _create_empty_result(self) -> BacktestResult:
        """Create an empty result when no trades occur."""
        return BacktestResult(
            strategy_name=self.strategy.name,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=self.config.initial_capital,
            final_capital=self.config.initial_capital,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            accuracy=0.0,
            trades=[],
            equity_curve=[self.config.initial_capital],
            equity_dates=[]
        )


def run_backtest(
    strategy: Strategy,
    start_date: date,
    end_date: date,
    initial_capital: float = 100000.0,
    symbols: Optional[List[str]] = None,
    **kwargs
) -> BacktestResult:
    """
    Convenience function to run a backtest.
    
    Args:
        strategy: Trading strategy to backtest
        start_date: Backtest start date
        end_date: Backtest end date
        initial_capital: Starting capital
        symbols: List of symbols to trade (None = all FNO symbols)
        **kwargs: Additional config parameters
        
    Returns:
        BacktestResult with all metrics and trades
    """
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        **kwargs
    )
    
    engine = BacktestEngine(strategy, config, symbols)
    return engine.run()
