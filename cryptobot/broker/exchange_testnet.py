from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import ccxt

from cryptobot.core.logging import get_logger
from cryptobot.core.types import Fill, Order, Position

log = get_logger()


@dataclass
class ExchangeTestnetPortfolio:
    """Portfolio state tracked from exchange testnet account."""
    cash: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)
    equity: float = 0.0
    last_update: float = 0.0


class ExchangeTestnetBroker:
    """
    Broker that uses real exchange testnet APIs directly.
    All orders are executed on the testnet (virtual funds, no risk).
    
    Advantages over paper simulation:
    - Real fees, slippage, liquidation rules
    - Real API behavior and error handling
    - Validates strategy works before going live
    """
    
    def __init__(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        market_type: str = "futures",
        testnet: bool = True,
    ):
        self.exchange_id = exchange_id
        self.market_type = market_type
        self.testnet = testnet
        
        # Initialize CCXT exchange
        ex_class = getattr(ccxt, exchange_id)
        options: Dict[str, object] = {}
        if market_type == "futures":
            options["defaultType"] = "future"
        
        self.ex = ex_class({
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": options,
        })
        
        # Enable testnet mode
        try:
            self.ex.set_sandbox_mode(bool(testnet))  # type: ignore[attr-defined]
        except Exception as e:
            log.warning(f"Exchange {exchange_id} may not support sandbox_mode: {e}")
        
        # Load markets
        try:
            self.ex.load_markets()
            log.info(f"Loaded {len(self.ex.markets)} markets from {exchange_id}")
        except Exception as e:
            log.error(f"Failed to load markets: {e}")
            raise
        
        # Portfolio cache
        self.portfolio = ExchangeTestnetPortfolio()
        self._refresh_portfolio()
    
    def _refresh_portfolio(self) -> None:
        """Refresh portfolio state from exchange."""
        try:
            if self.market_type == "futures":
                # Fetch futures balance
                balance = self.ex.fetch_balance({'type': 'future'})  # type: ignore[call-arg]
                self.portfolio.cash = float(balance.get("USDT", {}).get("free", 0.0))
                self.portfolio.equity = float(balance.get("USDT", {}).get("total", 0.0))
                
                # Fetch open positions
                positions = self.ex.fetch_positions()
                self.portfolio.positions = {}
                for pos_dict in positions:
                    size = float(pos_dict.get("contracts", 0) or 0)
                    if abs(size) > 1e-8:  # Only non-zero positions
                        symbol = str(pos_dict.get("symbol", ""))
                        if symbol:
                            entry_price = float(pos_dict.get("entryPrice", 0) or 0)
                            self.portfolio.positions[symbol] = Position(
                                symbol=symbol,
                                qty=size,
                                avg_price=entry_price,
                            )
            else:
                # Spot balance
                balance = self.ex.fetch_balance()
                self.portfolio.cash = float(balance.get("USDT", {}).get("free", 0.0))
                self.portfolio.equity = float(balance.get("USDT", {}).get("total", 0.0))
                # Spot positions = non-zero balances
                self.portfolio.positions = {}
                for currency, bal in balance.items():
                    if isinstance(bal, dict):
                        total = float(bal.get("total", 0) or 0)
                        if total > 1e-8:
                            symbol = f"{currency}/USDT"
                            self.portfolio.positions[symbol] = Position(
                                symbol=symbol,
                                qty=total,
                                avg_price=0.0,  # Spot doesn't track avg entry
                            )
            
            self.portfolio.last_update = time.time()
            log.debug(f"Portfolio refreshed: cash={self.portfolio.cash:.2f}, equity={self.portfolio.equity:.2f}, positions={len(self.portfolio.positions)}")
        
        except Exception as e:
            log.error(f"Failed to refresh portfolio: {e}")
            # Don't raise, use cached values
    
    def get_portfolio(self) -> ExchangeTestnetPortfolio:
        """Get current portfolio state (refreshes if stale)."""
        if time.time() - self.portfolio.last_update > 5.0:  # Refresh every 5s
            self._refresh_portfolio()
        return self.portfolio
    
    def _set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol on futures."""
        if self.market_type != "futures":
            return True  # No leverage for spot
        
        try:
            # CCXT unified method - some exchanges may require symbol first
            try:
                result = self.ex.set_leverage(leverage, symbol)  # type: ignore[call-arg,attr-defined]
            except TypeError:
                # Try alternative signature
                result = self.ex.set_leverage(symbol, leverage)  # type: ignore[call-arg,attr-defined]
            log.debug(f"Set leverage {leverage}x for {symbol}")
            return True
        except Exception as e:
            log.warning(f"Failed to set leverage {leverage}x for {symbol}: {e}")
            # Some exchanges don't support programmatic leverage setting
            # Or leverage is set per-position, not per-symbol
            return False
    
    def _set_margin_mode(self, symbol: str, mode: str = "isolated") -> bool:
        """Set margin mode (isolated/cross) for futures."""
        if self.market_type != "futures":
            return True
        
        try:
            # CCXT unified method (exchange-specific)
            result = self.ex.set_margin_mode(mode, symbol)  # type: ignore[call-arg,attr-defined]
            log.debug(f"Set margin mode {mode} for {symbol}")
            return True
        except Exception as e:
            log.warning(f"Failed to set margin mode {mode} for {symbol}: {e}")
            # May need to be set manually on exchange UI
            return False
    
    def market_order(self, order: Order, leverage: Optional[int] = None) -> Optional[Fill]:
        """
        Execute a market order on the testnet exchange.
        
        For futures:
        - buy = open long or close short
        - sell = open short or close long
        - Leverage must be set beforehand (or manually on exchange)
        
        Returns Fill if successful, None if failed.
        """
        try:
            symbol = order.symbol
            
            # Set leverage if provided (futures only)
            if leverage is not None and self.market_type == "futures":
                self._set_leverage(symbol, leverage)
            
            # Execute order via CCXT
            result = self.ex.create_market_order(
                symbol=symbol,
                side=order.side,  # 'buy' or 'sell'
                amount=abs(order.qty),  # Always positive
            )
            
            log.info(f"Order executed on testnet: {order.side} {order.qty} {symbol} (order_id: {result.get('id', 'N/A')})")
            
            # Parse fill from exchange response
            price = float(result.get("price", 0) or 0)
            if price == 0:
                # Some exchanges don't return price in order response, fetch from fills
                fills = result.get("fills", [])
                if fills:
                    # Average fill price
                    total_cost = sum(float(f.get("cost", 0) or 0) for f in fills)
                    total_qty = sum(float(f.get("amount", 0) or 0) for f in fills)
                    price = total_cost / total_qty if total_qty > 0 else 0
            
            fee_cost = float(result.get("fee", {}).get("cost", 0) or 0) if isinstance(result.get("fee"), dict) else 0
            
            # Refresh portfolio after order
            time.sleep(0.5)  # Small delay for exchange to process
            self._refresh_portfolio()
            
            return Fill(
                order_id=str(result.get("id", order.id)),
                symbol=symbol,
                side=order.side,
                qty=order.qty,
                price=price,
                fee=fee_cost,
                timestamp=int(time.time() * 1000),
            )
        
        except Exception as e:
            log.error(f"Failed to execute order {order.id} on testnet: {e}")
            return None
    
    def equity(self, prices: Optional[Dict[str, float]] = None) -> float:
        """Get current equity from exchange."""
        portfolio = self.get_portfolio()
        return portfolio.equity

