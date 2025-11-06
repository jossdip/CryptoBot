from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Literal, Any

import os
import time

from loguru import logger as log

try:  # optional dependency; only required when using Hyperliquid live
    # Prefer official SDK import path from 'hyperliquid-python-sdk'
    from hyperliquid.exchange import Exchange as HyperliquidClient  # type: ignore
except Exception as _e:  # pragma: no cover - import is optional
    HyperliquidClient = None  # type: ignore[assignment]
    _HL_IMPORT_ERR = _e  # type: ignore[assignment]
try:
    # Chain is optional; use if available to signal testnet/mainnet
    from hyperliquid.info import Chain as _HLChain  # type: ignore
except Exception:
    _HLChain = None  # type: ignore[assignment]


@dataclass
class HyperliquidConnection:
    base_url: str
    wallet_address: str
    private_key: str
    testnet: bool


class HyperliquidBroker:
    """
    Thin wrapper around Hyperliquid Python SDK for perpetual futures trading.

    Features:
    - Testnet/live switching via base_url selection
    - Market/limit order placement, with optional stop-loss
    - Portfolio snapshot (balances, positions)
    - Funding rate lookup
    - Prepared for WebSocket-based updates (future enhancement)
    """

    def __init__(
        self,
        wallet_address: str,
        private_key: str,
        testnet: bool = True,
        market_type: Literal["perpetual"] = "perpetual",
    ) -> None:
        if market_type != "perpetual":
            raise ValueError("HyperliquidBroker currently supports only perpetual markets")

        base_url = (
            os.getenv("HYPERLIQUID_TESTNET_URL", "https://api.hyperliquid-testnet.xyz")
            if testnet
            else os.getenv("HYPERLIQUID_LIVE_URL", "https://api.hyperliquid.xyz")
        )

        if HyperliquidClient is None:
            raise RuntimeError(
                "Hyperliquid Python SDK is not installed. Please install 'hyperliquid-python-sdk'."
            )

        self.conn = HyperliquidConnection(
            base_url=base_url,
            wallet_address=wallet_address,
            private_key=private_key,
            testnet=testnet,
        )
        # SDK signatures vary by version; try several known combinations
        client = None
        last_error: Exception | None = None
        chain_arg = None
        if _HLChain is not None:
            chain_arg = _HLChain.Testnet if self.conn.testnet else _HLChain.Mainnet
        attempts: list[tuple[str, tuple, dict]] = []
        if chain_arg is not None:
            attempts.extend([
                ("pos", (self.conn.wallet_address, self.conn.private_key), {"chain": chain_arg}),
                ("kw", (), {"account_address": self.conn.wallet_address, "secret_key": self.conn.private_key, "chain": chain_arg}),
                ("pos", (self.conn.wallet_address, self.conn.private_key), {"base_url": self.conn.base_url, "chain": chain_arg}),
                ("kw", (), {"account_address": self.conn.wallet_address, "secret_key": self.conn.private_key, "base_url": self.conn.base_url, "chain": chain_arg}),
            ])
        attempts.extend([
            ("pos", (self.conn.wallet_address, self.conn.private_key), {"base_url": self.conn.base_url}),
            ("kw", (), {"account_address": self.conn.wallet_address, "secret_key": self.conn.private_key, "base_url": self.conn.base_url}),
            ("pos", (self.conn.wallet_address, self.conn.private_key), {}),
            ("kw", (), {"account_address": self.conn.wallet_address, "secret_key": self.conn.private_key}),
        ])
        for mode, args, kwargs in attempts:
            try:
                if mode == "pos":
                    client = HyperliquidClient(*args, **kwargs)  # type: ignore[misc]
                else:
                    client = HyperliquidClient(**kwargs)  # type: ignore[misc]
                break
            except TypeError as e:
                last_error = e
                continue
            except Exception as e:
                last_error = e
                continue
        if client is None:
            raise RuntimeError(f"Failed to initialize Hyperliquid Exchange client. Last error: {last_error}")
        self.client = client

        log.info(
            f"Initialized HyperliquidBroker (testnet={self.conn.testnet}) at {self.conn.base_url}"
        )

    def place_order(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        size: float,
        leverage: int = 5,
        order_type: Literal["market", "limit"] = "market",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        client_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute order on Hyperliquid.

        Returns a structured dict with order identifiers and status.
        """
        if leverage < 1 or leverage > 50:
            raise ValueError("leverage must be within 1..50 for Hyperliquid")

        # SDK specific call placeholders (actual field names depend on SDK)
        try:
            payload: Dict[str, Any] = {
                "symbol": symbol,
                "side": side,
                "size": float(size),
                "type": order_type,
                "leverage": int(leverage),
            }
            if order_type == "limit":
                if price is None:
                    raise ValueError("price is required for limit orders")
                payload["price"] = float(price)
            if stop_loss is not None:
                payload["stop_loss"] = float(stop_loss)
            if take_profit is not None:
                payload["take_profit"] = float(take_profit)
            if client_id:
                payload["client_id"] = client_id

            # Example: response = self.client.place_order(**payload)
            # As SDK specifics may differ, keep a generic call with best effort
            response: Dict[str, Any] = self.client.place_order(**payload)  # type: ignore[arg-type]

            log.debug(f"Hyperliquid order response: {response}")
            return {
                "ok": True,
                "request": payload,
                "response": response,
                "ts": time.time(),
            }
        except Exception as e:  # pragma: no cover - SDK runtime path
            log.error(f"Failed to place order on Hyperliquid: {e}")
            return {"ok": False, "error": str(e), "ts": time.time()}

    def get_portfolio(self) -> Dict[str, Any]:
        """Get current portfolio state: balances, positions, and PnL."""
        try:
            # response = self.client.get_portfolio()
            response: Dict[str, Any] = self.client.get_portfolio()  # type: ignore[assignment]
            return {
                "ok": True,
                "response": response,
                "ts": time.time(),
            }
        except Exception as e:  # pragma: no cover - SDK runtime path
            log.error(f"Failed to fetch portfolio from Hyperliquid: {e}")
            return {"ok": False, "error": str(e), "ts": time.time()}

    def get_funding_rate(self, symbol: str) -> float:
        """Return current funding rate for a symbol (% per funding interval)."""
        try:
            # rate_info = self.client.get_funding_rate(symbol=symbol)
            rate_info: Dict[str, Any] = self.client.get_funding_rate(symbol=symbol)  # type: ignore[assignment]
            # Best effort extraction
            for k in ("rate", "fundingRate", "current"):
                if k in rate_info:
                    return float(rate_info[k])
            return 0.0
        except Exception:  # pragma: no cover - SDK runtime path
            return 0.0


