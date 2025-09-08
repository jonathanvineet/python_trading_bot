from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from bot.basic_bot import BasicBot, OrderRequest
from bot.config import Settings
from bot.logging_config import setup_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Binance Futures Testnet Trading Bot")
    p.add_argument("--symbol", required=True, help="Trading pair symbol e.g. BTCUSDT")
    p.add_argument("--side", required=True, choices=["BUY", "SELL"], help="Order side")
    p.add_argument(
        "--type",
        required=True,
        choices=["market", "limit", "stop_limit"],
        help="Order type",
    )
    p.add_argument("--quantity", required=True, type=float, help="Order quantity")
    p.add_argument("--price", type=float, help="Limit price (for limit/stop_limit)")
    p.add_argument("--stop-price", type=float, dest="stop_price", help="Stop trigger price (stop_limit)")
    p.add_argument(
        "--time-in-force",
        default="GTC",
        choices=["GTC", "IOC", "FOK"],
        dest="time_in_force",
        help="Time in force for limit orders",
    )
    p.add_argument("--api-key", dest="api_key", help="Binance API key (else env BINANCE_API_KEY)")
    p.add_argument("--api-secret", dest="api_secret", help="Binance API secret (else env BINANCE_API_SECRET)")
    p.add_argument("--dry-run", action="store_true", help="Simulate order without sending")
    p.add_argument("--log-level", default="INFO", help="Log level (default INFO)")
    p.add_argument("--diagnostic", action="store_true", help="Run connectivity/auth diagnostics and exit (or before order if also placing)")
    p.add_argument("--diagnostic-only", action="store_true", help="Only run diagnostics; do not place order")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = Settings.load(
        {
            "api_key": args.api_key,
            "api_secret": args.api_secret,
            "dry_run": args.dry_run,
            "log_level": args.log_level,
        }
    )
    setup_logging(settings.log_level)

    bot = BasicBot(settings)

    if args.diagnostic or args.diagnostic_only:
        diag = bot.diagnostics(symbol=args.symbol)
        print(json.dumps({"diagnostics": diag}, indent=2))
        if args.diagnostic_only:
            return 0
    order_req = OrderRequest(
        symbol=args.symbol.upper(),
        side=args.side,
        order_type=args.type,
        quantity=args.quantity,
        price=args.price,
        stop_price=args.stop_price,
        time_in_force=args.time_in_force,
    )

    response = bot.place_order(order_req)
    output: dict[str, Any] = {
        "success": response.success,
        "error": response.error,
        "data": response.raw,
    }
    print(json.dumps(output, indent=2, default=str))
    return 0 if response.success else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
