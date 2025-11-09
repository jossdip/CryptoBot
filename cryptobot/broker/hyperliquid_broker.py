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
    # Build a signing wallet from a private key
    from eth_account import Account  # type: ignore
except Exception as _e:
    Account = None  # type: ignore[assignment]
try:
    from hyperliquid.info import Info as HyperliquidInfo  # type: ignore
except Exception:
    HyperliquidInfo = None  # type: ignore[assignment]
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
        # Build LocalAccount wallet as required by SDK:
        # Exchange.__init__(wallet: LocalAccount, base_url: Optional[str] = None, ..., account_address: Optional[str] = None, ...)
        if Account is None:
            raise RuntimeError("eth-account is missing. Please reinstall 'hyperliquid-python-sdk'.")
        try:
            # Clean potential surrounding quotes/whitespace
            pk = str(self.conn.private_key).strip().strip('"').strip("'")
            wallet_obj = Account.from_key(pk)  # LocalAccount
        except Exception as e:
            raise RuntimeError(f"Invalid Hyperliquid private key: {e}")
        # Warn if provided wallet address mismatches derived address
        try:
            if self.conn.wallet_address and self.conn.wallet_address.lower() != wallet_obj.address.lower():
                log.warning(
                    f"Provided wallet address {self.conn.wallet_address} differs from private key address {wallet_obj.address}. "
                    "Using the derived address for signing; API may still accept provided account_address."
                )
        except Exception:
            pass

        # Keep references for later (Info queries, etc.)
        self._wallet_obj = wallet_obj
        # Address used to sign transactions (API wallet / agent wallet)
        self.account_address = wallet_obj.address
        # Address to query portfolio/state on Hyperliquid (must be the main account address)
        # If a wallet_address was provided in config/.env, prefer it; otherwise fall back to signer address
        self.query_address = self.conn.wallet_address or self.account_address

        # Initialize client with wallet object and base_url; pass account_address for clarity
        try:
            self.client = HyperliquidClient(
                wallet_obj,
                base_url=self.conn.base_url,
                account_address=self.query_address,
            )
        except TypeError:
            # Fallback: without account_address
            self.client = HyperliquidClient(wallet_obj, base_url=self.conn.base_url)

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

        # Normalize symbol to Hyperliquid coin ticker (e.g., "BTC/USD:USD" -> "BTC")
        try:
            hl_symbol = self._normalize_symbol_for_hyperliquid(symbol)
        except Exception:
            hl_symbol = symbol

        # SDK specific call placeholders (actual field names/signatures depend on SDK)
        try:
            # Best-effort: attempt multiple call signatures depending on SDK variant
            is_buy = side.lower() == "buy"
            # Some SDKs require leverage to be set separately; attempt if available (best-effort)
            try:
                if hasattr(self.client, "update_leverage"):
                    # Typical signature: update_leverage(coin="BTC", leverage=5)
                    self.client.update_leverage(coin=hl_symbol, leverage=int(leverage))  # type: ignore[attr-defined]
            except Exception:
                pass

            # 1) Preferred explicit signature using positional args (common in HL SDK)
            if order_type == "market" and hasattr(self.client, "market_open"):
                try:
                    # Try positional form: market_open(coin, is_buy, sz)
                    response = self.client.market_open(hl_symbol, is_buy, float(size))  # type: ignore[misc]
                    log.debug(f"Hyperliquid market_open(positional) response: {response}")
                    return {"ok": True, "request": {"coin": hl_symbol, "is_buy": is_buy, "sz": float(size), "type": "market"}, "response": response, "ts": time.time()}
                except TypeError:
                    # Fallback to keyword form if positional fails in this SDK
                    try:
                        response = self.client.market_open(coin=hl_symbol, is_buy=is_buy, sz=float(size))  # type: ignore[attr-defined]
                        log.debug(f"Hyperliquid market_open(keyword) response: {response}")
                        return {"ok": True, "request": {"coin": hl_symbol, "is_buy": is_buy, "sz": float(size), "type": "market"}, "response": response, "ts": time.time()}
                    except Exception:
                        # Will fall through to generic paths
                        pass

            # 2) Generic place_order with coin/is_buy/sz/(limit_px)
            payload_generic: Dict[str, Any] = {
                "coin": hl_symbol,
                "is_buy": is_buy,
                "sz": float(size),
            }
            if order_type == "limit":
                if price is None:
                    raise ValueError("price is required for limit orders")
                payload_generic["limit_px"] = float(price)
                payload_generic["post_only"] = True
            response: Dict[str, Any] = {}
            try:
                response = self.client.place_order(**payload_generic)  # type: ignore[arg-type]
                log.debug(f"Hyperliquid place_order response: {response}")
                return {"ok": True, "request": payload_generic, "response": response, "ts": time.time()}
            except TypeError:
                # 3) Alternative generic: method name 'order' with positional args is used in some variants
                try:
                    if hasattr(self.client, "order"):
                        response = self.client.order(hl_symbol, is_buy, float(size))  # type: ignore[misc]
                        log.debug(f"Hyperliquid order(positional) response: {response}")
                        return {"ok": True, "request": {"coin": hl_symbol, "is_buy": is_buy, "sz": float(size), "type": order_type}, "response": response, "ts": time.time()}
                except Exception:
                    pass
                # 4) Final fallback to original payload names if SDK expects them
                payload: Dict[str, Any] = {
                    "symbol": hl_symbol,
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

                response = self.client.place_order(**payload)  # type: ignore[arg-type]
                log.debug(f"Hyperliquid fallback place_order response: {response}")
                return {"ok": True, "request": payload, "response": response, "ts": time.time()}
        except Exception as e:  # pragma: no cover - SDK runtime path
            log.error(f"Failed to place order on Hyperliquid: {e}")
            return {"ok": False, "error": str(e), "ts": time.time()}

    def _normalize_symbol_for_hyperliquid(self, symbol: str) -> str:
        """
        Map common external symbol formats to Hyperliquid coin tickers.
        Examples:
        - 'BTC/USD:USD' -> 'BTC'
        - 'ETH/USDT'    -> 'ETH'
        - 'SOL'         -> 'SOL' (unchanged)
        """
        s = str(symbol or "").strip().upper()
        if not s:
            return s
        # Split by '/' first, take the base asset part
        if "/" in s:
            base = s.split("/", 1)[0]
        else:
            base = s
        # Remove any suffix like ':USD'
        base = base.replace(":USD", "")
        # Final cleanup: keep only alphanumerics (HL tickers are uppercase coin names)
        return "".join(ch for ch in base if ch.isalnum())

    def _normalize_user_state(self, data: Any) -> Dict[str, Any]:
        """Best-effort normalization of Info.user_state payload into a common schema.
        Returns a dict with keys: balance, equity, unrealized_pnl, positions.
        """
        out: Dict[str, Any] = {"balance": 0.0, "equity": 0.0, "unrealized_pnl": 0.0, "positions": {}}

        def _dig_first_number(obj: Any, keys: tuple[str, ...]) -> Optional[float]:
            try:
                if isinstance(obj, dict):
                    for k in keys:
                        if k in obj:
                            try:
                                return float(obj[k])
                            except Exception:
                                pass
                    # Search nested dictionaries one level deep
                    for v in obj.values():
                        if isinstance(v, dict):
                            val = _dig_first_number(v, keys)
                            if val is not None:
                                return val
                return None
            except Exception:
                return None

        # Try common summary fields for equity / balance / unrealized PnL
        equity = _dig_first_number(data, ("equity", "accountValue", "totalAccountValue", "marginBalance", "account_value"))
        balance = _dig_first_number(data, ("cash", "availableMargin", "availableBalance", "balance", "withdrawable", "free"))
        unreal = _dig_first_number(data, ("unrealizedPnl", "totalUnrealizedPnl", "unrealized_pnl", "upnl"))

        if equity is not None:
            out["equity"] = float(equity)
        if balance is not None:
            out["balance"] = float(balance)
        if unreal is not None:
            out["unrealized_pnl"] = float(unreal)

        # Positions: look for common containers
        try:
            pos_container: Any = None
            for key in ("perpPositions", "openPositions", "positions", "positionsMap"):
                if isinstance(data, dict) and key in data:
                    pos_container = data[key]
                    break
            positions: Dict[str, Any] = {}
            if isinstance(pos_container, list):
                for p in pos_container:
                    if not isinstance(p, dict):
                        continue
                    sym = str(p.get("symbol") or p.get("coin") or "")
                    if not sym:
                        continue
                    qty_val = None
                    for qk in ("sz", "size", "qty", "positionSize", "contracts"):
                        if qk in p:
                            try:
                                qty_val = float(p[qk])
                                break
                            except Exception:
                                pass
                    if qty_val is None:
                        continue
                    avg_px = 0.0
                    for pk in ("entryPx", "avgEntry", "entryPrice", "avg_price"):
                        if pk in p:
                            try:
                                avg_px = float(p[pk])
                                break
                            except Exception:
                                pass
                    positions[sym] = {"symbol": sym, "qty": float(qty_val), "avg_price": float(avg_px)}
            elif isinstance(pos_container, dict):
                for sym, p in pos_container.items():
                    try:
                        qty_val = None
                        if isinstance(p, dict):
                            for qk in ("sz", "size", "qty", "positionSize", "contracts"):
                                if qk in p:
                                    qty_val = float(p[qk])
                                    break
                            avg_px = 0.0
                            for pk in ("entryPx", "avgEntry", "entryPrice", "avg_price"):
                                if pk in p:
                                    avg_px = float(p[pk])
                                    break
                        else:
                            avg_px = 0.0
                        if qty_val is not None:
                            positions[str(sym)] = {"symbol": str(sym), "qty": float(qty_val), "avg_price": float(avg_px)}
                    except Exception:
                        continue
            out["positions"] = positions
        except Exception:
            # Leave positions empty if parsing fails
            pass

        return out

    def get_portfolio(self) -> Dict[str, Any]:
        """Get current portfolio state: balances, positions, and PnL."""
        # Try multiple strategies depending on SDK version
        # 1) If Exchange exposes a portfolio-like API
        try:
            candidate = getattr(self.client, "get_portfolio", None)
            if callable(candidate):
                try:
                    response: Dict[str, Any] = candidate()  # type: ignore[assignment]
                    return {"ok": True, "response": response, "ts": time.time()}
                except Exception as e:
                    log.debug(f"Exchange.get_portfolio call failed: {e}")
        except Exception as e:
            log.debug(f"Exchange.get_portfolio not available: {e}")
        # 2) Use Info client user_state(address)
        try:
            if HyperliquidInfo is not None:
                info_client = None
                last_err: Optional[Exception] = None
                # Try a few constructor variants
                for args, kwargs in (
                    ((), {"base_url": self.conn.base_url}),
                    ((self.conn.base_url,), {}),
                    ((), {}),
                ):
                    try:
                        info_client = HyperliquidInfo(*args, **kwargs)  # type: ignore[misc]
                        break
                    except Exception as e:
                        last_err = e
                        continue
                if info_client is None:
                    raise last_err or RuntimeError("Failed to construct Info client")
                # Call user_state using the derived address (source of truth)
                query_addr = self.query_address
                for call in (
                    lambda: info_client.user_state(query_addr),  # type: ignore[attr-defined]
                    lambda: info_client.user_state(address=query_addr),  # type: ignore[attr-defined]
                ):
                    try:
                        raw = call()
                        normalized = self._normalize_user_state(raw)
                        # Include raw payload for debugging/diagnostics
                        return {"ok": True, "response": normalized, "raw": raw, "ts": time.time()}
                    except Exception as e:
                        last_err = e
                        continue
                raise last_err or RuntimeError("user_state unavailable")
        except Exception as e:
            log.error(f"Failed to fetch portfolio from Hyperliquid: {e}")
            return {"ok": False, "error": str(e), "ts": time.time()}
        # 3) Fallback: not available
        return {"ok": False, "error": "Portfolio API not available in this SDK", "ts": time.time()}

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


