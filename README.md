# Investment MCP Server

A Python [Model Context Protocol](https://modelcontextprotocol.io) server exposing Turkish investment market data tools for AI assistants. Covers BIST equities, foreign exchange, gold, TEFAS mutual funds, Turkey CPI inflation, multi-asset return comparison, inflation-adjusted returns, and customer portfolio access — all through a single, consistent JSON envelope.

**MCP endpoint:** `https://mcp.aykutbuyukkaya.com/mcp`

---

## Table of Contents

- [Claude Desktop Integration](#claude-desktop-integration)
- [Features](#features)
- [Data Sources](#data-sources)
- [Tools](#tools)
  - [get_stock_quote_metadata](#get_stock_quote_metadata)
  - [get_stock_ohlcv_bars](#get_stock_ohlcv_bars)
  - [get_currency_ohlcv_bars](#get_currency_ohlcv_bars)
  - [get_gold_price_data](#get_gold_price_data)
  - [get_fund_price_data](#get_fund_price_data)
  - [get_turkey_inflation](#get_turkey_inflation)
  - [compare_asset_returns](#compare_asset_returns)
  - [get_real_returns](#get_real_returns)
  - [get_customer_portfolio](#get_customer_portfolio)
- [Response Envelope](#response-envelope)
- [Setup](#setup)
- [Configuration](#configuration)
- [Running the Server](#running-the-server)
- [Docker](#docker)
- [Development & Testing](#development--testing)
- [Project Layout](#project-layout)

---

## Claude Desktop Integration

The server is publicly hosted — no local installation required.

### Step 1 — Locate the Claude Desktop config file

| Platform | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

### Step 2 — Add the server entry

Open `claude_desktop_config.json` (create it if it does not exist) and add the following entry under `mcpServers`:

```json
{
  "mcpServers": {
    "investment-mcp-server": {
      "type": "streamable-http",
      "url": "https://mcp.aykutbuyukkaya.com/mcp"
    }
  }
}
```

### Step 3 — Restart Claude Desktop

Quit and reopen Claude Desktop. The investment tools will appear in the tool list. You can verify by asking:

> "What investment tools do you have available?"

### Self-hosting

If you prefer to run the server locally, install the package with `uv sync` and point Claude Desktop to your own instance:

```json
{
  "mcpServers": {
    "investment-mcp-server": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/investment-mcp-server",
        "run",
        "investment-mcp-server"
      ],
      "env": {
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

---

## Features

- **BIST equities** — quote metadata and OHLCV candles via Yahoo Finance, with automatic `.IS` suffix normalization
- **Foreign exchange** — OHLCV candles for any Yahoo FX pair (USD/TRY, EUR/TRY, …)
- **Gold** — daily gram-gold (XAUTRY) prices from Canli Doviz
- **TEFAS funds** — daily NAV prices with total and annualized return calculations
- **Turkey CPI inflation** — static Fiyat Endeksi dataset (2025=100) with monthly and annual changes
- **Multi-asset comparison** — rank up to 10 mixed-type assets by nominal return over the same period
- **Real (inflation-adjusted) returns** — Fisher-equation real return for any supported asset against Turkey CPI
- **Customer portfolio** — live portfolio fetch from a configurable backend service
- **Consistent envelope** — every tool returns `{ok, data, error}` so errors are always typed and structured

---

## Data Sources

| Asset class | Provider | Notes |
|---|---|---|
| BIST equities | Yahoo Finance | Tickers normalized to `.IS` suffix |
| Foreign currency | Yahoo Finance | Accepts slash, compact, or Yahoo FX symbol forms |
| Gram gold (XAUTRY) | Canli Doviz | Direct provider API |
| TEFAS mutual funds | TEFAS | Direct provider API |
| Turkey CPI inflation | Static dataset | Fiyat Endeksi / Tuketici Fiyatlari, 2025=100 |
| Customer portfolio | Local backend | Configurable via `PORTFOLIO_BACKEND_BASE_URL` |

---

## Tools

All tools share two time-range styles:

- **Preset window** — pass `preset` with one of `1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`
- **Explicit range** — pass both `start_date`/`end_date` (or `start`/`end` for stock/currency bars) together; cannot be combined with `preset`
- **Current price** — pass `current_price=true` to skip history and return the latest price only

---

### `get_stock_quote_metadata`

Fetch high-level metadata for a BIST equity from Yahoo Finance.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `ticker` | `string` | required | BIST symbol. Accepts `THYAO` or `THYAO.IS`; normalized to uppercase + `.IS` suffix. |
| `include_prepost` | `boolean` | `false` | Include pre/post-market periods when available. |
| `current_price` | `boolean` | `false` | Return only the latest market price instead of the full metadata payload. |

**Returns** — currency, exchange, regular market price, 52-week high/low, previous close, volume, timezone, and granularity.

**Example prompt**
> "What is the current price and 52-week range for THYAO?"

---

### `get_stock_ohlcv_bars`

Fetch OHLCV candles for a BIST equity.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `ticker` | `string` | required | BIST symbol (`THYAO` or `THYAO.IS`). |
| `preset` | `string` | `null` | Preset window: `1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`. |
| `start` | `string` | `null` | Start datetime `dd.mm.yyyy hh.MM` (Europe/Istanbul). Requires `end`. |
| `end` | `string` | `null` | End datetime `dd.mm.yyyy hh.MM` (Europe/Istanbul). Requires `start`. |
| `interval` | `string` | `1d` | Candle granularity: `1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo`. |
| `include_prepost` | `boolean` | `false` | Include pre/post session candles. |
| `include_null_bars` | `boolean` | `false` | When `false`, bars with any null OHLCV value are dropped. |
| `strict_alignment` | `boolean` | `true` | Return `DATA_ALIGNMENT_ERROR` if array lengths differ. |
| `limit` | `integer` | `null` | Cap the number of returned bars to the latest N. |
| `current_price` | `boolean` | `false` | Return only the latest price (ignores range parameters). |

**Example prompt**
> "Show me daily candles for SISE over the last 3 months."

---

### `get_currency_ohlcv_bars`

Fetch OHLCV candles for a foreign currency pair via Yahoo Finance.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `pair` | `string` | required | Currency pair. Accepts `USD/TRY`, `USDTRY`, `TRY=X`, `EURTRY=X`, etc. |
| `preset` | `string` | `null` | Preset window: `1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`. |
| `start` | `string` | `null` | Start datetime `dd.mm.yyyy hh.MM` (Europe/Istanbul). Requires `end`. |
| `end` | `string` | `null` | End datetime `dd.mm.yyyy hh.MM` (Europe/Istanbul). Requires `start`. |
| `interval` | `string` | `1d` | Candle granularity: `1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo`. |
| `include_prepost` | `boolean` | `true` | Include pre/post periods (defaults `true` for FX pairs). |
| `include_null_bars` | `boolean` | `false` | Drop bars with null OHLCV values when `false`. |
| `strict_alignment` | `boolean` | `true` | Return error if array lengths are misaligned. |
| `limit` | `integer` | `null` | Return only the latest N bars. |
| `current_price` | `boolean` | `false` | Return only the latest exchange rate. |

**Example prompt**
> "What is the EUR/TRY rate over the past year?"

---

### `get_gold_price_data`

Fetch daily gram-gold (XAUTRY) prices from Canli Doviz.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `asset` | `string` | `gram-altin` | Gold asset. Accepts `gram-altin`, `gram`, `XAUTRY`, `XAU-TRY`. |
| `preset` | `string` | `null` | Preset window: `1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`. |
| `start_date` | `string` | `null` | Start date `YYYY-MM-DD`. Requires `end_date`. |
| `end_date` | `string` | `null` | End date `YYYY-MM-DD`. Requires `start_date`. |
| `current_price` | `boolean` | `false` | Return only the latest gold price. |

**Returns** — opening, closing, and average price per day.

**Example prompt**
> "How much has the gram-gold price changed this year?"

---

### `get_fund_price_data`

Fetch daily TEFAS mutual fund NAV prices for a fund code.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `fund_code` | `string` | required | TEFAS fund code, e.g. `AFT`, `NNF`, `TCD`. |
| `preset` | `string` | `null` | Preset window: `1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`. |
| `start_date` | `string` | `null` | Start date `YYYY-MM-DD`. Requires `end_date`. |
| `end_date` | `string` | `null` | End date `YYYY-MM-DD`. Requires `start_date`. |
| `current_price` | `boolean` | `false` | Return only the latest NAV price. |

**Returns** — daily price points, opening price, closing price, average price, total return %, and annualized return %.

**Example prompt**
> "What is the 6-month total return for the AFT fund?"

---

### `get_turkey_inflation`

Return Turkey CPI inflation data (Fiyat Endeksi / Tuketici Fiyatlari, 2025=100).

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `period` | `string` | `null` | Single period in `MM-YYYY` or `YYYY-MM` format (e.g. `04-2026`). Cannot be combined with range. |
| `start_period` | `string` | `null` | Inclusive range start in `MM-YYYY` or `YYYY-MM`. Requires `end_period`. |
| `end_period` | `string` | `null` | Inclusive range end in `MM-YYYY` or `YYYY-MM`. Requires `start_period`. |
| `limit` | `integer` | `null` | Return only the latest N records (within the range if given). |

With no arguments, returns the single most recent available period.

**Returns** — monthly and annual CPI percentage changes for each requested period.

**Example prompt**
> "What was Turkey's annual inflation for each month of 2024?"

---

### `compare_asset_returns`

Compare nominal returns across up to 10 mixed-type assets over the same time period.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `assets` | `array` | required | List of `{type, identifier}` objects. `type` is `stock`, `currency`, `gold`, or `fund`. `identifier` is the ticker/pair/code for that type. Max 10 assets. |
| `preset` | `string` | `null` | Preset window: `1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`. |
| `start_date` | `string` | `null` | Start date `YYYY-MM-DD`. Requires `end_date`. |
| `end_date` | `string` | `null` | End date `YYYY-MM-DD`. Requires `start_date`. |

Per-asset fetch failures are returned inline and do not abort the whole call. Results are provided both in input order and ranked by `total_return_percent` descending.

**Asset spec examples**

```json
[
  { "type": "stock",    "identifier": "THYAO"     },
  { "type": "currency", "identifier": "USD/TRY"   },
  { "type": "gold",     "identifier": "gram-altin" },
  { "type": "fund",     "identifier": "AFT"        }
]
```

**Example prompt**
> "Compare the 1-year returns of THYAO, SISE, USD/TRY, gram-gold, and the AFT fund."

---

### `get_real_returns`

Compute the inflation-adjusted (real) return for a single asset using the Fisher equation:

```
real_return = (1 + nominal_return) / (1 + cumulative_inflation) − 1
```

Turkey CPI monthly changes are fetched for the same period and compounded.

**Parameters**

| Name | Type | Default | Description |
|---|---|---|---|
| `asset_type` | `string` | required | `stock`, `currency`, `gold`, or `fund`. |
| `identifier` | `string` | required | Ticker/pair/code matching the asset type (same format as `compare_asset_returns`). |
| `preset` | `string` | `null` | Preset window: `1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`. |
| `start_date` | `string` | `null` | Start date `YYYY-MM-DD`. Requires `end_date`. |
| `end_date` | `string` | `null` | End date `YYYY-MM-DD`. Requires `start_date`. |

**Returns** — `nominal_return_percent`, `cumulative_inflation_percent`, `real_return_percent`, annualized variants of each, a `beat_inflation` flag, and the CPI records used in the calculation.

**Example prompt**
> "Did THYAO beat inflation over the past year in real terms?"

---

### `get_customer_portfolio`

Fetch the customer's current portfolio from the configured backend service.

**Parameters** — none.

The backend endpoint is `GET /api/portfolio` at the URL configured by `PORTFOLIO_BACKEND_BASE_URL` (default: `http://178.105.68.111:6767`).

When presenting portfolio data, the assistant renders holdings and asset-class distributions as semantic HTML tables (not Markdown), with numeric columns right-aligned and Turkish currency/percentage formatting preserved.

**Example prompt**
> "Show me my current portfolio breakdown."

---

## Response Envelope

Every tool returns the same top-level structure:

```json
{
  "ok": true,
  "data": { "...": "..." },
  "error": null
}
```

On failure, `ok` is `false`, `data` is `null`, and `error` contains a structured payload:

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "TICKER_NOT_FOUND",
    "message": "No data returned for INVALID.IS",
    "retryable": false
  }
}
```

---

## Setup

**Requirements:** Python 3.11+ and either `uv` or `pip`.

### Using uv (recommended)

```bash
uv sync --extra dev
```

### Using pip

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `MCP_TRANSPORT` | `streamable-http` | Transport: `stdio`, `sse`, or `streamable-http` |
| `MCP_HOST` | `127.0.0.1` | Bind host for HTTP transports |
| `MCP_PORT` | `8000` | Bind port for HTTP transports |
| `MCP_LOG_LEVEL` | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `YF_BASE_URL` | `https://query2.finance.yahoo.com` | Yahoo Finance API base URL |
| `YF_TIMEOUT_CONNECT_SECONDS` | `3.0` | HTTP connect timeout |
| `YF_TIMEOUT_READ_SECONDS` | `7.0` | HTTP read timeout |
| `YF_TIMEOUT_TOTAL_SECONDS` | `10.0` | Total request timeout |
| `YF_MAX_RETRIES` | `3` | Maximum retry attempts |
| `YF_RETRY_BACKOFF_BASE` | `0.25` | Exponential backoff base (seconds) |
| `YF_USER_AGENT` | `investment-mcp-server/0.1.0` | User-Agent header sent to Yahoo |
| `YF_DEFAULT_INCLUDE_PREPOST` | `false` | Global default for pre/post-market inclusion |
| `PORTFOLIO_BACKEND_BASE_URL` | `http://178.105.68.111:6767` | Portfolio backend origin |
| `PORTFOLIO_BACKEND_TIMEOUT_SECONDS` | `10.0` | Portfolio backend request timeout |

---

## Running the Server

**Streamable HTTP** (default — suitable for remote or HTTP-based MCP clients):

```bash
uv run investment-mcp-server
# Endpoint: https://mcp.aykutbuyukkaya.com/mcp
```

**Custom host/port:**

```bash
MCP_HOST=0.0.0.0 MCP_PORT=9000 uv run investment-mcp-server
```

**stdio** (required for local MCP clients such as Claude Desktop):

```bash
MCP_TRANSPORT=stdio uv run investment-mcp-server
```

**Inspect with MCP Inspector:**

```bash
uv run mcp dev src/investment_mcp_server/server.py
```

---

## Docker

Build and run with streamable HTTP on port 8000:

```bash
docker build -t investment-mcp-server .
docker run -p 8000:8000 investment-mcp-server
```

Override settings at runtime:

```bash
docker run -p 9000:9000 \
  -e MCP_PORT=9000 \
  -e MCP_LOG_LEVEL=DEBUG \
  -e PORTFOLIO_BACKEND_BASE_URL=http://my-backend:6767 \
  investment-mcp-server
```

---

## Development & Testing

Run the test suite:

```bash
uv run pytest
```

Lint and format:

```bash
uv run ruff check .
uv run ruff format .
```

---

## Project Layout

```text
.
├── pyproject.toml
├── Dockerfile
├── .env.example
└── src/
    └── investment_mcp_server/
        ├── server.py            # FastMCP server — tool registration
        ├── settings.py          # Pydantic settings (env vars)
        ├── models.py            # Shared data models
        ├── errors.py            # Error codes and envelope helpers
        ├── parsers.py           # Yahoo Finance response parsers
        ├── stock_client.py      # Yahoo Finance HTTP client
        ├── gold_client.py       # Canli Doviz HTTP client
        ├── fund_client.py       # TEFAS HTTP client
        ├── portfolio_client.py  # Portfolio backend HTTP client
        └── tools/
            ├── stock_quote_metadata.py
            ├── stock_ohlcv_bars.py
            ├── currency_ohlcv_bars.py
            ├── gold_price_data.py
            ├── fund_price_data.py
            ├── turkey_inflation.py
            ├── compare_asset_returns.py
            ├── real_returns.py
            └── customer_portfolio.py
```
