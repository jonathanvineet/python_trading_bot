from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from bot.config import Settings
from bot.basic_bot import BasicBot, OrderRequest
from bot.logging_config import setup_logging

settings = Settings.load()
setup_logging(settings.log_level)
bot = BasicBot(settings)

app = FastAPI(title="Futures Testnet Trading Bot", version="0.1.0")


class OrderIn(BaseModel):
    symbol: str
    side: str
    order_type: str = Field(alias="type")
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"


class GridIn(BaseModel):
    symbol: str
    side: str
    levels: int
    step_pct: float
    quantity: float
    base_price: Optional[float] = None


@app.get("/api/diagnostics")
def api_diagnostics(symbol: str | None = None):
    return bot.diagnostics(symbol)


@app.get("/api/filters")
def api_filters(symbol: str):
  try:
    bot._symbol_filters.ensure(bot.client)  # type: ignore[attr-defined]
    filt = bot._symbol_filters.get(symbol)  # type: ignore[attr-defined]
    if not filt:
      raise HTTPException(status_code=404, detail="Symbol filters not found")
    return {
      "symbol": filt.symbol,
      "tickSize": str(filt.tick_size),
      "priceMin": str(filt.price_min),
      "priceMax": str(filt.price_max),
      "stepSize": str(filt.step_size),
      "lotMin": str(filt.lot_min),
      "lotMax": str(filt.lot_max),
    }
  except HTTPException:
    raise
  except Exception as e:  # noqa: BLE001
    raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/order")
def api_order(order: OrderIn):
  req = OrderRequest(
    symbol=order.symbol.upper(),
    side=order.side.upper(),
    order_type=order.order_type,
    quantity=order.quantity,
    price=order.price,
    stop_price=order.stop_price,
    time_in_force=order.time_in_force,
  )
  resp = bot.place_order(req, source="web-ui")
  if not resp.success:
    raise HTTPException(status_code=400, detail=resp.error or "Order failed")
  return resp.raw


@app.post("/api/grid")
def api_grid(grid: GridIn):
  result = bot.place_grid_orders(
    symbol=grid.symbol,
    side=grid.side,
    base_price=grid.base_price,
    levels=grid.levels,
    step_pct=grid.step_pct,
    quantity=grid.quantity,
    source="web-ui-grid",
  )
  return result["grid"]


@app.get("/api/balance")
def api_balance():
    if bot.settings.dry_run:
        return {"dry_run": True}
    try:
        return {"balance": bot.client.futures_account_balance()}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/positions")
def api_positions():
    if bot.settings.dry_run:
        return {"dry_run": True}
    try:
        pr = bot.client.futures_position_risk()
        nz = [p for p in pr if float(p.get("positionAmt", 0)) != 0]
        return {"positions": nz}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <title>Futures Testnet Bot</title>
  <style>
    body { font-family: system-ui, Arial, sans-serif; margin: 1.5rem; background:#10141a; color:#e5e7eb; }
    h1 { font-size: 1.4rem; }
    section { margin-bottom: 1.2rem; padding:1rem; border:1px solid #2c3948; border-radius:6px; }
    input, select { padding:4px 6px; margin:2px; background:#1f2730; border:1px solid #334355; color:#e5e7eb; }
    button { padding:6px 12px; background:#2563eb; color:#fff; border:none; border-radius:4px; cursor:pointer; }
    button:hover { background:#1d4ed8; }
    pre { background:#1f2730; padding:10px; overflow:auto; }
    .grid-row { display:flex; gap:0.5rem; flex-wrap:wrap; }
    label { display:flex; flex-direction:column; font-size:0.75rem; text-transform:uppercase; letter-spacing:.05em; }
  </style>
</head>
<body>
  <h1>Binance Futures Testnet Bot</h1>
  <section>
    <h2>Diagnostics</h2>
    <button onclick=loadDiag()>Run Diagnostics</button>
    <pre id=diag></pre>
  </section>
  <section>
    <h2>Place Order</h2>
    <div class=grid-row>
      <label>Symbol<input id=symbol value=BTCUSDT></label>
      <label>Side<select id=side><option>BUY</option><option>SELL</option></select></label>
      <label>Type<select id=otype>
        <option>market</option><option>limit</option><option>stop_limit</option><option>stop_market</option><option>take_profit</option><option>take_profit_market</option>
      </select></label>
      <label>Qty<input id=qty value=0.001></label>
      <label>Price<input id=price placeholder="opt"></label>
      <label>Stop<input id=stop placeholder="opt"></label>
      <label>TIF<select id=tif><option>GTC</option><option>IOC</option><option>FOK</option></select></label>
    </div>
    <button onclick=place()>Submit</button>
    <pre id=order></pre>
  </section>
  <section>
    <h2>Grid</h2>
    <div class=grid-row>
      <label>Symbol<input id=gsymbol value=BTCUSDT></label>
      <label>Side<select id=gside><option>BUY</option><option>SELL</option></select></label>
      <label>Levels<input id=levels value=3></label>
      <label>Step %<input id=step value=0.5></label>
      <label>Qty<input id=gqty value=0.001></label>
      <label>Base Price<input id=base placeholder="auto"></label>
    </div>
    <button onclick=grid()>Build Grid</button>
    <pre id=gridout></pre>
  </section>
  <section>
    <h2>Balance & Positions</h2>
    <button onclick=balance()>Balance</button>
    <button onclick=positions()>Positions</button>
    <pre id=acct></pre>
  </section>
  <script>
    async function loadDiag(){ const r=await fetch('/api/diagnostics'); document.getElementById('diag').textContent=JSON.stringify(await r.json(),null,2); }
    async function place(){
      const body={symbol:val('symbol'), side:val('side'), type:val('otype'), quantity:parseFloat(val('qty')),
        price: numOrNull('price'), stop_price: numOrNull('stop'), time_in_force: val('tif')};
      const r=await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      document.getElementById('order').textContent=JSON.stringify(await r.json(),null,2);
    }
    async function grid(){
      const body={symbol:val('gsymbol'), side:val('gside'), levels:parseInt(val('levels')), step_pct:parseFloat(val('step')), quantity:parseFloat(val('gqty'))};
      const bp=numOrNull('base'); if(bp!==null) body.base_price=bp; const r=await fetch('/api/grid',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      document.getElementById('gridout').textContent=JSON.stringify(await r.json(),null,2);
    }
    async function balance(){ const r=await fetch('/api/balance'); document.getElementById('acct').textContent=JSON.stringify(await r.json(),null,2);} 
    async function positions(){ const r=await fetch('/api/positions'); document.getElementById('acct').textContent=JSON.stringify(await r.json(),null,2);} 
    function val(id){return document.getElementById(id).value.trim();}
    function numOrNull(id){const v=val(id); return v?parseFloat(v):null;}
  </script>
</body>
</html>
"""


@app.get("/")
def root_html():  # pragma: no cover - simple HTML route
    return HTMLResponse(content=HTML_TEMPLATE)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn
    uvicorn.run("web_server:app", host="0.0.0.0", port=8000, reload=False)