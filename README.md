# Investment MCP Server

Python MCP server for investment workflows. The current server exposes BIST stock market data tools backed by a Yahoo Finance stock provider, using `.IS` ticker normalization for Turkish stock exchange symbols, gold price data backed by direct Canli Doviz provider calls, and fund price data backed by direct TEFAS provider calls.

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

The default transport is `stdio`, which is the usual mode for local MCP clients:

```bash
uv run investment-mcp-server
```

For browser-accessible or service-style development, use streamable HTTP:

```bash
MCP_TRANSPORT=streamable-http uv run investment-mcp-server
```

The streamable HTTP endpoint is available at the SDK default path, typically:

```text
http://localhost:8000/mcp
```

## Tools

The server currently registers these MCP tools:

- `get_stock_quote_metadata`: fetches stock quote metadata for a BIST symbol such as `THYAO` or `THYAO.IS`.
- `get_stock_ohlcv_bars`: fetches stock OHLCV candles for a BIST symbol using either `preset` (`1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`) or an explicit Istanbul-time `start` plus `end` range.
- `get_gold_price_data`: fetches daily gram gold / XAUTRY data directly from Canli Doviz and returns opening, closing, and average prices. Use either `preset` (`1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`) or `start_date` plus `end_date`.
- `get_fund_price_data`: fetches daily TEFAS fund prices for a fund code using either `preset` (`1w`, `1mo`, `3mo`, `6mo`, `1y`, `5y`) or `start_date` plus `end_date`, and returns opening, closing, average, total return, and annualized return.

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
