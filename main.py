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
        required=False,
        default="market",
        choices=[
            "market",
            "limit",
            "stop_limit",
            "stop_market",
            "take_profit",
            "take_profit_market",
        ],
        help="Order type (default market)",
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
    # Grid options
    p.add_argument("--grid", action="store_true", help="Place a simple one-sided grid of limit orders (requires --levels and --step-pct)")
    p.add_argument("--levels", type=int, help="Number of grid levels")
    p.add_argument("--step-pct", type=float, dest="step_pct", help="Percentage step between grid levels")
    p.add_argument("--base-price", type=float, dest="base_price", help="Optional manual base price for grid")
    p.add_argument("--interactive", action="store_true", help="Interactive prompt mode (ignores other order args unless grid specified)")
    p.add_argument("--balance", action="store_true", help="Show futures account balance summary and exit")
    p.add_argument("--positions", action="store_true", help="Show open positions and exit")
    p.add_argument("--strict-prices", action="store_true", help="Reject (do not auto-adjust) invalid tick/step sizes")
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

    if args.balance:
        if bot.settings.dry_run:
            print("Dry-run mode: no authenticated balance available", file=sys.stderr)
            return 0
        try:
            bal = bot.client.futures_account_balance()
            print(json.dumps({"balance": bal}, indent=2))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"error": str(e)}))
        return 0

    if args.positions:
        if bot.settings.dry_run:
            print("Dry-run mode: no authenticated positions available", file=sys.stderr)
            return 0
        try:
            pr = bot.client.futures_position_risk()
            # Filter non-zero positions
            non_zero = [p for p in pr if float(p.get("positionAmt", 0)) != 0]
            print(json.dumps({"positions": non_zero}, indent=2))
        except Exception as e:  # noqa: BLE001
            print(json.dumps({"error": str(e)}))
        return 0
    if args.grid:
        if not (args.levels and args.step_pct and args.quantity):
            print("--grid requires --levels, --step-pct, and --quantity", file=sys.stderr)
            return 2
        grid_result = bot.place_grid_orders(
            symbol=args.symbol,
            side=args.side,
            base_price=args.base_price,
            levels=args.levels,
            step_pct=args.step_pct,
            quantity=args.quantity,
            time_in_force=args.time_in_force,
            source="cli-grid",
        )
        print(json.dumps(grid_result, indent=2))
        return 0

    if args.interactive:
        print("Interactive mode. Press Ctrl+C to exit.")
        while True:
            try:
                sym = input(f"Symbol [{args.symbol}]: ") or args.symbol
                side = input("Side (BUY/SELL) [BUY]: ") or "BUY"
                otype = input("Type (market/limit/stop_limit/stop_market/take_profit/take_profit_market) [market]: ") or "market"
                qty = float(input("Quantity [1]: ") or 1)
                price = input("Price (blank if N/A): ") or None
                stop_price = input("Stop Price (blank if N/A): ") or None
                req = OrderRequest(
                    symbol=sym.upper(),
                    side=side.upper(),
                    order_type=otype,
                    quantity=qty,
                    price=float(price) if price else None,
                    stop_price=float(stop_price) if stop_price else None,
                    time_in_force=args.time_in_force,
                )
                resp = bot.place_order(req, source="cli-interactive")
                print(json.dumps({"success": resp.success, "error": resp.error, "data": resp.raw}, indent=2))
            except KeyboardInterrupt:
                print("\nExiting interactive mode.")
                break
            except Exception as e:  # noqa: BLE001
                print(f"Error: {e}")
        return 0

    # Standard single order path
    order_req = OrderRequest(
        symbol=args.symbol.upper(),
        side=args.side,
        order_type=args.type,
        quantity=args.quantity,
        price=args.price,
        stop_price=args.stop_price,
        time_in_force=args.time_in_force,
    )
    response = bot.place_order(order_req, source="cli", strict=args.strict_prices)
    output: dict[str, Any] = {"success": response.success, "error": response.error, "data": response.raw}
    print(json.dumps(output, indent=2, default=str))
    return 0 if response.success else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
