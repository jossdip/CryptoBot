from __future__ import annotations

import asyncio
import time
import logging
from typing import Any, Dict, Literal, Optional

import aiohttp
from eth_account import Account
from eth_account.signers.local import LocalAccount

# Attempt to import signing utils from installed SDK
try:
    from hyperliquid.utils.signing import sign_l1_action, get_timestamp_ms
except ImportError:
    sign_l1_action = None
    get_timestamp_ms = lambda: int(time.time() * 1000)

from cryptobot.core.logging import get_logger

logger = get_logger()

class AsyncExecutionClient:
    """
    Low-latency async HTTP client for Hyperliquid execution.
    Directly signs and posts orders to /exchange endpoint, bypassing SDK overhead.
    """

    def __init__(
        self,
        wallet_address: str,
        private_key: str,
        testnet: bool = True,
    ):
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.testnet = testnet
        self.base_url = (
            "https://api.hyperliquid-testnet.xyz"
            if testnet
            else "https://api.hyperliquid.xyz"
        )
        
        # Init wallet
        try:
            clean_pk = str(private_key).strip().strip('"').strip("'")
            self.wallet: LocalAccount = Account.from_key(clean_pk)
        except Exception as e:
            logger.error(f"Failed to init wallet in AsyncClient: {e}")
            self.wallet = None

        self.session: Optional[aiohttp.ClientSession] = None
        self.asset_map: Dict[str, int] = {} # symbol -> asset_id
        self._map_lock = asyncio.Lock()

    async def start(self):
        """Initialize session and fetch asset map."""
        if not self.session:
            # TCPConnector with keepalive and fast timeouts
            # ttl_dns_cache helps avoid DNS lookups on every request
            conn = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300, keepalive_timeout=60)
            self.session = aiohttp.ClientSession(
                connector=conn,
                headers={"Content-Type": "application/json"}
            )
            await self._fetch_asset_map()

    async def stop(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def refresh_assets(self):
        """Public method to refresh asset map."""
        await self._fetch_asset_map()

    async def _fetch_asset_map(self):
        """Fetch universe to map symbols to asset IDs."""
        if not self.session:
            return
        
        try:
            url = f"{self.base_url}/info"
            payload = {"type": "meta"}
            async with self.session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # data['universe'] is list of {name: "BTC", szDecimals: ...}
                    # The index in the universe list is the asset ID
                    universe = data.get("universe", [])
                    async with self._map_lock:
                        self.asset_map = {asset["name"]: idx for idx, asset in enumerate(universe)}
                    logger.info(f"AsyncClient: Mapped {len(self.asset_map)} assets.")
                else:
                    logger.warning(f"AsyncClient: Failed to fetch meta: {resp.status}")
        except Exception as e:
            logger.error(f"Failed to fetch asset map: {e}")

    async def get_asset_id(self, symbol: str) -> Optional[int]:
        # Normalize symbol for Hyperliquid (e.g. BTC, ETH)
        s = symbol.replace("/", "").replace("USDT", "").replace("USD", "").split(":")[0].upper()
        
        async with self._map_lock:
            if not self.asset_map:
                # Will be fetched on start, but retry if empty
                pass 
            return self.asset_map.get(s)

    async def place_order(
        self,
        symbol: str,
        is_buy: bool,
        size: float,
        limit_px: float,
        order_type: Literal["limit", "market"] = "limit",
        reduce_only: bool = False,
        cloid: Optional[str] = None,
        post_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Sign and place an order.
        """
        if not self.session:
            await self.start()
            
        asset_id = await self.get_asset_id(symbol)
        if asset_id is None:
            # Try one refresh
            await self._fetch_asset_map()
            asset_id = await self.get_asset_id(symbol)
            if asset_id is None:
                return {"ok": False, "error": f"Unknown symbol {symbol}"}

        # Construct Order Wire Format
        # Price/Size formatting: simple string conversion, caller should quantize
        
        # Order Type logic
        # Limit: { "limit": { "tif": "Gtc" } }
        # Market: { "limit": { "tif": "Ioc" } } with aggressive price
        # Post-Only: { "limit": { "tif": "Alo" } }
        
        tif = "Gtc"
        if order_type == "market":
            tif = "Ioc"
            # Note: Ensure limit_px is aggressive enough for market buy/sell
        elif post_only:
            tif = "Alo"
        
        order_wire = {
            "a": asset_id,
            "b": is_buy,
            "p": str(limit_px),
            "s": str(size),
            "r": reduce_only,
            "t": {"limit": {"tif": tif}}, 
        }
        
        if cloid:
            order_wire["c"] = cloid

        action = {
            "type": "order",
            "orders": [order_wire],
            "grouping": "na",
        }

        nonce = get_timestamp_ms()
        
        if not sign_l1_action:
             return {"ok": False, "error": "Signing utils missing"}
             
        signature = sign_l1_action(
            self.wallet,
            action,
            None, # active_asset_data_oid
            nonce,
            not self.testnet # is_mainnet (True if live)
        )
        
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
        }

        start_t = time.perf_counter()
        try:
            url = f"{self.base_url}/exchange"
            async with self.session.post(url, json=payload) as resp:
                latency = (time.perf_counter() - start_t) * 1000
                if resp.status == 200:
                    data = await resp.json()
                    # Check "status" in response data
                    return {"ok": True, "response": data, "latency_ms": latency}
                else:
                    text = await resp.text()
                    return {"ok": False, "status": resp.status, "error": text, "latency_ms": latency}
        except Exception as e:
            return {"ok": False, "error": str(e)}

