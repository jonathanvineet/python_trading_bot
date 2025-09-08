from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from .binance_rest import RESTClient, BinanceRESTError
from .config import Settings

logger = logging.getLogger(__name__)


VALID_SIDES = {"BUY", "SELL"}
VALID_ORDER_TYPES = {"market", "limit", "stop_limit"}


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
        if self.order_type in {"limit", "stop_limit"} and (self.price is None or self.price <= 0):
            raise ValueError("Price required and must be positive for limit/stop_limit orders.")
        if self.order_type == "stop_limit" and (self.stop_price is None or self.stop_price <= 0):
            raise ValueError("stop_price required and must be positive for stop_limit orders.")


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

    def place_order(self, req: OrderRequest) -> OrderResponse:
        logger.info("Placing order: %s", asdict(req))
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
            }
            return OrderResponse(success=True, raw=fake_resp)

        params: Dict[str, Any] = {
            "symbol": req.symbol.upper(),
            "side": req.side,
            "quantity": req.quantity,
        }
        if req.order_type == "market":
            params["type"] = "MARKET"
        elif req.order_type == "limit":
            params["type"] = "LIMIT"
            params["timeInForce"] = req.time_in_force
            params["price"] = req.price
        elif req.order_type == "stop_limit":
            # Futures STOP order with limit price = price, stopPrice triggers
            params["type"] = "STOP"
            params["timeInForce"] = req.time_in_force
            params["price"] = req.price
            params["stopPrice"] = req.stop_price
        else:
            return OrderResponse(success=False, raw={}, error="Unsupported order type")

        try:
            response = self.client.futures_order(**params)
            logger.info("Order accepted: id=%s status=%s", response.get("orderId"), response.get("status"))
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
