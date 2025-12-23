"""
Backtest performance analyzer for calculating metrics and generating reports.
Calculates returns, risk metrics, trade statistics, and equity curves.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, date, timedelta
import math

from core.logger import get_logger

if TYPE_CHECKING:
    from core.backtester import BacktestResult, BacktestTrade

logger = get_logger(__name__)


# Risk-free rate for Sharpe ratio (annualized)
RISK_FREE_RATE = 0.06  # 6% for India


@dataclass
class PerformanceMetrics:
    """Container for all performance metrics."""
    
    # Returns
    total_return: float = 0.0
    annual_return: float = 0.0
    cagr: float = 0.0
    
    # Risk metrics
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    volatility: float = 0.0
    downside_deviation: float = 0.0
    
    # Drawdown
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    avg_drawdown: float = 0.0
    
    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    
    # Position metrics
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    risk_reward_ratio: float = 0.0
    
    # Time metrics
    avg_holding_days: float = 0.0
    max_holding_days: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "returns": {
                "total_return": round(self.total_return, 4),
                "annual_return": round(self.annual_return, 4),
                "cagr": round(self.cagr, 4)
            },
            "risk": {
                "sharpe_ratio": round(self.sharpe_ratio, 4) if self.sharpe_ratio else None,
                "sortino_ratio": round(self.sortino_ratio, 4) if self.sortino_ratio else None,
                "calmar_ratio": round(self.calmar_ratio, 4) if self.calmar_ratio else None,
                "volatility": round(self.volatility, 4),
                "downside_deviation": round(self.downside_deviation, 4)
            },
            "drawdown": {
                "max_drawdown": round(self.max_drawdown, 4),
                "max_drawdown_duration": self.max_drawdown_duration,
                "avg_drawdown": round(self.avg_drawdown, 4)
            },
            "trades": {
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "win_rate": round(self.win_rate, 4),
                "profit_factor": round(self.profit_factor, 4)
            },
            "positions": {
                "avg_win": round(self.avg_win, 2),
                "avg_loss": round(self.avg_loss, 2),
                "avg_win_pct": round(self.avg_win_pct, 4),
                "avg_loss_pct": round(self.avg_loss_pct, 4),
                "largest_win": round(self.largest_win, 2),
                "largest_loss": round(self.largest_loss, 2),
                "risk_reward_ratio": round(self.risk_reward_ratio, 4)
            },
            "time": {
                "avg_holding_days": round(self.avg_holding_days, 1),
                "max_holding_days": self.max_holding_days
            }
        }


class BacktestAnalyzer:
    """
    Analyzes backtest results and calculates performance metrics.
    
    Calculates:
    - Returns (total, annualized, CAGR)
    - Risk metrics (Sharpe, Sortino, Calmar)
    - Drawdown analysis
    - Trade statistics
    """
    
    def __init__(
        self,
        result: "BacktestResult",
        daily_returns: Optional[List[float]] = None
    ):
        """
        Initialize analyzer.
        
        Args:
            result: BacktestResult to analyze
            daily_returns: List of daily returns (optional, calculated if not provided)
        """
        self.result = result
        self.daily_returns = daily_returns or []
        self.metrics = PerformanceMetrics()
        
        logger.debug(f"BacktestAnalyzer initialized for {result.strategy_name}")
    
    def calculate_all_metrics(self) -> PerformanceMetrics:
        """
        Calculate all performance metrics.
        
        Returns:
            PerformanceMetrics with all calculated values
        """
        self._calculate_returns()
        self._calculate_risk_metrics()
        self._calculate_drawdown()
        self._calculate_trade_metrics()
        self._calculate_time_metrics()
        
        # Update result object
        self.result.total_return = self.metrics.total_return
        self.result.annual_return = self.metrics.annual_return
        self.result.sharpe_ratio = self.metrics.sharpe_ratio
        self.result.sortino_ratio = self.metrics.sortino_ratio
        self.result.max_drawdown = self.metrics.max_drawdown
        self.result.max_drawdown_duration = self.metrics.max_drawdown_duration
        self.result.profit_factor = self.metrics.profit_factor
        self.result.accuracy = self.metrics.win_rate
        
        return self.metrics
    
    def _calculate_returns(self) -> None:
        """Calculate return metrics."""
        initial = self.result.initial_capital
        final = self.result.final_capital
        
        if initial <= 0:
            return
        
        # Total return
        self.metrics.total_return = (final - initial) / initial
        
        # Calculate period in years
        start = self.result.start_date
        end = self.result.end_date
        days = (end - start).days
        years = days / 365.0
        
        if years <= 0:
            return
        
        # Annualized return (simple)
        self.metrics.annual_return = self.metrics.total_return / years
        
        # CAGR (Compound Annual Growth Rate)
        if final > 0:
            self.metrics.cagr = (final / initial) ** (1 / years) - 1
    
    def _calculate_risk_metrics(self) -> None:
        """Calculate risk-adjusted return metrics."""
        if not self.daily_returns or len(self.daily_returns) < 2:
            return
        
        # Convert to numpy-like calculations without numpy
        returns = self.daily_returns
        n = len(returns)
        
        # Mean return
        mean_return = sum(returns) / n
        
        # Standard deviation (volatility)
        variance = sum((r - mean_return) ** 2 for r in returns) / (n - 1)
        std_dev = math.sqrt(variance) if variance > 0 else 0
        
        # Annualized volatility (assume 252 trading days)
        self.metrics.volatility = std_dev * math.sqrt(252)
        
        # Sharpe Ratio
        # (Annualized Return - Risk Free Rate) / Annualized Volatility
        if self.metrics.volatility > 0:
            annualized_mean = mean_return * 252
            self.metrics.sharpe_ratio = (annualized_mean - RISK_FREE_RATE) / self.metrics.volatility
        
        # Downside deviation (for Sortino ratio)
        downside_returns = [r for r in returns if r < 0]
        if downside_returns:
            downside_variance = sum(r ** 2 for r in downside_returns) / len(downside_returns)
            self.metrics.downside_deviation = math.sqrt(downside_variance) * math.sqrt(252)
            
            # Sortino Ratio
            if self.metrics.downside_deviation > 0:
                annualized_mean = mean_return * 252
                self.metrics.sortino_ratio = (annualized_mean - RISK_FREE_RATE) / self.metrics.downside_deviation
        
        # Calmar Ratio
        if self.metrics.max_drawdown > 0:
            self.metrics.calmar_ratio = self.metrics.annual_return / self.metrics.max_drawdown
    
    def _calculate_drawdown(self) -> None:
        """Calculate drawdown metrics."""
        equity_curve = self.result.equity_curve
        
        if not equity_curve:
            return
        
        # Calculate drawdown series
        peak = equity_curve[0]
        drawdowns = []
        drawdown_durations = []
        current_duration = 0
        
        for equity in equity_curve:
            if equity > peak:
                peak = equity
                if current_duration > 0:
                    drawdown_durations.append(current_duration)
                current_duration = 0
            else:
                dd = (peak - equity) / peak if peak > 0 else 0
                drawdowns.append(dd)
                current_duration += 1
        
        # Handle final drawdown duration
        if current_duration > 0:
            drawdown_durations.append(current_duration)
        
        # Max drawdown
        self.metrics.max_drawdown = max(drawdowns) if drawdowns else 0
        
        # Max drawdown duration
        self.metrics.max_drawdown_duration = max(drawdown_durations) if drawdown_durations else 0
        
        # Average drawdown
        positive_drawdowns = [d for d in drawdowns if d > 0]
        self.metrics.avg_drawdown = sum(positive_drawdowns) / len(positive_drawdowns) if positive_drawdowns else 0
    
    def _calculate_trade_metrics(self) -> None:
        """Calculate trade statistics."""
        trades = self.result.trades
        closed_trades = [t for t in trades if t.exit_price is not None]
        
        if not closed_trades:
            return
        
        # Basic counts
        self.metrics.total_trades = len(closed_trades)
        
        winning = [t for t in closed_trades if t.pnl > 0]
        losing = [t for t in closed_trades if t.pnl <= 0]
        
        self.metrics.winning_trades = len(winning)
        self.metrics.losing_trades = len(losing)
        
        # Win rate
        self.metrics.win_rate = self.metrics.winning_trades / self.metrics.total_trades
        
        # P&L metrics
        if winning:
            total_wins = sum(t.pnl for t in winning)
            self.metrics.avg_win = total_wins / len(winning)
            self.metrics.largest_win = max(t.pnl for t in winning)
            self.metrics.avg_win_pct = sum(t.pnl_pct for t in winning) / len(winning)
        
        if losing:
            total_losses = abs(sum(t.pnl for t in losing))
            self.metrics.avg_loss = -total_losses / len(losing)  # Negative
            self.metrics.largest_loss = min(t.pnl for t in losing)  # Most negative
            self.metrics.avg_loss_pct = sum(t.pnl_pct for t in losing) / len(losing)
        
        # Profit factor
        total_profit = sum(t.pnl for t in winning) if winning else 0
        total_loss = abs(sum(t.pnl for t in losing)) if losing else 0
        
        if total_loss > 0:
            self.metrics.profit_factor = total_profit / total_loss
        elif total_profit > 0:
            self.metrics.profit_factor = float('inf')
        
        # Risk/Reward ratio (average win / average loss)
        if self.metrics.avg_loss < 0:
            self.metrics.risk_reward_ratio = abs(self.metrics.avg_win / self.metrics.avg_loss)
    
    def _calculate_time_metrics(self) -> None:
        """Calculate time-based metrics."""
        trades = self.result.trades
        closed_trades = [t for t in trades if t.exit_price is not None]
        
        if not closed_trades:
            return
        
        holding_days = [t.holding_days for t in closed_trades]
        
        self.metrics.avg_holding_days = sum(holding_days) / len(holding_days)
        self.metrics.max_holding_days = max(holding_days)
    
    def get_equity_curve_data(self) -> Dict[str, Any]:
        """
        Get equity curve data for plotting.
        
        Returns:
            Dictionary with dates and equity values
        """
        return {
            "dates": [d.isoformat() if hasattr(d, 'isoformat') else str(d) 
                     for d in self.result.equity_dates],
            "equity": self.result.equity_curve
        }
    
    def get_drawdown_curve(self) -> List[float]:
        """
        Calculate drawdown at each point in equity curve.
        
        Returns:
            List of drawdown values (as percentages)
        """
        equity_curve = self.result.equity_curve
        
        if not equity_curve:
            return []
        
        drawdowns = []
        peak = equity_curve[0]
        
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            drawdowns.append(dd)
        
        return drawdowns
    
    def get_monthly_returns(self) -> Dict[str, float]:
        """
        Calculate monthly returns.
        
        Returns:
            Dictionary mapping year-month to return
        """
        if not self.result.equity_curve or not self.result.equity_dates:
            return {}
        
        monthly_returns = {}
        
        # Group by month
        monthly_data: Dict[str, List[tuple]] = {}
        for i, (date, equity) in enumerate(zip(self.result.equity_dates, self.result.equity_curve)):
            key = date.strftime("%Y-%m") if hasattr(date, 'strftime') else str(date)[:7]
            if key not in monthly_data:
                monthly_data[key] = []
            monthly_data[key].append((i, equity))
        
        # Calculate return for each month
        prev_month_end = self.result.initial_capital
        for month in sorted(monthly_data.keys()):
            data_points = monthly_data[month]
            month_end = data_points[-1][1]  # Last equity value of month
            
            if prev_month_end > 0:
                monthly_returns[month] = (month_end - prev_month_end) / prev_month_end
            
            prev_month_end = month_end
        
        return monthly_returns
    
    def generate_summary(self) -> str:
        """
        Generate text summary of backtest results.
        
        Returns:
            Formatted summary string
        """
        r = self.result
        m = self.metrics
        
        # Handle optional/infinity values
        if m.profit_factor == float('inf'):
            pf_str = "∞ (No losses)"
        else:
            pf_str = f"{m.profit_factor:.2f}"
        
        sharpe_str = f"{m.sharpe_ratio:.2f}" if m.sharpe_ratio is not None else "N/A"
        sortino_str = f"{m.sortino_ratio:.2f}" if m.sortino_ratio is not None else "N/A"
        
        summary = f"""
