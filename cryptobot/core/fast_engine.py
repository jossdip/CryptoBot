from __future__ import annotations

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from cryptobot.core.logging import get_logger
from cryptobot.broker.fast_client import AsyncExecutionClient

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
    def __init__(self, broker, strategies: List[Any] = None, symbols: List[str] = None, performance_tracker: Any = None):
        self.broker = broker
        self.strategies = strategies or []
        self.symbols = symbols or ["BTC", "ETH", "SOL"]
        self.performance_tracker = performance_tracker
        self.params = FastPathParams()
        self.running = False
        self.tasks: List[asyncio.Task] = []
        self._params_lock = asyncio.Lock()
        self.logger = get_logger()
        
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

    async def start(self):
        """Start the event-driven engine."""
        if self.running:
            return
        self.running = True
        self.logger.info("FastEngine starting (HFT Mode)...")
        
        # Start Fast Client
        await self.fast_client.start()

        # Create tasks
        self.tasks = [
            asyncio.create_task(self._market_data_loop(), name="market_data"),
            asyncio.create_task(self._risk_loop(), name="risk"),
        ]

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
                # Direct Strategy Trigger
                for strat in self.strategies:
                    # Returns None or signal dict
                    signal = strat.process_tick(coin, payload)
                    if signal:
                        # Fire and forget execution task to not block WS reader
                        asyncio.create_task(self.execute_signal(signal))
                        
        except Exception as e:
            pass # Suppress errors in critical path to keep running

    async def execute_signal(self, signal: Dict[str, Any]):
        """
        Execute signal via Fast Client.
        signal: { symbol, side, size, limit_px, ... }
        """
        try:
            symbol = signal.get("symbol")
            direction = signal.get("direction", "flat")
            if direction == "flat":
                return
                
            is_buy = (direction == "long")
            price = signal.get("price")
            
            # Sizing (TODO: Dynamic Kelly)
            size_usd = 100.0 
            size = size_usd / price
            
            # Execute with Fast Client
            res = await self.fast_client.place_order(
                symbol=symbol,
                is_buy=is_buy,
                size=size,
                limit_px=price,
                order_type="limit" if signal.get("is_maker") else "market"
            )
            
            if res.get("ok"):
                self.logger.info(f"HFT EXECUTION: {symbol} {direction} @ {price} | Latency: {res.get('latency_ms'):.2f}ms")
                # TODO: Bracket orders (Post-execution)
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
            await asyncio.sleep(1)
            # TODO: PnL checks
