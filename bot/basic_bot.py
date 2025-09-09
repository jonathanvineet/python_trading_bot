from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from .binance_rest import RESTClient, BinanceRESTError
from .symbol_filters import SymbolFilterCache
from .config import Settings

logger = logging.getLogger(__name__)


VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {
    "market",
    "limit",
    "stop_limit",        # maps to STOP (stop + limit price)
    "stop_market",       # maps to STOP_MARKET (stop trigger only)
    "take_profit",       # maps to TAKE_PROFIT (tp + limit price)
    "take_profit_market" # maps to TAKE_PROFIT_MARKET (tp trigger only)
}


@dataclass
class OrderRequest:
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"

    def validate(self) -> None:
        if self.side not in VALID_SIDES:
            raise ValueError(f"Invalid side: {self.side}. Must be one of {VALID_SIDES}.")
        if self.order_type not in VALID_ORDER_TYPES:
            raise ValueError(
                f"Invalid order type: {self.order_type}. Must be one of {VALID_ORDER_TYPES}."
            )
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive.")
        if self.order_type in {"limit"} and (self.price is None or self.price <= 0):
            raise ValueError("Price required and must be positive for limit orders.")
        if self.order_type in {"stop_limit", "take_profit"}:
            if (self.price is None or self.price <= 0) or (self.stop_price is None or self.stop_price <= 0):
                raise ValueError("price and stop_price required & positive for stop_limit / take_profit.")
        if self.order_type in {"stop_market", "take_profit_market"} and (self.stop_price is None or self.stop_price <= 0):
            raise ValueError("stop_price required & positive for stop_market / take_profit_market.")


@dataclass
class OrderResponse:
    success: bool
    raw: Dict[str, Any]
    error: Optional[str] = None