================================================================================
BACKTEST RESULTS - {r.strategy_name}
================================================================================
Period: {r.start_date} to {r.end_date}
Initial Capital: ${r.initial_capital:,.2f}
Final Capital: ${r.final_capital:,.2f}

RETURNS
-------
Total Return: {m.total_return:.2%}
Annual Return: {m.annual_return:.2%}
CAGR: {m.cagr:.2%}

RISK METRICS
------------
Sharpe Ratio: {sharpe_str}
Sortino Ratio: {sortino_str}
Max Drawdown: {m.max_drawdown:.2%}
Volatility: {m.volatility:.2%}

TRADE STATISTICS
----------------
Total Trades: {m.total_trades}
Winning Trades: {m.winning_trades} ({m.win_rate:.1%})
Losing Trades: {m.losing_trades}
Profit Factor: {pf_str}

POSITION METRICS
----------------
Average Win: ${m.avg_win:,.2f} ({m.avg_win_pct:.2%})
Average Loss: ${m.avg_loss:,.2f} ({m.avg_loss_pct:.2%})
Largest Win: ${m.largest_win:,.2f}
Largest Loss: ${m.largest_loss:,.2f}
Risk/Reward: {m.risk_reward_ratio:.2f}

TIME METRICS
------------
Avg Holding Period: {m.avg_holding_days:.1f} days
Max Holding Period: {m.max_holding_days} days
================================================================================
"""
        return summary


def analyze_backtest(result: "BacktestResult", daily_returns: Optional[List[float]] = None) -> PerformanceMetrics:
    """
    Convenience function to analyze a backtest result.
    
    Args:
        result: BacktestResult to analyze
        daily_returns: Optional list of daily returns
        
    Returns:
        PerformanceMetrics with all calculated values
    """
    analyzer = BacktestAnalyzer(result, daily_returns)
    return analyzer.calculate_all_metrics()
