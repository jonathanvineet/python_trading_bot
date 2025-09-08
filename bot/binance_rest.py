from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)


class BinanceRESTError(RuntimeError):
    def __init__(self, status_code: int, err_code: int | None, msg: str, response_text: str):
        self.status_code = status_code
        self.err_code = err_code
        self.msg = msg
        self.response_text = response_text
        super().__init__(f"HTTP {status_code} Binance error {err_code}: {msg}")


@dataclass
class RESTClient:
    api_key: str
    api_secret: str
    base_url: str
    recv_window: int = 5000
    timeout: int = 10

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = urlencode(params, True)
        signature = hmac.new(
            self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _request(
        self,
        method: str,
        path: str,
        signed: bool = False,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        params = params or {}
        headers = {"X-MBX-APIKEY": self.api_key}
        if signed:
            params.setdefault("timestamp", int(time.time() * 1000))
            params.setdefault("recvWindow", self.recv_window)
            self._sign(params)
        url = f"{self.base_url}{path}"
        logger.debug("Request %s %s params=%s", method, url, params)
        resp = requests.request(
            method, url, params=params if method == "GET" else None, data=None if method == "GET" else params, headers=headers, timeout=self.timeout
        )
        text = resp.text
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            data = {"raw": text}
        if resp.status_code >= 400 or (isinstance(data, dict) and data.get("code", 0) < 0):
            err_code = data.get("code") if isinstance(data, dict) else None
            msg = data.get("msg") if isinstance(data, dict) else text
            logger.error("Binance REST error %s %s", err_code, msg)
            raise BinanceRESTError(resp.status_code, err_code, msg, text)
        logger.debug("Response: %s", data)
        return data  # type: ignore[return-value]

    # Futures endpoints
    def futures_account_balance(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v2/balance", signed=True)

    def futures_exchange_info(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/exchangeInfo")

    def futures_order(self, **params: Any) -> Dict[str, Any]:
        return self._request("POST", "/fapi/v1/order", signed=True, params=params)

    def futures_ping(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/ping")

    def futures_server_time(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v1/time")

    def futures_account(self) -> Dict[str, Any]:
        return self._request("GET", "/fapi/v2/account", signed=True)
