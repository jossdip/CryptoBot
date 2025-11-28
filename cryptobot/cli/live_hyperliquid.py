from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import signal
import threading
from typing import Dict, Any, Optional

from loguru import logger as log
from dotenv import load_dotenv

from cryptobot.core.config import AppConfig
from cryptobot.broker.hyperliquid_broker import HyperliquidBroker
from cryptobot.strategy.volatility_breakout import VolatilityBreakoutStrategy
from cryptobot.data.context_aggregator import MarketContextAggregator
from cryptobot.core.logging import setup_logging, get_logger
from cryptobot.core.env import load_local_environment

try:
    import uvloop
except ImportError:
    uvloop = None

# Mock Broker for Testing
class MockBroker:
    def get_account_value(self):
        return 10000.0
    
    def get_portfolio(self):
        return {}
    
    async def place_order_async(self, *args, **kwargs):
        return {"ok": True, "response": {"filled": {"totalSz": kwargs.get("size", 0)}}}

class SmartBot:
    def __init__(self, config_path: str = "configs/live.hyperliquid.yaml", mock: bool = False, stop_event: Optional[threading.Event] = None):
        self.mock = mock
        self.running = True
        self.stop_event = stop_event
        
        # Load Config
        self.config = AppConfig.load(config_path)
        self.config_data = self.config.model_dump()
            
        self.symbols = self.config.general.symbols
        self.interval = self.config.llm.decision_interval_sec
        
        # Setup Components
        self._setup_broker()
        self.aggregator = MarketContextAggregator(
            broker=self.broker,
            config=self.config
        )
        self.strategy = VolatilityBreakoutStrategy(
            broker=self.broker,
            config=self.config_data["strategy"]["params"]
        )
        
        # Signals handled by caller or loop

    def _setup_broker(self):
        hl_conf = self.config.hyperliquid
        
        if self.mock:
            log.info("INITIALIZING IN MOCK MODE")
            self.broker = MockBroker()
            return

        try:
            self.broker = HyperliquidBroker(
                wallet_address=os.getenv("HYPERLIQUID_WALLET_ADDRESS", hl_conf.wallet_address),
                private_key=os.getenv("HYPERLIQUID_PRIVATE_KEY", hl_conf.private_key),
                testnet=hl_conf.testnet
            )
            log.info("Hyperliquid Broker Initialized")
        except Exception as e:
            log.error(f"Failed to init broker: {e}")
            if not self.mock:
                raise

    async def run(self):
        log.info(f"Starting Smart Breakout Bot on {len(self.symbols)} symbols: {self.symbols}")
        
        while self.running:
            if self.stop_event and self.stop_event.is_set():
                log.info("Stop event received. Exiting loop.")
                break

            try:
                start_time = time.time()
                
                # 1. Collect Market Context
                log.info("Collecting market context...")
                
                # Build base context (prices, sentiment, etc)
                context = await asyncio.to_thread(self.aggregator.build_context, self.symbols)
                
                # Attach Candles for Strategy (5m timeframe as per config/strategy)
                timeframe = self.config.general.timeframe
                candles = await asyncio.to_thread(self.aggregator.get_candles, self.symbols, timeframe=timeframe)
                context["market"]["candles"] = candles
                
                # 2. Run Strategy
                log.info("Scanning for opportunities...")
                opportunities = self.strategy.detect_opportunities(context)
                
                if not opportunities:
                    log.info("No opportunities detected.")
                
                # 3. Execute Signals
                for opp in opportunities:
                    log.info(f"EXECUTING: {opp}")
                    await self.execute_opportunity(opp)
                
                # Sleep remainder of interval
                elapsed = time.time() - start_time
                # --- SPEED FIX: FORCE 15 SECONDS MAX ---
                target_interval = 15.0 
                sleep_time = max(1.0, target_interval - elapsed)
                log.info(f"Sleeping {sleep_time:.1f}s...")
                
                # interruptible sleep
                for _ in range(int(sleep_time)):
                    if self.stop_event and self.stop_event.is_set():
                        return
                    await asyncio.sleep(1)
                await asyncio.sleep(sleep_time % 1)
                
            except Exception as e:
                log.error(f"Error in main loop: {e}")
                await asyncio.sleep(10)

    async def execute_opportunity(self, opp: Dict[str, Any]):
        """
        Execute the trade via Broker.
        """
        symbol = opp["symbol"]
        direction = opp["direction"]
        confidence = opp["confidence"]
        
        # Calculate sizing
        if self.mock:
            capital = 10000.0
        else:
            try:
                pf = self.broker.get_portfolio()
                capital = float(pf.get("response", {}).get("equity", 100.0))
            except Exception:
                capital = 100.0

        # --- GUERRILLA SIZING FIX ---
        # Mode "Small Account" (< 500€) : On veut de la croissance, pas de la préservation.
        # On risque 10% du capital sur ce trade. Si le SL touche, on perd 10€.
        risk_pct_per_trade = 0.10 
        stop_loss_pct = self.config.strategy.params.get("stop_loss_pct", 0.02) # ex: 2%

        risk_amount_usd = capital * risk_pct_per_trade
        
        # Formule magique du levier : Taille = Risque / SL%
        # Ex: 10€ risque / 2% SL = 500€ de position (Levier 5x effectif)
        size_usd = risk_amount_usd / stop_loss_pct
        
        # HARD CAP : Max 20x levier pour ne pas se faire liquider par le moteur d'échange
        max_buying_power = capital * 20.0 * 0.95
        if size_usd > max_buying_power:
            size_usd = max_buying_power
            log.warning(f"Size capped by max leverage: {size_usd:.2f}")
        
        leverage = self.config.hyperliquid.default_leverage
        
        log.info(f"GUERRILLA SIZING: Capital ${capital:.1f} | Risk ${risk_amount_usd:.1f} | Size ${size_usd:.1f} (Levier effectif: {size_usd/capital:.1f}x)")
        
        if self.mock:
            log.success(f"[MOCK] Order Placed: {symbol} {direction}")
            return

        # Real Execution
        try:
            is_buy = (direction == "long")
            
            # Calculate size in coins
            price = opp.get("current_price", 0.0)
            if price <= 0:
                log.error("Invalid price for execution, skipping")
                return

            size_coin = size_usd / price
            
            log.info(f"Sending order to Hyperliquid: {symbol} {direction.upper()} {size_coin:.4f} @ Market (approx ${price:.2f})")
            
            await self.broker.place_order_async(
                symbol=symbol,
                side="buy" if is_buy else "sell",
                size=size_coin,
                leverage=leverage,
                order_type="market",
                stop_loss=stop_loss_pct,
                take_profit=None 
            )
            log.success(f"Order Executed: {symbol}")
        
        except Exception as e:
            log.error(f"Execution Failed: {e}")


def run_live(config_path: str, stop_event: Optional[threading.Event] = None, mock: bool = False) -> bool:
    """Entry point wrapper."""
    load_local_environment()
    setup_logging(level="INFO")
    
    try:
        if uvloop:
            uvloop.install()
            get_logger().info("uvloop activated")
            
        bot = SmartBot(config_path=config_path, mock=mock, stop_event=stop_event)
        asyncio.run(bot.run())
        return True
    except KeyboardInterrupt:
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Breakout Bot Runner")
    parser.add_argument("--config", type=str, default="configs/live.hyperliquid.yaml")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode")
    args = parser.parse_args()
    
    run_live(args.config, mock=args.mock)

if __name__ == "__main__":
    main()
