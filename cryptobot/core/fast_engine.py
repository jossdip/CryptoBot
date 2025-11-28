from __future__ import annotations

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from cryptobot.core.logging import get_logger
from cryptobot.broker.fast_client import AsyncExecutionClient
from cryptobot.broker.risk import RiskManager
from cryptobot.core.config import RiskConfig
from cryptobot.data.ccxt_live import fetch_mark_price

logger = get_logger()

@dataclass
class FastPathParams:
    """
    Parameters for the Fast Path engine, updated by the Slow Path (LLM).
    """
    # Global
    enabled: bool = True
    max_leverage: int = 5
    max_positions: int = 3
    
    # Strategy: Microstructure
    scalping_enabled: bool = True
    min_obi: float = 0.3      # Order Book Imbalance threshold
    min_spread_bps: float = 2.0
    
    # Risk
    stop_loss_pct: float = 0.01
    take_profit_pct: float = 0.015
    max_drawdown_pct: float = 0.02


class FastEngine:
    """
    Event-Driven High-Frequency Execution Engine.
    Eliminates polling loops; triggers logic directly on WebSocket events.
    """
    def __init__(self, broker, strategies: List[Any] = None, symbols: List[str] = None, performance_tracker: Any = None, risk_config: Optional[RiskConfig] = None):
        self.broker = broker
        self.strategies = strategies or []
        self.symbols = symbols or ["BTC", "ETH", "SOL"]
        self.performance_tracker = performance_tracker
        self.params = FastPathParams()
        self.running = False
        self.tasks: List[asyncio.Task] = []
        self._params_lock = asyncio.Lock()
        self.logger = get_logger()
        
        # Risk Management
        # Default to conservative config if none provided
        if risk_config is None:
            # Basic defaults
            risk_config = RiskConfig(max_position_pct=0.1, max_drawdown_pct=0.05)
        self.risk_manager = RiskManager(risk_config)
        self.equity = 0.0 # Cached equity
        self.positions_cache: Dict[str, float] = {} # Cached positions by symbol
        self.price_cache: Dict[str, float] = {} # Cached prices
        
        # Initialize Low-Latency Client
        self.fast_client = AsyncExecutionClient(
            wallet_address=broker.conn.wallet_address,
            private_key=broker.conn.private_key,
            testnet=broker.conn.testnet
        )

    async def update_params(self, new_params: Dict[str, Any]):
        """Called by Slow Path to update runtime parameters."""
        async with self._params_lock:
            for k, v in new_params.items():
                if hasattr(self.params, k):
                    setattr(self.params, k, v)
            # Update strategies
            for strat in self.strategies:
                if hasattr(strat, 'params'):
                    strat.params = self.params
            self.logger.info(f"FastEngine params updated: {new_params}")

    async def add_symbol(self, symbol: str):
        """Dynamically add a symbol to monitoring."""
        if symbol in self.symbols:
            return
        self.logger.info(f"FastEngine: Adding new symbol {symbol}")
        self.symbols.append(symbol)
        
        # Do not cancel the market data loop.
        # We assume the broker's subscription can be updated or the loop picks up the change
        # on next iteration/reconnect if implemented that way.
        # If the broker requires explicit subscription, we inject it here.
        if hasattr(self.broker, "subscribe_symbol"):
             await self.broker.subscribe_symbol(symbol)
        elif hasattr(self.broker, "update_subscriptions"):
             await self.broker.update_subscriptions(self.symbols)
        else:
            self.logger.info(f"Symbol {symbol} added to list. Waiting for next update cycle.")

    async def start(self):
        """Start the event-driven engine."""
        if self.running:
            return
        self.running = True
        self.logger.info("FastEngine starting (HFT Mode)...")
        
        # Start Fast Client
        await self.fast_client.start()
        
        # Inject dependencies into strategies
        for strat in self.strategies:
            if hasattr(strat, "set_fast_client"):
                strat.set_fast_client(self.fast_client)
            if hasattr(strat, "set_engine"):
                strat.set_engine(self)

        # Initial Equity Sync
        try:
            pf = await self.broker.get_portfolio_async()
            if pf.get("ok"):
                self.equity = float(pf.get("response", {}).get("equity", 0.0))
                self.logger.info(f"Initial Equity: {self.equity}")
        except Exception as e:
            self.logger.warn(f"Could not fetch initial equity: {e}")

        # Create tasks
        self.tasks = [
            asyncio.create_task(self._market_data_loop(), name="market_data"),
            asyncio.create_task(self._risk_loop(), name="risk"),
        ]

        # Add strategy background tasks
        for strat in self.strategies:
            if hasattr(strat, "get_tasks"):
                strat_tasks = await strat.get_tasks()
                for t in strat_tasks:
                    if asyncio.iscoroutine(t):
                        self.tasks.append(asyncio.create_task(t))
                    else:
                         self.tasks.append(t)

    async def stop(self):
        """Stop the engine."""
        self.running = False
        self.logger.info("FastEngine stopping...")
        await self.fast_client.stop()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []

    async def on_market_data(self, data: Dict[str, Any]):
        """
        CRITICAL PATH: Handle WS updates.
        Triggers strategy logic immediately.
        """
        if not self.params.enabled:
            return

        try:
            channel = data.get("channel")
            # payload: { coin: BTC, levels: [[bids], [asks]], ... }
            payload = data.get("data", {})
            
            if channel == "l2Book":
                coin = payload.get("coin")
                # Update Price Cache
                levels = payload.get("levels")
                if levels and len(levels) == 2:
                    bids = levels[0]
                    asks = levels[1]
                    if bids and asks:
                        try:
                            mid = (float(bids[0]['px']) + float(asks[0]['px'])) / 2.0
                            self.price_cache[coin] = mid
                        except Exception:
                            pass

                # Direct Strategy Trigger
                current_position = self.positions_cache.get(coin, 0.0)
                
                for strat in self.strategies:
                    # Returns None or signal object
                    signal = strat.process_tick(coin, payload, current_position)
                    if signal:
                        # Fire and forget execution task to not block WS reader
                        asyncio.create_task(self.execute_signal(signal))
                        
        except Exception as e:
            pass # Suppress errors in critical path to keep running

    async def inject_signal(self, signal: Any):
        """
        External Signal Injection (e.g. News Monitor).
        """
        self.logger.info(f"FastEngine: Received external signal for {signal.symbol}")
        
        # Ensure we are monitoring this symbol if possible
        if signal.symbol not in self.symbols:
             await self.add_symbol(signal.symbol)

        # Ensure price is set for sizing
        if signal.price <= 0:
            if signal.symbol in self.price_cache:
                signal.price = self.price_cache[signal.symbol]
            else:
                # Fetch fallback
                try:
                    # Attempt to fetch mark price via CCXT (Hyperliquid or Binance as fallback)
                    price = await asyncio.to_thread(fetch_mark_price, "hyperliquid", signal.symbol)
                    if not price:
                         price = await asyncio.to_thread(fetch_mark_price, "binance", signal.symbol)
                    
                    if price:
                        signal.price = price
                    else:
                        self.logger.warn(f"Could not determine price for {signal.symbol}, skipping inject.")
                        return
                except Exception as e:
                     self.logger.error(f"Price fetch failed for {signal.symbol}: {e}")
                     return

        # Force execute
        await self.execute_signal(signal)

    async def execute_signal(self, signal: Any):
        """
        Execute signal via Fast Client.
        signal: Signal object (dataclass)
        """
        try:
            symbol = signal.symbol
            direction = signal.direction
            if direction == "flat":
                return
                
            is_buy = (direction == "long")
            price = signal.price
            confidence = signal.confidence
            
            # Dynamic Sizing via Risk Manager
            # We use the cached equity.
            current_equity = self.equity
            if current_equity <= 0:
                # Fallback if equity not yet synced - DO NOT TRADE
                self.logger.warn("Skipping execution: Equity not synced (0.0).")
                return 
            
            # Get size in COIN units
            # Check metadata for specific sizing instructions
            meta = getattr(signal, "metadata", {}) or {}
            position_pct = meta.get("position_pct", 0.0)
            
            if position_pct > 0:
                # Use specific percentage from signal
                usd_size = current_equity * position_pct
                # Optional: cap by max_usd if present
                max_usd = meta.get("max_usd", 0.0)
                if max_usd > 0:
                     usd_size = min(usd_size, max_usd)
                
                size = usd_size / price
            else:
                 # Default Risk Manager Logic
                size = self.risk_manager.calculate_dynamic_size(
                    equity=current_equity,
                    price=price,
                    confidence=confidence,
                    tp_pct=self.params.take_profit_pct,
                    sl_pct=self.params.stop_loss_pct
                )
            
            if size <= 0:
                return

            # Default to Limit orders (Maker) for scalping
            # Use Post-Only to ensure rebate
            order_type = "limit"
            post_only = True
            
            # If confidence is extremely high (>0.9), maybe take liquidity?
            if confidence > 0.9:
                order_type = "market"
                post_only = False

            # Execute with Fast Client
            # Note: AsyncExecutionClient needs update to support post_only if not already
            # We pass it in kwargs or explicit arg if supported
            res = await self.fast_client.place_order(
                symbol=symbol,
                is_buy=is_buy,
                size=size,
                limit_px=price,
                order_type=order_type,
                post_only=post_only 
            )
            
            if res.get("ok"):
                self.logger.info(f"HFT EXECUTION: {symbol} {direction} @ {price} | Size: {size:.4f} | Latency: {res.get('latency_ms'):.2f}ms")
                # TODO: Bracket orders (Post-execution) handled by local bracket manager or exchange
            else:
                self.logger.warn(f"HFT Exec Failed: {res.get('error')}")
                
        except Exception as e:
            self.logger.error(f"Execution error: {e}")

    async def _market_data_loop(self):
        """Consume Websocket feeds."""
        self.logger.info("Market Data loop started")
        while self.running:
            try:
                # Uses broker's WS connection but directs callbacks to self.on_market_data
                await self.broker.listen_market_updates(self.symbols, self.on_market_data)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in market data loop: {e}")
                await asyncio.sleep(5)

    async def _risk_loop(self):
        """Monitoring loop (Non-critical path)."""
        while self.running:
            try:
                # Sync equity every minute
                pf = await self.broker.get_portfolio_async()
                if pf.get("ok"):
                    resp = pf.get("response", {})
                    equity = float(resp.get("equity", 0.0))
                    if equity > 0:
                        self.equity = equity
                    
                    # Update positions cache
                    positions = resp.get("positions", {})
                    new_cache = {}
                    if isinstance(positions, list):
                        # Handle list format if necessary, though broker normalizes to dict usually
                        for p in positions:
                            sym = p.get("symbol") or p.get("coin")
                            qty = float(p.get("qty") or p.get("size", 0.0))
                            if sym:
                                new_cache[sym] = qty
                    elif isinstance(positions, dict):
                        for sym, p in positions.items():
                            qty = float(p.get("qty", 0.0))
                            new_cache[sym] = qty
                    self.positions_cache = new_cache

                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Risk loop error: {e}")
                await asyncio.sleep(10)
