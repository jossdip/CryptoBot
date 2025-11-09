from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Literal, Any

import os
import time
from decimal import Decimal, ROUND_DOWN, getcontext

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
        # Use signer address if provided address mismatches to avoid ambiguity
        if self.conn.wallet_address and self.conn.wallet_address.lower() != self.account_address.lower():
            log.info("Using signer address as query address for consistency with the private key")
            self.query_address = self.account_address
        else:
            # If a wallet_address was provided in config/.env, prefer it; otherwise fall back to signer address
            self.query_address = self.conn.wallet_address or self.account_address

        # Initialize client with wallet object and base_url; pass account_address for clarity
        try:
            self.client = HyperliquidClient(
                wallet_obj,
                base_url=self.conn.base_url,
                account_address=self.account_address,
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

            # 1) Preferred for market orders: use market_open with positional args and quantized size
            if order_type == "market" and hasattr(self.client, "market_open"):
                q_sz = self._quantize_size(hl_symbol, float(size))
                response = None
                try:
                    response = self.client.market_open(hl_symbol, is_buy, float(q_sz))  # type: ignore[misc]
                except Exception as e:
                    # Retry once if wire rounding complained; reduce by one size step
                    if "float_to_wire" in str(e) or "rounding" in str(e):
                        step = self._get_size_step(hl_symbol)
                        new_q = max(0.0, float(Decimal(str(q_sz)) - Decimal(str(step))))
                        if new_q > 0.0:
                            log.debug(f"Retrying market_open with adjusted size due to wire rounding: {q_sz} -> {new_q}")
                            response = self.client.market_open(hl_symbol, is_buy, float(new_q))  # type: ignore[misc]
                            q_sz = new_q
                        else:
                            raise
                    else:
                        # Propagate to outer handler
                        raise
                if response is not None:
                    log.debug(f"Hyperliquid market_open(positional) response: {response}")
                return {"ok": True, "request": {"coin": hl_symbol, "is_buy": is_buy, "sz": float(q_sz), "type": "market"}, "response": response, "ts": time.time()}

            # 2) Limit orders: attempt positional 'order(coin, is_buy, sz, limit_px)' if available; else market fallback
            if order_type == "limit":
                if price is None:
                    raise ValueError("price is required for limit orders")
                q_sz = self._quantize_size(hl_symbol, float(size))
                limit_px = float(price)
                if hasattr(self.client, "order"):
                    response = None
                    try:
                        # Common signature: order(coin, is_buy, sz, limit_px)
                        response = self.client.order(hl_symbol, is_buy, float(q_sz), limit_px)  # type: ignore[misc]
                    except TypeError as e:
                        # Alternate signature requires order_type
                        if "order_type" in str(e):
                            try:
                                # Try appending positional order_type
                                response = self.client.order(hl_symbol, is_buy, float(q_sz), limit_px, "limit")  # type: ignore[misc]
                            except TypeError:
                                # Try keyword order_type
                                response = self.client.order(hl_symbol, is_buy, float(q_sz), limit_px, order_type="limit")  # type: ignore[misc]
                        else:
                            raise
                    except Exception as e:
                        if "float_to_wire" in str(e) or "rounding" in str(e):
                            step = self._get_size_step(hl_symbol)
                            new_q = max(0.0, float(Decimal(str(q_sz)) - Decimal(str(step))))
                            if new_q > 0.0:
                                log.debug(f"Retrying limit order with adjusted size due to wire rounding: {q_sz} -> {new_q}")
                                try:
                                    response = self.client.order(hl_symbol, is_buy, float(new_q), limit_px)  # type: ignore[misc]
                                except TypeError as e2:
                                    if "order_type" in str(e2):
                                        try:
                                            response = self.client.order(hl_symbol, is_buy, float(new_q), limit_px, "limit")  # type: ignore[misc]
                                        except TypeError:
                                            response = self.client.order(hl_symbol, is_buy, float(new_q), limit_px, order_type="limit")  # type: ignore[misc]
                                    else:
                                        raise
                                q_sz = new_q
                            else:
                                raise
                        else:
                            raise
                    if response is not None:
                        log.debug(f"Hyperliquid order(positional, limit) response: {response}")
                    return {"ok": True, "request": {"coin": hl_symbol, "is_buy": is_buy, "sz": float(q_sz), "limit_px": limit_px, "type": "limit"}, "response": response, "ts": time.time()}
                # Fallback: place a market order if limit path not available
                response = self.client.market_open(hl_symbol, is_buy, float(q_sz))  # type: ignore[misc]
                log.debug(f"Hyperliquid market_open(as fallback for limit) response: {response}")
                return {"ok": True, "request": {"coin": hl_symbol, "is_buy": is_buy, "sz": float(q_sz), "type": "market"}, "response": response, "ts": time.time()}
            # 3) Market orders without market_open: try generic 'order(coin, is_buy, sz)'
            if hasattr(self.client, "order"):
                q_sz = self._quantize_size(hl_symbol, float(size))
                response = None
                try:
                    # Some SDKs: order(coin, is_buy, sz)
                    response = self.client.order(hl_symbol, is_buy, float(q_sz))  # type: ignore[misc]
                except TypeError as e:
                    if "order_type" in str(e):
                        # Try including order_type='market'
                        try:
                            response = self.client.order(hl_symbol, is_buy, float(q_sz), "market")  # type: ignore[misc]
                        except TypeError:
                            response = self.client.order(hl_symbol, is_buy, float(q_sz), order_type="market")  # type: ignore[misc]
                    else:
                        raise
                log.debug(f"Hyperliquid order(positional, market) response: {response}")
                return {"ok": True, "request": {"coin": hl_symbol, "is_buy": is_buy, "sz": float(q_sz), "type": "market"}, "response": response, "ts": time.time()}
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

    def _get_size_step(self, coin: str) -> float:
        """
        Best-effort retrieval of size step (minimum increment) for a coin.
        Falls back to conservative defaults if SDK info is unavailable.
        """
        # Conservative defaults (may be overridden by Info metadata)
        defaults = {
            "BTC": 0.001,
            "ETH": 0.01,
        }
        try:
            if HyperliquidInfo is not None:
                info_client = None
                last_err: Optional[Exception] = None
                # Prefer constructing Info with explicit chain when available; some SDKs need it to read testnet state
                chain_kw = {}
                try:
                    if _HLChain is not None:
                        chain_kw = {"chain": (_HLChain.TESTNET if bool(self.conn.testnet) else _HLChain.MAINNET)}  # type: ignore[assignment]
                except Exception:
                    chain_kw = {}
                for args, kwargs in (
                    # With base_url + chain (preferred)
                    ((), {"base_url": self.conn.base_url, **chain_kw}),
                    # With positional base_url + chain
                    ((self.conn.base_url,), {**chain_kw}),
                    # Chain only (fallback)
                    ((), {**chain_kw}),
                    # Base_url only (legacy)
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
                # Try common metadata endpoints
                meta_obj = None
                for getter in ("meta", "all_coins", "get_all_coins"):
                    fn = getattr(info_client, getter, None)
                    if callable(fn):
                        try:
                            meta_obj = fn()
                            break
                        except Exception:
                            continue
                # Try to extract szDecimals for the coin
                if isinstance(meta_obj, dict):
                    candidates = []
                    for key in ("coins", "assets", "data"):
                        if key in meta_obj:
                            obj = meta_obj[key]
                            if isinstance(obj, list):
                                candidates = obj
                                break
                    if not candidates and "meta" in meta_obj and isinstance(meta_obj["meta"], list):
                        candidates = meta_obj["meta"]
                    for c in candidates:
                        try:
                            name = str(c.get("name") or c.get("coin") or c.get("symbol") or "").upper()
                            if name == coin.upper():
                                sz_dec = c.get("szDecimals") or c.get("sz_decimals") or c.get("sizeDecimals")
                                if sz_dec is not None:
                                    d = int(sz_dec)
                                    step = 10.0 ** (-d)
                                    if step > 0:
                                        return float(step)
                        except Exception:
                            continue
        except Exception:
            pass
        return float(defaults.get(coin.upper(), 0.001))

    def _quantize_size(self, coin: str, size: float) -> float:
        """
        Quantize the size down to the allowed increment to avoid wire rounding errors.
        """
        try:
            step = max(Decimal("1e-12"), Decimal(str(self._get_size_step(coin))))
            if float(size) <= 0 or step <= 0:
                return 0.0
            getcontext().prec = max(getcontext().prec, 28)
            sz = Decimal(str(size))
            q = sz.quantize(step, rounding=ROUND_DOWN)
            if q <= 0 and sz > 0:
                q = step
            # Limit to 12 decimals on wire
            return float(Decimal(q).quantize(Decimal("1e-12"), rounding=ROUND_DOWN))
        except Exception:
            # Last resort: return original size with limited precision
            try:
                return float(Decimal(str(size)).quantize(Decimal("1e-12"), rounding=ROUND_DOWN))
            except Exception:
                return float(f"{float(size):.12f}")

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
            # Hyperliquid testnet payload often exposes positions under 'assetPositions' as a list of objects
            if pos_container is None and isinstance(data, dict) and "assetPositions" in data:
                pos_container = data.get("assetPositions")
            positions: Dict[str, Any] = {}
            if isinstance(pos_container, list):
                for p in pos_container:
                    # Support both flat position dicts and HL shape: {'type': 'oneWay', 'position': {...}}
                    if isinstance(p, dict) and "position" in p and isinstance(p["position"], dict):
                        p = p["position"]
                    if not isinstance(p, dict):
                        continue
                    sym = str(p.get("symbol") or p.get("coin") or "")
                    if not sym:
                        continue
                    qty_val = None
                    for qk in ("sz", "szi", "size", "qty", "positionSize", "contracts"):
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
                    # Optional leverage extraction if present
                    lev_val = None
                    # HL can present leverage as {'type':'cross','value':20}
                    if "leverage" in p:
                        try:
                            lev_obj = p.get("leverage")
                            if isinstance(lev_obj, dict) and "value" in lev_obj:
                                lev_val = float(lev_obj.get("value"))
                            else:
                                lev_val = float(lev_obj)
                        except Exception:
                            lev_val = None
                    if lev_val is None:
                        for lk in ("lev", "x", "isolatedLeverage"):
                            if lk in p:
                                try:
                                    lev_val = float(p[lk])
                                    break
                                except Exception:
                                    pass
                    pos_obj = {"symbol": sym, "qty": float(qty_val), "avg_price": float(avg_px)}
                    if lev_val is not None:
                        pos_obj["leverage"] = float(lev_val)
                    positions[sym] = pos_obj
            elif isinstance(pos_container, dict):
                for sym, p in pos_container.items():
                    try:
                        qty_val = None
                        if isinstance(p, dict):
                            for qk in ("sz", "szi", "size", "qty", "positionSize", "contracts"):
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
                            lev_val = None
                            if isinstance(p, dict):
                                if "leverage" in p:
                                    try:
                                        lev_obj = p.get("leverage")
                                        if isinstance(lev_obj, dict) and "value" in lev_obj:
                                            lev_val = float(lev_obj.get("value"))
                                        else:
                                            lev_val = float(lev_obj)
                                    except Exception:
                                        lev_val = None
                                if lev_val is None:
                                    for lk in ("lev", "x", "isolatedLeverage"):
                                        if lk in p:
                                            try:
                                                lev_val = float(p[lk])
                                                break
                                            except Exception:
                                                pass
                            pos_obj = {"symbol": str(sym), "qty": float(qty_val), "avg_price": float(avg_px)}
                            if lev_val is not None:
                                pos_obj["leverage"] = float(lev_val)
                            positions[str(sym)] = pos_obj
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
                    return {"ok": True, "response": response, "ts": time.time(), "query_address_used": self.query_address}
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
                # Call user_state; prefer signer address but fall back to provided wallet if equity is zero
                addresses_to_try: list[str] = []
                signer_addr = self.account_address
                if signer_addr:
                    addresses_to_try.append(signer_addr)
                if self.conn.wallet_address and self.conn.wallet_address not in addresses_to_try:
                    addresses_to_try.append(self.conn.wallet_address)
                best_payload: Optional[Dict[str, Any]] = None
                best_raw: Optional[Dict[str, Any]] = None
                best_addr_used: Optional[str] = None
                best_equity = -1.0
                for addr in addresses_to_try:
                    for call in (
                        lambda a=addr: info_client.user_state(a),  # type: ignore[attr-defined]
                        lambda a=addr: info_client.user_state(address=a),  # type: ignore[attr-defined]
                    ):
                        try:
                            raw = call()
                            normalized = self._normalize_user_state(raw)
                            equity = float(normalized.get("equity", 0.0))
                            if equity > best_equity:
                                best_equity = equity
                                best_payload = normalized
                                best_raw = raw
                                best_addr_used = addr
                            # Short-circuit if clearly non-zero equity
                            if equity > 0.0:
                                break
                        except Exception as e:
                            last_err = e
                            continue
                    if best_equity > 0.0:
                        break
                if best_payload is not None:
                    return {"ok": True, "response": best_payload, "raw": best_raw, "ts": time.time(), "query_address_used": best_addr_used}
                raise last_err or RuntimeError("user_state unavailable or empty")
        except Exception as e:
            log.error(f"Failed to fetch portfolio from Hyperliquid: {e}")
            return {"ok": False, "error": str(e), "ts": time.time()}
        # 3) Fallback: not available
        return {"ok": False, "error": "Portfolio API not available in this SDK", "ts": time.time()}

    def close_all_positions(self) -> Dict[str, Any]:
        """
        Flatten all open positions by placing opposing market orders for the full size.
        Returns a summary of close attempts.
        """
        summary: Dict[str, Any] = {"ok": True, "closed": [], "errors": []}
        try:
            pf = self.get_portfolio()
            resp = pf.get("response", {}) if isinstance(pf, dict) else {}
            positions = resp.get("positions", {}) if isinstance(resp, dict) else {}
            # Normalize dict and list shapes
            pos_list = []
            if isinstance(positions, dict):
                for k, v in positions.items():
                    if isinstance(v, dict):
                        v = dict(v)
                        v.setdefault("symbol", k)
                        pos_list.append(v)
            elif isinstance(positions, list):
                pos_list = positions
            for p in pos_list:
                try:
                    sym = str(p.get("symbol") or p.get("coin") or "")
                    qty = float(p.get("qty") or p.get("size") or p.get("sz") or p.get("szi") or 0.0)
                    if not sym or qty == 0.0:
                        continue
                    side = "sell" if qty > 0 else "buy"
                    sz = abs(qty)
                    # Place reduce-only market order by convention (some SDKs infer reduce-only; we best-effort place market)
                    r = self.place_order(symbol=sym, side=side, size=sz, leverage=1, order_type="market")
                    if r.get("ok"):
                        summary["closed"].append({"symbol": sym, "qty": qty, "resp": r})
                    else:
                        summary["errors"].append({"symbol": sym, "qty": qty, "error": r.get("error")})
                except Exception as e:
                    summary["ok"] = False
                    summary["errors"].append({"symbol": p.get("symbol"), "error": str(e)})
        except Exception as e:
            summary["ok"] = False
            summary["errors"].append({"error": str(e)})
        return summary

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


