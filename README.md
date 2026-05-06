# Investment MCP Server

Python MCP server for investment workflows. The current server exposes BIST stock market data tools backed by a Yahoo Finance stock provider, using `.IS` ticker normalization for Turkish stock exchange symbols, foreign currency data backed by Yahoo Finance FX symbols, gold price data backed by direct Canli Doviz provider calls, fund price data backed by direct TEFAS provider calls, and a customer portfolio integration backed by a local backend service.

## Project Layout

```text
.
├── pyproject.toml
├── src/
│   └── investment_mcp_server/
│       ├── __init__.py
│       ├── errors.py
│       ├── fund_client.py
│       ├── gold_client.py
│       ├── models.py
│       ├── parsers.py
│       ├── settings.py
│       ├── server.py
│       ├── stock_client.py
│       └── tools/
│           ├── stock_ohlcv_bars.py
│           └── stock_quote_metadata.py
└── tests/
    └── ...
```

## Setup

Using `uv`:

```bash
uv sync --extra dev
```

Using `pip`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run

The default transport is streamable HTTP:

```bash
uv run investment-mcp-server
```

The streamable HTTP endpoint is available at:

```text
http://localhost:8000/mcp
```

For Docker or another host/port, configure:

```bash
MCP_HOST=0.0.0.0 MCP_PORT=8000 uv run investment-mcp-server
```

If a local MCP client needs stdio, override the transport explicitly:

```bash
MCP_TRANSPORT=stdio uv run investment-mcp-server
```

## Tools

The server currently registers these MCP tools:

- `get_stock_quote_metadata`: fetches stock quote metadata for a BIST symbol such as `THYAO` or `THYAO.IS`. Set `current_price=true` to fetch only the latest price from the metadata response.
- `get_stock_ohlcv_bars`: fetches stock OHLCV candles for a BIST symbol using either `preset` (`1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`) or an explicit Istanbul-time `start` plus `end` range. Set `current_price=true` to fetch only the latest price; in that mode `preset`, `start`, and `end` are not required and are ignored when supplied.
- `get_currency_ohlcv_bars`: fetches foreign currency OHLCV candles from Yahoo Finance using pairs such as `USD/TRY`, `USDTRY`, `EUR/TRY`, or `EURTRY`. Yahoo FX symbols such as `TRY=X` and `EURTRY=X` are also accepted. Use either `preset` (`1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`) or an explicit Istanbul-time `start` plus `end` range. Set `current_price=true` to fetch only the latest price; in that mode `preset`, `start`, and `end` are not required and are ignored when supplied.
- `get_gold_price_data`: fetches daily gram gold / XAUTRY data directly from Canli Doviz and returns opening, closing, and average prices. Use either `preset` (`1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`) or `start_date` plus `end_date`. Set `current_price=true` to fetch only the latest price; in that mode `preset`, `start_date`, and `end_date` are not required and are ignored when supplied.
- `get_fund_price_data`: fetches daily TEFAS fund prices for a fund code using either `preset` (`1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`) or `start_date` plus `end_date`, and returns opening, closing, average, total return, and annualized return. Set `current_price=true` to fetch only the latest price; in that mode `preset`, `start_date`, and `end_date` are not required and are ignored when supplied.
- `get_turkey_inflation`: returns Turkey CPI inflation data from the supplied static dataset (`Fiyat Endeksi / Tuketici Fiyatlari`, 2025=100), including annual and monthly percentage changes. With no arguments it returns the latest available period. Use `period` for one month or `start_period` plus `end_period` for an inclusive range; period formats can be `MM-YYYY` or `YYYY-MM`.
- `get_customer_portfolio`: fetches the customer's current dummy portfolio from the local backend service at `/api/portfolio`. Configure the backend origin with `PORTFOLIO_BACKEND_BASE_URL`, defaulting to `http://localhost:6767`.

Tool responses use this envelope:

```json
{
  "ok": true,
  "data": {},
  "error": null
}
```

On failure, `ok` is `false`, `data` is `null`, and `error` contains a stable code/message/retryable payload.

## Inspect

You can test the server with the MCP Inspector:

```bash
uv run mcp dev src/investment_mcp_server/server.py
```

## Extend

Add domain-specific capabilities in `src/investment_mcp_server/server.py`:

- `@mcp.tool()` for actions the model can call.
- `@mcp.resource()` for readable context/data.
- `@mcp.prompt()` for reusable prompt templates.