class BasicBot:
    """Simplified Futures Testnet trading bot using direct REST calls."""

    def __init__(self, settings: Settings):
        self.settings = settings
        if not settings.api_key or not settings.api_secret:
            logger.warning(
                "API key/secret missing. Operating in dry-run mode only. Provide BINANCE_API_KEY/BINANCE_API_SECRET for real orders."
            )
            settings.dry_run = True
        self.client = RESTClient(
            api_key=settings.api_key or "",  # safe due to dry-run check
            api_secret=settings.api_secret or "",
            base_url=settings.base_url,
            recv_window=settings.recv_window,
        )
        # Cache for symbol filters (tick size, step size)
        self._symbol_filters = SymbolFilterCache()


    def place_order(self, req: OrderRequest, source: str = "cli", strict: bool = False) -> OrderResponse:
        logger.info("Placing order (source=%s): %s", source, asdict(req))
        try:
            req.validate()
        except Exception as e:  # noqa: BLE001
            logger.error("Validation failed: %s", e)
            return OrderResponse(success=False, raw={}, error=str(e))

        if self.settings.dry_run:
            logger.info("Dry-run: simulating order placement.")
            fake_resp = {
                "symbol": req.symbol,
                "side": req.side,
                "type": req.order_type,
                "status": "SIMULATED",
                "origQty": req.quantity,
                "price": req.price,
                "stopPrice": req.stop_price,
                "source": source,
            }
            return OrderResponse(success=True, raw=fake_resp)

        params: Dict[str, Any] = {
            "symbol": req.symbol.upper(),
            "side": req.side,
            "quantity": req.quantity,
        }
        # Ensure filters (only for non-market for price/qty normalization)
        try:
            self._symbol_filters.ensure(self.client)
            filt = self._symbol_filters.get(req.symbol)
        except Exception as _e:  # noqa: BLE001
            filt = None
        # Adjust quantity if filter available
        if filt:
            if not filt.is_qty_valid(req.quantity):
                try:
                    adj_qty = filt.adjust_quantity(req.quantity)
                    if strict:
                        return OrderResponse(False, {}, f"Quantity not valid step size (wanted {req.quantity}, nearest {adj_qty})")
                    if adj_qty != req.quantity:
                        logger.info(
                            "Adjusted quantity from %s to %s based on step size (source=%s)",
                            req.quantity,
                            adj_qty,
                            source,
                        )
                    params["quantity"] = adj_qty
                except Exception as e:  # noqa: BLE001
                    return OrderResponse(False, {}, f"Quantity invalid: {e}")
        ot = req.order_type
        if ot == "market":
            params["type"] = "MARKET"
        elif ot == "limit":
            params["type"] = "LIMIT"
            params["timeInForce"] = req.time_in_force
            price_val = req.price
            if filt and price_val is not None and not filt.is_price_valid(price_val):
                try:
                    adj = filt.adjust_price(price_val)
                    if strict:
                        return OrderResponse(False, {}, f"Price not valid tick size (wanted {price_val}, nearest {adj})")
                    if adj != price_val:
                        logger.info(
                            "Adjusted price from %s to %s based on tick size (source=%s)",
                            price_val,
                            adj,
                            source,
                        )
                    price_val = adj
                except Exception as e:  # noqa: BLE001
                    return OrderResponse(False, {}, f"Price invalid: {e}")
            params["price"] = price_val
        elif ot == "stop_limit":
            params["type"] = "STOP"
            params["timeInForce"] = req.time_in_force
            price_val = req.price
            stop_val = req.stop_price
            if filt and price_val is not None and not filt.is_price_valid(price_val):
                try:
                    adj = filt.adjust_price(price_val)
                    if strict:
                        return OrderResponse(False, {}, f"Price not valid tick size (wanted {price_val}, nearest {adj})")
                    if adj != price_val:
                        logger.info(
                            "Adjusted price from %s to %s based on tick size (source=%s)",
                            price_val,
                            adj,
                            source,
                        )
                    price_val = adj
                except Exception as e:  # noqa: BLE001
                    return OrderResponse(False, {}, f"Price invalid: {e}")
            if filt and stop_val is not None and not filt.is_price_valid(stop_val):
                try:
                    adj = filt.adjust_price(stop_val)
                    if strict:
                        return OrderResponse(False, {}, f"Stop price not valid tick size (wanted {stop_val}, nearest {adj})")
                    if adj != stop_val:
                        logger.info(
                            "Adjusted stopPrice from %s to %s based on tick size (source=%s)",
                            stop_val,
                            adj,
                            source,
                        )
                    stop_val = adj
                except Exception as e:  # noqa: BLE001
                    return OrderResponse(False, {}, f"Stop price invalid: {e}")
            params["price"] = price_val
            params["stopPrice"] = stop_val
        elif ot == "stop_market":
            params["type"] = "STOP_MARKET"
            stop_val = req.stop_price
            if filt and stop_val is not None and not filt.is_price_valid(stop_val):
                try:
                    adj = filt.adjust_price(stop_val)
                    if strict:
                        return OrderResponse(False, {}, f"Stop price not valid tick size (wanted {stop_val}, nearest {adj})")
                    if adj != stop_val:
                        logger.info(
                            "Adjusted stopPrice from %s to %s based on tick size (source=%s)",
                            stop_val,
                            adj,
                            source,
                        )
                    stop_val = adj
                except Exception as e:  # noqa: BLE001
                    return OrderResponse(False, {}, f"Stop price invalid: {e}")
            params["stopPrice"] = stop_val
        elif ot == "take_profit":
            params["type"] = "TAKE_PROFIT"
            params["timeInForce"] = req.time_in_force
            price_val = req.price
            stop_val = req.stop_price
            if filt and price_val is not None:
                try:
                    adj = filt.adjust_price(price_val)
                    if adj != price_val:
                        logger.info(
                            "Adjusted price from %s to %s based on tick size (source=%s)",
                            price_val,
                            adj,
                            source,
                        )
                    price_val = adj
                except Exception as e:  # noqa: BLE001
                    return OrderResponse(False, {}, f"Price invalid: {e}")
            if filt and stop_val is not None and not filt.is_price_valid(stop_val):
                try:
                    adj = filt.adjust_price(stop_val)
                    if strict:
                        return OrderResponse(False, {}, f"Stop price not valid tick size (wanted {stop_val}, nearest {adj})")
                    if adj != stop_val:
                        logger.info(
                            "Adjusted stopPrice from %s to %s based on tick size (source=%s)",
                            stop_val,
                            adj,
                            source,
                        )
                    stop_val = adj
                except Exception as e:  # noqa: BLE001
                    return OrderResponse(False, {}, f"Stop price invalid: {e}")
            params["price"] = price_val
            params["stopPrice"] = stop_val
        elif ot == "take_profit_market":
            params["type"] = "TAKE_PROFIT_MARKET"
            stop_val = req.stop_price
            if filt and stop_val is not None:
                try:
                    adj = filt.adjust_price(stop_val)
                    if adj != stop_val:
                        logger.info(
                            "Adjusted stopPrice from %s to %s based on tick size (source=%s)",
                            stop_val,
                            adj,
                            source,
                        )
                    stop_val = adj
                except Exception as e:  # noqa: BLE001
                    return OrderResponse(False, {}, f"Stop price invalid: {e}")
            params["stopPrice"] = stop_val
        else:
            return OrderResponse(success=False, raw={}, error=f"Unsupported order type {ot}")

        try:
            response = self.client.futures_order(**params)
            response["source"] = source  # annotate for downstream logging/inspection
            logger.info(
                "Order accepted (source=%s): id=%s status=%s", source, response.get("orderId"), response.get("status")
            )
            return OrderResponse(success=True, raw=response)
        except BinanceRESTError as e:
            logger.exception("Order failed: %s", e)
            return OrderResponse(success=False, raw={}, error=str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("Unexpected error placing order")
            return OrderResponse(success=False, raw={}, error=str(e))

    def diagnostics(self, symbol: str | None = None) -> Dict[str, Any]:
        """Run simple connectivity + auth diagnostics.

        Returns dict with ping, server time delta, exchange symbol presence, and (if keys) account balance summary.
        """
        out: Dict[str, Any] = {}
        try:
            out["ping"] = self.client.futures_ping() or {"ok": True}
        except Exception as e:  # noqa: BLE001
            out["ping_error"] = str(e)
        try:
            server = self.client.futures_server_time()
            import time as _t
            local_ms = int(_t.time() * 1000)
            out["server_time"] = server
            out["time_delta_ms"] = local_ms - server.get("serverTime", local_ms)
        except Exception as e:  # noqa: BLE001
            out["time_error"] = str(e)
        try:
            info = self.client.futures_exchange_info()
            out["exchange_info_symbols"] = len(info.get("symbols", []))
            if symbol:
                out["symbol_listed"] = any(s.get("symbol") == symbol.upper() for s in info.get("symbols", []))
        except Exception as e:  # noqa: BLE001
            out["exchange_info_error"] = str(e)
        # Auth-required checks
        if not self.settings.dry_run:
            try:
                bal = self.client.futures_account_balance()
                out["balance_count"] = len(bal)
            except Exception as e:  # noqa: BLE001
                out["balance_error"] = str(e)
            try:
                acct = self.client.futures_account()
                out["assets"] = len(acct.get("assets", []))
                out["positions"] = len(acct.get("positions", []))
            except Exception as e:  # noqa: BLE001
                out["account_error"] = str(e)
        # Masked key info
        if self.settings.api_key:
            ak = self.settings.api_key
            out["api_key_masked"] = f"{ak[:4]}***{ak[-4:]}"
        return out

    def place_grid_orders(
        self,
        symbol: str,
        side: str,
        base_price: float | None,
        levels: int,
        step_pct: float,
        quantity: float,
        time_in_force: str = "GTC",
        dry_run: bool | None = None,
        source: str = "cli-grid",
    ) -> Dict[str, Any]:
        """Create a simple static grid of limit orders around (or one-sided from) current price.

        BUY grid: places levels BUY limits below current (descending).
        SELL grid: places levels SELL limits above current (ascending).
        If base_price not provided, fetch ticker price.
        """
        side_u = side.upper()
        if side_u not in VALID_SIDES:
            raise ValueError("side must be BUY or SELL")
        dry = self.settings.dry_run if dry_run is None else dry_run
        try:
            if base_price is None:
                tp = self.client.futures_ticker_price(symbol)
                base_price = float(tp["price"])  # type: ignore[index]
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Failed to fetch ticker price: {e}") from e
        assert base_price is not None
        orders = []
        # Load filters once
        filt = None
        try:
            self._symbol_filters.ensure(self.client)
            filt = self._symbol_filters.get(symbol)
        except Exception:  # noqa: BLE001
            pass
        for i in range(1, levels + 1):
            if side_u == "BUY":
                price = base_price * (1 - step_pct / 100 * i)
            else:
                price = base_price * (1 + step_pct / 100 * i)
            price_rounded = price
            if filt:
                try:
                    if not filt.is_price_valid(price):
                        adj = filt.adjust_price(price)
                        if adj != price:
                            logger.info("Grid adjusted price %s -> %s (tick %s)", price, adj, filt.tick_size)
                        price_rounded = adj
                except Exception as e:  # noqa: BLE001
                    logger.warning("Grid price %s invalid: %s", price, e)
            req = OrderRequest(
                symbol=symbol.upper(),
                side=side_u,
                order_type="limit",
                quantity=quantity,
                price=price_rounded,
            )
            if dry or self.settings.dry_run:
                orders.append({"simulated": True, "price": price_rounded, "side": side_u, "source": source})
            else:
                resp = self.place_order(req, source=source)
                orders.append({
                    "price": price_rounded,
                    "side": side_u,
                    "orderId": resp.raw.get("orderId"),
                    "success": resp.success,
                    "error": resp.error,
                    "source": source,
                })
        return {
            "grid": {
                "symbol": symbol.upper(),
                "side": side_u,
                "levels": levels,
                "step_pct": step_pct,
                "base_price": base_price,
                "orders": orders,
                "dry_run": dry or self.settings.dry_run,
                "source": source,
            }
        }
