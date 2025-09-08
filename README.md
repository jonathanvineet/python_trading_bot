## Simplified Binance Futures Testnet Trading Bot

This project provides a minimal, extensible Python trading bot targeting the Binance **USDT-M Futures Testnet**.

Features:

- Market, Limit, and Stop-Limit orders (testnet only)
- REST implementation (no external abstractions required)
- Command-line interface with validation
- Structured logging (console + rotating file)
- Dry-run mode when API credentials are missing
- Clean, reusable code structure

> IMPORTANT: This is for educational use on the Binance **Futures Testnet**. Not production-ready. No warranty. Use at your own risk.

### 1. Setup

Clone and install dependencies:

```bash
pip install -r requirements.txt
```

Optionally create a `.env` file:

```env
BINANCE_API_KEY=your_testnet_key
BINANCE_API_SECRET=your_testnet_secret
LOG_LEVEL=INFO
```

Add your credentials securely:

1. Copy `.env.example` to `.env`
2. Paste your testnet keys:
```
BINANCE_API_KEY=...your key...
BINANCE_API_SECRET=...your secret...
```
3. NEVER hardcode keys in source files or commit `.env`.

### 2. Usage

Place a market order:

```bash
python main.py --symbol BTCUSDT --side BUY --type market --quantity 0.001 
```

Place a limit order:

```bash
python main.py --symbol BTCUSDT --side SELL --type limit --quantity 0.001 --price 75000 
```

Place a stop-limit order:

```bash
python main.py --symbol BTCUSDT --side BUY --type stop_limit --quantity 0.001 --price 76000 --stop-price 75500 
```

Dry run (no API keys required):

```bash
python main.py --symbol BTCUSDT --side BUY --type market --quantity 0.001 --dry-run
```

### 3. Project Structure

```
bot/
	basic_bot.py        # Core order placement logic
	binance_rest.py     # Minimal REST client with signing
	config.py           # Settings loader (.env + CLI overrides)
	logging_config.py   # Logging setup
main.py               # CLI entrypoint
requirements.txt
README.md
```

### 4. Extending

- Add more order types (e.g., OCO, Trailing Stop)
- Integrate websockets for live mark price & fills
- Implement risk controls (max position size, notional limits)
- Add strategy layer (signal generation, backtesting adapter)

### 5. Notes

- Base URL: `https://testnet.binancefuture.com`
- Endpoint used: `/fapi/v1/order`
- Signatures: HMAC SHA256 of query string with secret key
- Timestamps: Milliseconds since epoch

### 6. Disclaimer

This software is provided **AS IS**. No guarantees. Test thoroughly. Never use with real funds without proper safeguards.

---

Happy building.

# python_trading_bot