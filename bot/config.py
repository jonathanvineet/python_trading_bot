from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv


BINANCE_FUTURES_TESTNET_BASE = "https://testnet.binancefuture.com"


@dataclass
class Settings:
    api_key: str | None
    api_secret: str | None
    base_url: str = BINANCE_FUTURES_TESTNET_BASE
    recv_window: int = 5000
    dry_run: bool = False
    log_level: str = "INFO"

    @classmethod
    def load(cls, override: Optional[dict] = None) -> "Settings":
        load_dotenv(override=True)
        override = override or {}
        return cls(
            api_key=override.get("api_key") or os.getenv("BINANCE_API_KEY"),
            api_secret=override.get("api_secret") or os.getenv("BINANCE_API_SECRET"),
            base_url=override.get("base_url", BINANCE_FUTURES_TESTNET_BASE),
            recv_window=int(override.get("recv_window") or os.getenv("BINANCE_RECV_WINDOW", 5000)),
            dry_run=bool(override.get("dry_run") or os.getenv("DRY_RUN", "").lower() in {"1", "true", "yes"}),
            log_level=override.get("log_level") or os.getenv("LOG_LEVEL", "INFO"),
        )
