"""
Unified scanner for running strategies across symbols.
Replaces separate EOD and Intraday scanners with single parameterized implementation.
"""

from typing import List, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.logger import get_logger
from core.strategy_engine import Strategy, SignalOutput, registry
from data.repository import repository
from data.models import Timeframe, OrderAction
from config import settings

logger = get_logger(__name__)


class Scanner:
    """Unified scanner for executing strategies across multiple symbols."""
    
    def __init__(
        self,
        strategies: List[Strategy] = None,
        symbols: List[str] = None,
        timeframe: Timeframe = Timeframe.DAILY,
        lookback_days: int = 365
    ):
        """
        Initialize scanner.
        
        Args:
            strategies: List of strategies to run (uses all tradeable if None)
            symbols: List of symbols to scan (uses all active if None)
            timeframe: Data timeframe to use
            lookback_days: Number of days of historical data to fetch
        """
        self.strategies = strategies or registry.get_tradeable()
        self.timeframe = timeframe
        self.lookback_days = lookback_days
        
        # Get symbols from database if not provided
        if symbols is None:
            symbol_objects = repository.get_fno_symbols()  # F&O stocks for higher liquidity
            self.symbols = [s.symbol for s in symbol_objects]
        else:
            self.symbols = symbols
        
        logger.info(
            f"Scanner initialized: {len(self.strategies)} strategies, "
            f"{len(self.symbols)} symbols, timeframe={timeframe.value}"
        )
    
    def scan(self, parallel: bool = True) -> List[SignalOutput]:
        """
        Run all strategies across all symbols.
        
        Args:
            parallel: Use parallel execution for speed
        
        Returns:
            List of generated signals
        """
        logger.info(f"Starting scan: {len(self.symbols)} symbols × {len(self.strategies)} strategies")
        
        all_signals = []
        
        if parallel:
            all_signals = self._scan_parallel()
        else:
            all_signals = self._scan_sequential()
        
        # Filter valid signals
        valid_signals = [s for s in all_signals if s.is_valid()]
        
        logger.info(
            f"Scan complete: {len(valid_signals)} valid signals from "
            f"{len(all_signals)} total signals"
        )
        
        return valid_signals
    
    def _scan_sequential(self) -> List[SignalOutput]:
        """Scan symbols sequentially."""
        signals = []
        
        for symbol in self.symbols:
            for strategy in self.strategies:
                signal = self._run_strategy_on_symbol(strategy, symbol)
                if signal:
                    signals.append(signal)
        
        return signals
    
    def _scan_parallel(self) -> List[SignalOutput]:
        """Scan symbols in parallel using thread pool."""
        signals = []
        
        # Create tasks for all symbol-strategy combinations
        tasks = [
            (strategy, symbol)
            for symbol in self.symbols
            for strategy in self.strategies
        ]
        
        # Execute in parallel
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_task = {
                executor.submit(self._run_strategy_on_symbol, strategy, symbol): (strategy, symbol)
                for strategy, symbol in tasks
            }
            
            for future in as_completed(future_to_task):
                strategy, symbol = future_to_task[future]
                try:
                    signal = future.result()
                    if signal:
                        signals.append(signal)
                except Exception as e:
                    logger.error(f"Error running {strategy.name} on {symbol}: {e}")
        
        return signals
    
    def _run_strategy_on_symbol(self, strategy: Strategy, symbol: str) -> Optional[SignalOutput]:
        """
        Run single strategy on single symbol.
        
        Args:
            strategy: Strategy to run
            symbol: Symbol to analyze
        
        Returns:
            Signal if generated, None otherwise
        """
        try:
            # Fetch historical data
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days)
            
            data = repository.get_prices(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                timeframe=self.timeframe
            )
            
            if data.empty:
                logger.debug(f"No data available for {symbol}")
                return None
            
            # Validate data
            if not strategy.validate_data(data):
                logger.debug(f"Data validation failed for {strategy.name} on {symbol}")
                return None
            
            # Generate signal
            signal = strategy.generate_signal(symbol, data)
            
            if signal:
                logger.info(
                    f"Signal generated: {strategy.name} → {signal.action.value} "
                    f"{symbol} @ {signal.price}"
                )
                
                # Save to database
                repository.add_signal(
                    strategy_name=strategy.name,
                    symbol=symbol,
                    action=signal.action,
                    price=signal.price,
                    stop_loss=signal.stop_loss,
                    target=signal.target,
                    confidence=signal.confidence,
                    reason=signal.reason
                )
            
            return signal
            
        except Exception as e:
            logger.error(f"Error in {strategy.name} on {symbol}: {e}", exc_info=True)
            return None
    
    def scan_single_symbol(self, symbol: str) -> List[SignalOutput]:
        """
        Scan single symbol with all strategies.
        
        Args:
            symbol: Symbol to scan
        
        Returns:
            List of signals
        """
        logger.info(f"Scanning {symbol} with {len(self.strategies)} strategies")
        
        signals = []
        for strategy in self.strategies:
            signal = self._run_strategy_on_symbol(strategy, symbol)
            if signal and signal.is_valid():
                signals.append(signal)
        
        return signals
    
    def scan_with_strategy(self, strategy_name: str) -> List[SignalOutput]:
        """
        Run single strategy across all symbols.
        
        Args:
            strategy_name: Name of strategy to run
        
        Returns:
            List of signals
        """
        strategy = registry.get(strategy_name)
        if not strategy:
            logger.error(f"Strategy not found: {strategy_name}")
            return []
        
        if not strategy.is_tradeable():
            logger.error(f"Strategy {strategy_name} is not tradeable")
            return []
        
        logger.info(f"Running strategy {strategy_name} on {len(self.symbols)} symbols")
        
        signals = []
        for symbol in self.symbols:
            signal = self._run_strategy_on_symbol(strategy, symbol)
            if signal and signal.is_valid():
                signals.append(signal)
        
        return signals


# EOD Scanner (convenience wrapper)
def create_eod_scanner(symbols: List[str] = None) -> Scanner:
    """
    Create scanner for end-of-day analysis.
    
    Args:
        symbols: List of symbols (uses all F&O stocks if None)
    
    Returns:
        Scanner configured for EOD
    """
    return Scanner(
        symbols=symbols,
        timeframe=Timeframe.DAILY,
        lookback_days=365
    )


# Intraday Scanner (convenience wrapper)
def create_intraday_scanner(symbols: List[str] = None) -> Scanner:
    """
    Create scanner for intraday analysis.
    
    Args:
        symbols: List of symbols (uses all F&O stocks if None)
    
    Returns:
        Scanner configured for intraday
    """
    return Scanner(
        symbols=symbols,
        timeframe=Timeframe.MINUTE_15,  # 15-minute bars
        lookback_days=30  # Less history needed for intraday
    )
