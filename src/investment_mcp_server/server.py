import asyncio
import logging
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from investment_mcp_server.settings import Settings
from investment_mcp_server.gold_client import DirectGoldClient
from investment_mcp_server.tools.gold_price_data import execute_get_gold_price_data
from investment_mcp_server.tools.gold_price_data import GoldPriceClient
from investment_mcp_server.tools.ohlcv_bars import execute_get_ohlcv_bars
from investment_mcp_server.tools.quote_metadata import execute_get_quote_metadata
from investment_mcp_server.yahoo_client import YahooClient

Transport = Literal["stdio", "sse", "streamable-http"]

LOGGER = logging.getLogger(__name__)


def create_server(
    yahoo_client: YahooClient | None = None,
    gold_client: GoldPriceClient | None = None,
    settings: Settings | None = None,
) -> FastMCP:
    """Create the MCP server and register all tools/resources/prompts."""
    resolved_settings = settings or Settings()
    client = yahoo_client or YahooClient(settings=resolved_settings)
    resolved_gold_client = gold_client or DirectGoldClient()

    mcp = FastMCP(
        name="investment-mcp-server",
        instructions=(
            "Investment MCP server with BIST market data tools backed by Yahoo Finance "
            "and gold price data backed by direct Canli Doviz provider calls. BIST tickers "
            "are normalized to Yahoo's .IS suffix."
        ),
        log_level=resolved_settings.log_level,
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(
        name="get_quote_metadata",
        description=(
            "Fetch high-level quote metadata for a BIST equity from Yahoo Finance chart API. "
            "Use this when you need symbol-level context such as currency, exchange, regular "
            "market price, 52-week high/low, previous close, volume, timezone, and granularity. "
            "Returns a standard envelope: {ok, data, error}."
        ),
    )
    async def get_quote_metadata(
        ticker: str = Field(
            description=(
                "Target BIST symbol. Accepts base symbol, e.g. THYAO, or explicit .IS symbol, "
                "e.g. THYAO.IS. The server normalizes to uppercase and ensures .IS suffix."
            )
        ),
        include_prepost: bool = Field(
            default=False,
            description=(
                "If true, asks Yahoo to include pre-market and post-market periods when available."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_get_quote_metadata(
            client,
            ticker=ticker,
            include_prepost=include_prepost,
        )

    @mcp.tool(
        name="get_ohlcv_bars",
        description=(
            "Fetch time-series OHLCV candles for a BIST symbol from Yahoo Finance. Supports "
            "strict alignment checks, null-bar filtering, and optional output limiting. Returns "
            "bars with Unix timestamp and ISO UTC datetime in a standard envelope: {ok, data, error}."
        ),
    )
    async def get_ohlcv_bars(
        ticker: str = Field(
            description=(
                "Target BIST symbol. Accepts THYAO or THYAO.IS. The value is normalized to "
                "uppercase with .IS suffix before querying Yahoo."
            )
        ),
        start: str = Field(
            description=(
                "Start datetime in format dd.mm.yyyy hh.MM using Europe/Istanbul timezone. "
                "Example: 01.01.2024 09.30"
            )
        ),
        end: str = Field(
            description=(
                "End datetime in format dd.mm.yyyy hh.MM using Europe/Istanbul timezone. "
                "Must be later than start. Example: 31.01.2024 18.00"
            )
        ),
        interval: str = Field(
            description=(
                "Requested candle granularity. Supported values include 1m, 5m, 15m, 1h, 1d, "
                "1wk, and 1mo. Use values Yahoo supports for the requested time span."
            )
        ),
        include_prepost: bool = Field(
            default=False,
            description="If true, requests pre/post session candles when Yahoo provides them.",
        ),
        include_null_bars: bool = Field(
            default=False,
            description=(
                "If false, bars containing any null OHLCV value are dropped and counted in "
                "dropped_null_bar_count."
            ),
        ),
        strict_alignment: bool = Field(
            default=True,
            description=(
                "If true, returns DATA_ALIGNMENT_ERROR when timestamp/open/high/low/close/volume "
                "array lengths differ."
            ),
        ),
        limit: int | None = Field(
            default=None,
            description=(
                "Optional maximum number of latest bars to include. Must be greater than 0 when set."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_get_ohlcv_bars(
            client,
            ticker=ticker,
            start=start,
            end=end,
            interval=interval,
            include_prepost=include_prepost,
            include_null_bars=include_null_bars,
            strict_alignment=strict_alignment,
            limit=limit,
        )

    @mcp.tool(
        name="get_gold_price_data",
        description=(
            "Fetch daily gold price data with direct Canli Doviz provider "
            "calls. Supports gram-altin / XAUTRY only and returns opening, closing, and "
            "average prices. Provide either a preset (1w, 1mo, 3mo, 6mo, 1y, 5y) or a "
            "start_date/end_date range. Returns a standard envelope: "
            "{ok, data, error}."
        ),
    )
    async def get_gold_price_data(
        asset: str = Field(
            default="gram-altin",
            description=(
                "Gold asset to fetch. Supported canonical value: gram-altin. Common aliases "
                "such as gram, XAUTRY, and XAU-TRY are also accepted."
            ),
        ),
        preset: str | None = Field(
            default=None,
            description=(
                "Optional preset window. Supported values: 1w, 1mo, 3mo, 6mo, 1y, 5y. "
                "Cannot be combined with start_date/end_date."
            ),
        ),
        start_date: str | None = Field(
            default=None,
            description="Optional history start date in YYYY-MM-DD format.",
        ),
        end_date: str | None = Field(
            default=None,
            description="Optional history end date in YYYY-MM-DD format.",
        ),
    ) -> dict[str, Any]:
        return await execute_get_gold_price_data(
            resolved_gold_client,
            asset=asset,
            preset=preset,
            start_date=start_date,
            end_date=end_date,
        )

    @mcp.resource("config://server")
    def server_config() -> dict[str, str]:
        """Expose minimal server metadata."""
        return {
            "name": "investment-mcp-server",
            "version": "0.1.0",
            "status": "ready",
            "market_data_provider": "Yahoo Finance, Canli Doviz",
            "market": "BIST, gold",
        }

    @mcp.prompt()
    def investment_research_prompt(
        topic: str,
        objective: str = "summarize key considerations",
    ) -> str:
        """Create a starter research prompt for future investment workflows."""
        return (
            f"Research the investment topic '{topic}' and {objective}. "
            "Call available MCP tools and resources when useful, and state assumptions clearly."
        )

    return mcp


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _close_yahoo_client_sync(client: YahooClient) -> None:
    try:
        asyncio.run(client.close())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(client.close())
        finally:
            loop.close()


def _close_gold_client_sync(client: GoldPriceClient) -> None:
    close = getattr(client, "close", None)
    if close is None:
        return
    try:
        asyncio.run(close())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(close())
        finally:
            loop.close()


def main() -> None:
    """Run the MCP server."""
    settings = Settings()
    transport = _validate_transport(settings.transport)
    configure_logging(settings.log_level)

    yahoo_client = YahooClient(settings=settings)
    gold_client = DirectGoldClient()
    server = create_server(yahoo_client=yahoo_client, gold_client=gold_client, settings=settings)

    LOGGER.info("Starting investment MCP server on %s transport", transport)
    try:
        server.run(transport=transport)
    finally:
        _close_yahoo_client_sync(yahoo_client)
        _close_gold_client_sync(gold_client)
        LOGGER.info("Yahoo HTTP client closed")


def _validate_transport(value: str) -> Transport:
    allowed: set[Transport] = {"stdio", "sse", "streamable-http"}
    if value in allowed:
        return value  # type: ignore[return-value]

    options = ", ".join(sorted(allowed))
    raise ValueError(f"Unsupported MCP transport '{value}'. Expected one of: {options}.")


mcp = create_server()


if __name__ == "__main__":
    main()
