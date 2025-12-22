# BrokerModules/Zerodha/position_manager.py
"""
Position management module for Zerodha Kite Connect.
Provides high-level position operations with reconciliation support.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass

from BrokerModules.base_broker import (
    PositionData,
    HoldingData,
    ProductType,
    ExchangeType,
    TransactionType,
    BrokerError,
)
from BrokerModules.Zerodha.kite_client import KiteClient
from core.logger import get_logger
from core.position_tracker import BrokerPosition

logger = get_logger(__name__)


@dataclass
class PositionSummary:
    """Summary of positions."""
    total_positions: int
    total_pnl: float
    total_day_pnl: float
    long_positions: int
    short_positions: int
    total_long_value: float
    total_short_value: float


class PositionManager:
    """
    High-level position management for Zerodha.
    
    Provides position tracking, conversion, and reconciliation with:
    - Position summaries
    - Holdings management
    - Position conversion (MIS to CNC)
    - Integration with position tracker
    
    Example:
        >>> from BrokerModules.Zerodha.kite_client import KiteClient
        >>> client = KiteClient()
        >>> # ... authenticate client
        >>> 
        >>> position_manager = PositionManager(client)
        >>> 
        >>> # Get all positions
        >>> positions = position_manager.get_positions()
        >>> for pos in positions:
        ...     print(f"{pos.symbol}: {pos.quantity} @ {pos.average_price}")
        >>> 
        >>> # Get position summary
        >>> summary = position_manager.get_position_summary()
        >>> print(f"Total P&L: {summary.total_pnl}")
    """
    
    def __init__(self, client: KiteClient):
        """
        Initialize position manager.
        
        Args:
            client: Authenticated KiteClient instance
        """
        self._client = client
        logger.info("PositionManager initialized")
    
    # ==========================================================================
    # Position Operations
    # ==========================================================================
    
    def get_positions(self) -> List[PositionData]:
        """
        Get all current positions.
        
        Returns:
            List[PositionData]: List of all positions
        
        Example:
            >>> positions = position_manager.get_positions()
            >>> for pos in positions:
            ...     print(f"{pos.symbol}: {pos.quantity} shares, P&L: {pos.pnl}")
        """
        return self._client.get_positions()
    
    def get_position_by_symbol(
        self,
        symbol: str,
        exchange: Optional[ExchangeType] = None
    ) -> Optional[PositionData]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Trading symbol
            exchange: Exchange filter (optional)
        
        Returns:
            PositionData or None if not found
        
        Example:
            >>> pos = position_manager.get_position_by_symbol("RELIANCE")
            >>> if pos:
            ...     print(f"Position: {pos.quantity} shares")
        """
        positions = self.get_positions()
        
        for pos in positions:
            if pos.symbol == symbol.upper():
                if exchange is None or pos.exchange == self._client.EXCHANGE_MAP.get(exchange):
                    return pos
        
        return None
    
    def get_day_positions(self) -> List[PositionData]:
        """
        Get intraday positions only.
        
        Returns:
            List[PositionData]: List of intraday positions
        """
        positions = self.get_positions()
        return [
            pos for pos in positions
            if pos.product in ["MIS", "BO", "CO"]  # Intraday products
        ]
    
    def get_delivery_positions(self) -> List[PositionData]:
        """
        Get delivery (overnight) positions only.
        
        Returns:
            List[PositionData]: List of delivery positions
        """
        positions = self.get_positions()
        return [
            pos for pos in positions
            if pos.product in ["CNC", "NRML"]  # Delivery products
        ]
    
    def get_position_summary(self) -> PositionSummary:
        """
        Get summary of all positions.
        
        Returns:
            PositionSummary: Aggregated position metrics
        
        Example:
            >>> summary = position_manager.get_position_summary()
            >>> print(f"Total P&L: {summary.total_pnl}")
            >>> print(f"Long positions: {summary.long_positions}")
        """
        positions = self.get_positions()
        
        total_pnl = sum(pos.pnl for pos in positions)
        total_day_pnl = sum(pos.day_pnl for pos in positions)
        
        long_positions = [pos for pos in positions if pos.quantity > 0]
        short_positions = [pos for pos in positions if pos.quantity < 0]
        
        total_long_value = sum(
            abs(pos.quantity * pos.last_price)
            for pos in long_positions
        )
        
        total_short_value = sum(
            abs(pos.quantity * pos.last_price)
            for pos in short_positions
        )
        
        return PositionSummary(
            total_positions=len(positions),
            total_pnl=total_pnl,
            total_day_pnl=total_day_pnl,
            long_positions=len(long_positions),
            short_positions=len(short_positions),
            total_long_value=total_long_value,
            total_short_value=total_short_value
        )
    
    # ==========================================================================
    # Holdings Operations
    # ==========================================================================
    
    def get_holdings(self) -> List[HoldingData]:
        """
        Get all holdings (delivery positions).
        
        Returns:
            List[HoldingData]: List of all holdings
        
        Example:
            >>> holdings = position_manager.get_holdings()
            >>> for holding in holdings:
            ...     print(f"{holding.symbol}: {holding.quantity} shares")
        """
        return self._client.get_holdings()
    
    def get_holding_by_symbol(self, symbol: str) -> Optional[HoldingData]:
        """
        Get holding for a specific symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            HoldingData or None if not found
        """
        holdings = self.get_holdings()
        
        for holding in holdings:
            if holding.symbol == symbol.upper():
                return holding
        
        return None
    
    def get_holdings_value(self) -> Dict[str, float]:
        """
        Get total holdings value and P&L.
        
        Returns:
            Dict with total_value, total_cost, total_pnl, total_pnl_pct
        """
        holdings = self.get_holdings()
        
        total_value = sum(h.quantity * h.last_price for h in holdings)
        total_cost = sum(h.quantity * h.average_price for h in holdings)
        total_pnl = sum(h.pnl for h in holdings)
        total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0
        
        return {
            "total_value": total_value,
            "total_cost": total_cost,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "holdings_count": len(holdings)
        }
    
    # ==========================================================================
    # Position Conversion
    # ==========================================================================
    
    def convert_to_delivery(
        self,
        symbol: str,
        exchange: ExchangeType,
        quantity: int
    ) -> bool:
        """
        Convert intraday position to delivery (MIS to CNC).
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            quantity: Quantity to convert
        
        Returns:
            bool: True if conversion successful
        
        Example:
            >>> success = position_manager.convert_to_delivery(
            ...     symbol="RELIANCE",
            ...     exchange=ExchangeType.NSE,
            ...     quantity=10
            ... )
        """
        # Get position to determine transaction type
        position = self.get_position_by_symbol(symbol, exchange)
        
        if not position:
            raise BrokerError(
                message=f"No position found for {symbol}",
                code="POSITION_NOT_FOUND"
            )
        
        if position.product != "MIS":
            raise BrokerError(
                message=f"Position is not MIS product: {position.product}",
                code="INVALID_PRODUCT"
            )
        
        # Determine transaction type based on position
        transaction_type = (
            TransactionType.BUY if position.quantity > 0
            else TransactionType.SELL
        )
        
        return self._client.convert_position(
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            from_product=ProductType.MIS,
            to_product=ProductType.CNC
        )
    
    def convert_to_intraday(
        self,
        symbol: str,
        exchange: ExchangeType,
        quantity: int
    ) -> bool:
        """
        Convert delivery position to intraday (CNC to MIS).
        
        Args:
            symbol: Trading symbol
            exchange: Exchange type
            quantity: Quantity to convert
        
        Returns:
            bool: True if conversion successful
        """
        position = self.get_position_by_symbol(symbol, exchange)
        
        if not position:
            raise BrokerError(
                message=f"No position found for {symbol}",
                code="POSITION_NOT_FOUND"
            )
        
        if position.product != "CNC":
            raise BrokerError(
                message=f"Position is not CNC product: {position.product}",
                code="INVALID_PRODUCT"
            )
        
        transaction_type = (
            TransactionType.BUY if position.quantity > 0
            else TransactionType.SELL
        )
        
        return self._client.convert_position(
            symbol=symbol,
            exchange=exchange,
            transaction_type=transaction_type,
            quantity=quantity,
            from_product=ProductType.CNC,
            to_product=ProductType.MIS
        )
    
    # ==========================================================================
    # Integration with Position Tracker
    # ==========================================================================
    
    def get_positions_for_reconciler(self) -> List[BrokerPosition]:
        """
        Get positions formatted for PositionReconciler.
        
        Returns:
            List[BrokerPosition]: Positions in reconciler format
        
        Example:
            >>> from core.position_reconciler import PositionReconciler
            >>> broker_positions = position_manager.get_positions_for_reconciler()
            >>> result = await reconciler.reconcile_positions("Zerodha", broker_positions)
        """
        positions = self.get_positions()
        
        broker_positions = []
        for pos in positions:
            broker_pos = BrokerPosition(
                symbol=pos.symbol,
                quantity=pos.quantity,
                average_price=pos.average_price,
                last_price=pos.last_price,
                pnl=pos.pnl,
                broker_id=f"{pos.exchange}:{pos.symbol}",
                exchange=pos.exchange,
                product=pos.product
            )
            broker_positions.append(broker_pos)
        
        return broker_positions
    
    def get_position_by_broker_id(self, broker_id: str) -> Optional[PositionData]:
        """
        Get position by broker ID (exchange:symbol format).
        
        Args:
            broker_id: Broker ID in "EXCHANGE:SYMBOL" format
        
        Returns:
            PositionData or None if not found
        """
        try:
            exchange, symbol = broker_id.split(":")
        except ValueError:
            return None
        
        positions = self.get_positions()
        
        for pos in positions:
            if pos.symbol == symbol and pos.exchange == exchange:
                return pos
        
        return None
    
    # ==========================================================================
    # Position Analysis
    # ==========================================================================
    
    def get_profitable_positions(self) -> List[PositionData]:
        """
        Get all profitable positions.
        
        Returns:
            List[PositionData]: Positions with positive P&L
        """
        positions = self.get_positions()
        return [pos for pos in positions if pos.pnl > 0]
    
    def get_losing_positions(self) -> List[PositionData]:
        """
        Get all losing positions.
        
        Returns:
            List[PositionData]: Positions with negative P&L
        """
        positions = self.get_positions()
        return [pos for pos in positions if pos.pnl < 0]
    
    def get_position_exposure(self) -> Dict[str, float]:
        """
        Get position exposure breakdown.
        
        Returns:
            Dict with exposure metrics
        """
        positions = self.get_positions()
        
        long_exposure = sum(
            pos.quantity * pos.last_price
            for pos in positions if pos.quantity > 0
        )
        
        short_exposure = sum(
            abs(pos.quantity) * pos.last_price
            for pos in positions if pos.quantity < 0
        )
        
        net_exposure = long_exposure - short_exposure
        gross_exposure = long_exposure + short_exposure
        
        return {
            "long_exposure": long_exposure,
            "short_exposure": short_exposure,
            "net_exposure": net_exposure,
            "gross_exposure": gross_exposure,
            "long_short_ratio": long_exposure / short_exposure if short_exposure > 0 else float('inf')
        }
    
    def get_sector_exposure(self) -> Dict[str, float]:
        """
        Get exposure by sector (requires sector mapping).
        
        Note: This is a placeholder. Sector data would need to be
        maintained separately or fetched from another source.
        
        Returns:
            Dict[str, float]: Sector -> exposure mapping
        """
        # TODO: Implement sector mapping
        # This would require maintaining a symbol -> sector mapping
        logger.warning("Sector exposure not implemented - requires sector mapping")
        return {}
    
    # ==========================================================================
    # Utility Methods
    # ==========================================================================
    
    def has_position(self, symbol: str) -> bool:
        """
        Check if there's an open position for a symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            bool: True if position exists
        """
        return self.get_position_by_symbol(symbol) is not None
    
    def get_position_quantity(self, symbol: str) -> int:
        """
        Get position quantity for a symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            int: Position quantity (0 if no position)
        """
        position = self.get_position_by_symbol(symbol)
        return position.quantity if position else 0
    
    def get_position_value(self, symbol: str) -> float:
        """
        Get position value (quantity * last_price) for a symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            float: Position value (0 if no position)
        """
        position = self.get_position_by_symbol(symbol)
        if position:
            return abs(position.quantity * position.last_price)
        return 0.0
