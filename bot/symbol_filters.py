from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, getcontext
from typing import Any, Dict, Optional


@dataclass
class SymbolFilters:
    symbol: str
    price_min: Decimal
    price_max: Decimal
    tick_size: Decimal
    lot_min: Decimal
    lot_max: Decimal
    step_size: Decimal

    @classmethod
    def from_exchange_symbol(cls, sym_data: Dict[str, Any]) -> "SymbolFilters":
        sym = sym_data["symbol"]
        price_min = Decimal("0")
        price_max = Decimal("0")
        tick_size = Decimal("1")
        lot_min = Decimal("0")
        lot_max = Decimal("0")
        step_size = Decimal("1")
        for f in sym_data.get("filters", []):
            ftype = f.get("filterType")
            if ftype == "PRICE_FILTER":
                price_min = Decimal(f.get("minPrice", "0"))
                price_max = Decimal(f.get("maxPrice", "0"))
                tick_size = Decimal(f.get("tickSize", "1"))
            elif ftype in {"LOT_SIZE", "MARKET_LOT_SIZE"}:
                lot_min = Decimal(f.get("minQty", "0"))
                lot_max = Decimal(f.get("maxQty", "0"))
                step_size = Decimal(f.get("stepSize", "1"))
        return cls(
            symbol=sym,
            price_min=price_min,
            price_max=price_max,
            tick_size=tick_size,
            lot_min=lot_min,
            lot_max=lot_max,
            step_size=step_size,
        )

    def is_price_valid(self, price: float) -> bool:
        p = Decimal(str(price))
        if self.tick_size <= 0:
            return True
        if p < self.price_min:
            return False
        if self.price_max > 0 and p > self.price_max:
            return False
        # Use quantization check
        # Normalize difference
        diff = (p - self.price_min) / self.tick_size
        return diff == diff.to_integral_value()

    def adjust_price(self, price: float) -> float:
        """Floor price to nearest valid tick multiple from price_min."""
        p = Decimal(str(price))
        if self.tick_size <= 0:
            return float(p)
        if p < self.price_min:
            raise ValueError(f"Price {price} < min price {self.price_min}")
        if self.price_max > 0 and p > self.price_max:
            raise ValueError(f"Price {price} > max price {self.price_max}")
        steps = ((p - self.price_min) / self.tick_size).to_integral_value(rounding=ROUND_DOWN)
        return float(self.price_min + steps * self.tick_size)

    def is_qty_valid(self, qty: float) -> bool:
        q = Decimal(str(qty))
        if q < self.lot_min:
            return False
        if self.lot_max > 0 and q > self.lot_max:
            return False
        if self.step_size <= 0:
            return True
        diff = (q - self.lot_min) / self.step_size
        return diff == diff.to_integral_value()

    def adjust_quantity(self, qty: float) -> float:
        q = Decimal(str(qty))
        if q < self.lot_min:
            raise ValueError(f"Quantity {qty} < min qty {self.lot_min}")
        if self.lot_max > 0 and q > self.lot_max:
            raise ValueError(f"Quantity {qty} > max qty {self.lot_max}")
        if self.step_size <= 0:
            return float(q)
        steps = ((q - self.lot_min) / self.step_size).to_integral_value(rounding=ROUND_DOWN)
        return float(self.lot_min + steps * self.step_size)


class SymbolFilterCache:
    def __init__(self):
        self._cache: Dict[str, SymbolFilters] = {}
        self._loaded = False

    def ensure(self, rest_client, force: bool = False) -> None:
        if self._loaded and not force:
            return
        data = rest_client.futures_exchange_info()
        for sym in data.get("symbols", []):
            try:
                filt = SymbolFilters.from_exchange_symbol(sym)
                self._cache[filt.symbol] = filt
            except Exception:
                continue
        self._loaded = True

    def get(self, symbol: str) -> Optional[SymbolFilters]:
        return self._cache.get(symbol.upper())
