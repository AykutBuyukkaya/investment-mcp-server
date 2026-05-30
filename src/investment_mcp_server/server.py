import asyncio
import logging
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from investment_mcp_server.settings import Settings
from investment_mcp_server.fund_client import DirectFundClient
from investment_mcp_server.gold_client import DirectGoldClient
from investment_mcp_server.rate_limiter import RateLimiter
from investment_mcp_server.portfolio_client import BackendPortfolioClient
from investment_mcp_server.tools.customer_portfolio import PortfolioClient
from investment_mcp_server.tools.customer_portfolio import execute_get_customer_portfolio
from investment_mcp_server.tools.fund_price_data import FundPriceClient
from investment_mcp_server.tools.fund_price_data import execute_get_fund_price_data
from investment_mcp_server.tools.gold_price_data import execute_get_gold_price_data
from investment_mcp_server.tools.gold_price_data import GoldPriceClient
from investment_mcp_server.tools.currency_ohlcv_bars import execute_get_currency_ohlcv_bars
from investment_mcp_server.tools.stock_ohlcv_bars import execute_get_stock_ohlcv_bars
from investment_mcp_server.tools.stock_quote_metadata import execute_get_stock_quote_metadata
from investment_mcp_server.tools.turkey_inflation import execute_get_turkey_inflation
from investment_mcp_server.tools.compare_asset_returns import execute_compare_asset_returns
from investment_mcp_server.tools.real_returns import execute_get_real_returns
from investment_mcp_server.stock_client import YahooStockClient

Transport = Literal["stdio", "sse", "streamable-http"]

LOGGER = logging.getLogger(__name__)


def create_server(
    stock_client: YahooStockClient | None = None,
    gold_client: GoldPriceClient | None = None,
    fund_client: FundPriceClient | None = None,
    portfolio_client: PortfolioClient | None = None,
    settings: Settings | None = None,
) -> FastMCP:
    """Create the MCP server and register all tools/resources/prompts."""
    resolved_settings = settings or Settings()
    resolved_stock_client = stock_client or YahooStockClient(settings=resolved_settings)
    resolved_gold_client = gold_client or DirectGoldClient(
        rate_limiter=RateLimiter.from_rps(resolved_settings.gold_rate_limit_rps)
    )
    resolved_fund_client = fund_client or DirectFundClient(
        rate_limiter=RateLimiter.from_rps(resolved_settings.fund_rate_limit_rps)
    )
    resolved_portfolio_client = portfolio_client or BackendPortfolioClient(settings=resolved_settings)

    mcp = FastMCP(
        name="investment-mcp-server",
        instructions=(
            "Investment MCP server with BIST market data tools backed by Yahoo Finance "
            "plus Yahoo Finance foreign currency data, direct Canli Doviz gold data, and "
            "direct TEFAS fund data, static Turkey CPI inflation data, plus a local "
            "customer portfolio backend integration. "
            "BIST tickers are normalized to Yahoo's .IS suffix. "
            "When presenting customer portfolio data to a user, render portfolio holdings "
            "and asset-class distributions as semantic HTML tables using table, thead, "
            "tbody, tr, th, and td elements. Do not render portfolio tables as Markdown. "
            "Right-align numeric cells and keep Turkish currency/percentage formatting."
        ),
        log_level=resolved_settings.log_level,
        host=resolved_settings.host,
        port=resolved_settings.port,
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(
        name="get_stock_quote_metadata",
        description=(
            "Fetch high-level stock quote metadata for a BIST equity from Yahoo Finance chart API. "
            "Use this when you need symbol-level context such as currency, exchange, regular "
            "market price, 52-week high/low, previous close, volume, timezone, and granularity. "
            "Returns a standard envelope: {ok, data, error}."
        ),
    )
    async def get_stock_quote_metadata(
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
        current_price: bool = Field(
            default=False,
            description=(
                "If true, returns the current/latest price directly instead of the full metadata "
                "payload."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_get_stock_quote_metadata(
            resolved_stock_client,
            ticker=ticker,
            include_prepost=include_prepost,
            current_price=current_price,
        )

    @mcp.tool(
        name="get_stock_ohlcv_bars",
        description=(
            "Fetch time-series stock OHLCV candles for a BIST symbol from Yahoo Finance. Supports "
            "preset windows (1w, 1mo, 3mo, 6mo, 1y, 5y) or explicit Istanbul-time start/end, "
            "strict alignment checks, null-bar filtering, optional output limiting, and current "
            "price mode. Returns a standard envelope: {ok, data, error}."
        ),
    )
    async def get_stock_ohlcv_bars(
        ticker: str = Field(
            description=(
                "Target BIST symbol. Accepts THYAO or THYAO.IS. The value is normalized to "
                "uppercase with .IS suffix before querying Yahoo."
            )
        ),
        start: str | None = Field(
            default=None,
            description=(
                "Optional start datetime in format dd.mm.yyyy hh.MM using Europe/Istanbul "
                "timezone. Must be supplied with end and cannot be combined with preset. "
                "Example: 01.01.2024 09.30"
            )
        ),
        end: str | None = Field(
            default=None,
            description=(
                "Optional end datetime in format dd.mm.yyyy hh.MM using Europe/Istanbul "
                "timezone. Must be supplied with start and cannot be combined with preset. "
                "Example: 31.01.2024 18.00"
            )
        ),
        preset: str | None = Field(
            default=None,
            description=(
                "Optional preset window. Supported values: 1w, 1mo, 3mo, 6mo, 1y, 5y. "
                "Cannot be combined with start/end."
            ),
        ),
        interval: str = Field(
            default="1d",
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
                "Optional maximum number of latest bars to include. Must be greater than 0 "
                "when set."
            ),
        ),
        current_price: bool = Field(
            default=False,
            description=(
                "If true, returns the current/latest price for the symbol. When true, preset, "
                "start, and end are ignored and are not required."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_get_stock_ohlcv_bars(
            resolved_stock_client,
            ticker=ticker,
            start=start,
            end=end,
            preset=preset,
            interval=interval,
            include_prepost=include_prepost,
            include_null_bars=include_null_bars,
            strict_alignment=strict_alignment,
            limit=limit,
            current_price=current_price,
        )

    @mcp.tool(
        name="get_currency_ohlcv_bars",
        description=(
            "Fetch time-series foreign currency OHLCV candles from Yahoo Finance. Supports "
            "pairs like USD/TRY, USDTRY, EUR/TRY, EURTRY, or direct Yahoo FX symbols like "
            "TRY=X and EURTRY=X. Supports preset windows (1w, 1mo, 3mo, 6mo, 1y, 5y) or "
            "explicit Istanbul-time start/end, null-bar filtering, and optional output "
            "limiting, plus current price mode. Returns a standard envelope: {ok, data, error}."
        ),
    )
    async def get_currency_ohlcv_bars(
        pair: str = Field(
            description=(
                "Target currency pair. Accepts slash form such as USD/TRY, compact form "
                "such as EURTRY, or Yahoo symbols such as TRY=X and EURTRY=X."
            )
        ),
        start: str | None = Field(
            default=None,
            description=(
                "Optional start datetime in format dd.mm.yyyy hh.MM using Europe/Istanbul "
                "timezone. Must be supplied with end and cannot be combined with preset. "
                "Example: 01.01.2024 09.30"
            )
        ),
        end: str | None = Field(
            default=None,
            description=(
                "Optional end datetime in format dd.mm.yyyy hh.MM using Europe/Istanbul "
                "timezone. Must be supplied with start and cannot be combined with preset. "
                "Example: 31.01.2024 18.00"
            )
        ),
        preset: str | None = Field(
            default=None,
            description=(
                "Optional preset window. Supported values: 1w, 1mo, 3mo, 6mo, 1y, 5y. "
                "Cannot be combined with start/end."
            ),
        ),
        interval: str = Field(
            default="1d",
            description=(
                "Requested candle granularity. Supported values include 1m, 5m, 15m, 1h, 1d, "
                "1wk, and 1mo. Use values Yahoo supports for the requested time span."
            )
        ),
        include_prepost: bool = Field(
            default=True,
            description=(
                "If true, requests pre/post periods from Yahoo. This defaults to true for FX "
                "to match Yahoo chart requests commonly used for currency pairs."
            ),
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
                "Optional maximum number of latest bars to include. Must be greater than 0 "
                "when set."
            ),
        ),
        current_price: bool = Field(
            default=False,
            description=(
                "If true, returns the current/latest price for the currency pair. When true, "
                "preset, start, and end are ignored and are not required."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_get_currency_ohlcv_bars(
            resolved_stock_client,
            pair=pair,
            start=start,
            end=end,
            preset=preset,
            interval=interval,
            include_prepost=include_prepost,
            include_null_bars=include_null_bars,
            strict_alignment=strict_alignment,
            limit=limit,
            current_price=current_price,
        )

    @mcp.tool(
        name="get_gold_price_data",
        description=(
            "Fetch daily gold price data with direct Canli Doviz provider "
            "calls. Supports gram-altin / XAUTRY only and returns opening, closing, and "
            "average prices. Provide either a preset (1w, 1mo, 3mo, 6mo, 1y, 5y) or a "
            "start_date/end_date range, or set current_price=true for the latest price. "
            "Returns a standard envelope: {ok, data, error}."
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
        current_price: bool = Field(
            default=False,
            description=(
                "If true, returns the current/latest gold price. When true, preset, "
                "start_date, and end_date are ignored and are not required."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_get_gold_price_data(
            resolved_gold_client,
            asset=asset,
            preset=preset,
            start_date=start_date,
            end_date=end_date,
            current_price=current_price,
        )

    @mcp.tool(
        name="get_fund_price_data",
        description=(
            "Fetch daily TEFAS mutual fund price data for a fund code over a date range. "
            "Accepts the same preset windows as gold and stocks (1w, 1mo, 3mo, 6mo, 1y, 5y) "
            "or explicit start_date/end_date, or set current_price=true for the latest price. "
            "Returns price points plus opening, closing, average, total return, and "
            "annualized return in the standard envelope: {ok, data, error}."
        ),
    )
    async def get_fund_price_data(
        fund_code: str = Field(
            description="TEFAS fund code, for example AFT, NNF, or TCD.",
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
            description=(
                "Optional start date in YYYY-MM-DD format. Must be supplied with end_date and "
                "cannot be combined with preset."
            ),
        ),
        end_date: str | None = Field(
            default=None,
            description=(
                "Optional end date in YYYY-MM-DD format. Must be supplied with start_date and "
                "cannot be combined with preset."
            ),
        ),
        current_price: bool = Field(
            default=False,
            description=(
                "If true, returns the current/latest fund price. When true, preset, "
                "start_date, and end_date are ignored and are not required."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_get_fund_price_data(
            resolved_fund_client,
            fund_code=fund_code,
            preset=preset,
            start_date=start_date,
            end_date=end_date,
            current_price=current_price,
        )

    @mcp.tool(
        name="get_turkey_inflation",
        description=(
            "Return Turkey CPI inflation data from the supplied static dataset "
            "(Fiyat Endeksi / Tuketici Fiyatlari, 2025=100). Returns annual and monthly "
            "percentage changes. With no period arguments, returns the latest available "
            "period. Use period for a single month or start_period/end_period for an "
            "inclusive range. Accepted period formats: MM-YYYY or YYYY-MM. Returns a "
            "standard envelope: {ok, data, error}."
        ),
    )
    async def get_turkey_inflation(
        period: str | None = Field(
            default=None,
            description=(
                "Optional single inflation period in MM-YYYY or YYYY-MM format. "
                "Example: 04-2026 or 2026-04. Cannot be combined with start_period/end_period."
            ),
        ),
        start_period: str | None = Field(
            default=None,
            description=(
                "Optional inclusive range start period in MM-YYYY or YYYY-MM format. "
                "Must be supplied with end_period and cannot be combined with period."
            ),
        ),
        end_period: str | None = Field(
            default=None,
            description=(
                "Optional inclusive range end period in MM-YYYY or YYYY-MM format. "
                "Must be supplied with start_period and cannot be combined with period."
            ),
        ),
        limit: int | None = Field(
            default=None,
            description=(
                "Optional maximum number of latest records to include. When used with a "
                "range, limits to the latest records within that range. Must be greater "
                "than 0 when set."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_get_turkey_inflation(
            period=period,
            start_period=start_period,
            end_period=end_period,
            limit=limit,
        )

    @mcp.tool(
        name="compare_asset_returns",
        description=(
            "Compare nominal returns across multiple assets (BIST stocks, currency pairs, gold, "
            "TEFAS funds) over a shared time period. Accepts up to 10 assets as a list of "
            "{'type': ..., 'identifier': ...} specs where type is one of: stock, currency, gold, "
            "fund. Uses either a preset window (1w, 1mo, 3mo, 6mo, 1y, 5y) or an explicit "
            "start_date/end_date range in YYYY-MM-DD format. Per-asset failures are returned "
            "inline without failing the whole call. Results are returned both in input order and "
            "ranked by total_return_percent descending. Returns a standard envelope: "
            "{ok, data, error}."
        ),
    )
    async def compare_asset_returns(
        assets: list[dict[str, str]] = Field(
            description=(
                "List of asset specs to compare. Each spec must have 'type' (stock, currency, "
                "gold, or fund) and 'identifier' (BIST ticker like THYAO, currency pair like "
                "USD/TRY, gold asset like gram-altin, or TEFAS fund code like AFT). "
                "Example: [{\"type\": \"stock\", \"identifier\": \"THYAO\"}, "
                "{\"type\": \"fund\", \"identifier\": \"AFT\"}]"
            )
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
            description=(
                "Optional start date in YYYY-MM-DD format. Must be supplied with end_date and "
                "cannot be combined with preset."
            ),
        ),
        end_date: str | None = Field(
            default=None,
            description=(
                "Optional end date in YYYY-MM-DD format. Must be supplied with start_date and "
                "cannot be combined with preset."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_compare_asset_returns(
            resolved_stock_client,
            resolved_gold_client,
            resolved_fund_client,
            assets=assets,
            preset=preset,
            start_date=start_date,
            end_date=end_date,
        )

    @mcp.tool(
        name="get_real_returns",
        description=(
            "Compute inflation-adjusted (real) return for a single asset over a time period. "
            "Fetches the asset's price history and compounds Turkey CPI monthly changes for the "
            "same period, then applies the Fisher equation: "
            "real_return = (1 + nominal) / (1 + cumulative_inflation) - 1. "
            "Supported asset types: stock (BIST via Yahoo Finance), currency (FX via Yahoo "
            "Finance), gold (gram-altin via Canli Doviz), fund (TEFAS). "
            "Use preset (1w, 1mo, 3mo, 6mo, 1y, 5y) or explicit start_date/end_date. "
            "Returns nominal_return_percent, cumulative_inflation_percent, real_return_percent, "
            "annualized variants, beat_inflation flag, and the CPI records used. "
            "Returns a standard envelope: {ok, data, error}."
        ),
    )
    async def get_real_returns(
        asset_type: str = Field(
            description=(
                "Type of asset. One of: stock, currency, gold, fund."
            )
        ),
        identifier: str = Field(
            description=(
                "Asset identifier. For stock: BIST ticker like THYAO or THYAO.IS. "
                "For currency: pair like USD/TRY, USDTRY, or Yahoo symbol like TRY=X. "
                "For gold: gram-altin (or aliases: gram, XAUTRY). "
                "For fund: TEFAS fund code like AFT or NNF."
            )
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
            description=(
                "Optional start date in YYYY-MM-DD format. Must be supplied with end_date and "
                "cannot be combined with preset."
            ),
        ),
        end_date: str | None = Field(
            default=None,
            description=(
                "Optional end date in YYYY-MM-DD format. Must be supplied with start_date and "
                "cannot be combined with preset."
            ),
        ),
    ) -> dict[str, Any]:
        return await execute_get_real_returns(
            resolved_stock_client,
            resolved_gold_client,
            resolved_fund_client,
            asset_type=asset_type,
            identifier=identifier,
            preset=preset,
            start_date=start_date,
            end_date=end_date,
        )

    @mcp.tool(
        name="get_customer_portfolio",
        description=(
            "Fetch the customer's current dummy portfolio from the local backend service at "
            "/api/portfolio. The backend is expected to be reachable from the MCP server. "
            "Returns the backend portfolio payload in the standard envelope: "
            "{ok, data, error}. When using this data in an assistant response, present "
            "portfolio holdings and asset-class summaries as semantic HTML tables, not "
            "Markdown tables, with numeric columns right-aligned."
        ),
    )
    async def get_customer_portfolio() -> dict[str, Any]:
        return await execute_get_customer_portfolio(resolved_portfolio_client)

    @mcp.resource("config://server")
    def server_config() -> dict[str, str]:
        """Expose minimal server metadata."""
        return {
            "name": "investment-mcp-server",
            "version": "0.1.0",
            "status": "ready",
            "stock_data_provider": "Yahoo Finance",
            "currency_data_provider": "Yahoo Finance",
            "gold_data_provider": "Canli Doviz",
            "fund_data_provider": "TEFAS",
            "turkey_inflation_data_provider": "Provided static CPI dataset",
            "portfolio_data_provider": "Local portfolio backend",
            "market": "BIST, foreign currencies, gold, funds, Turkey inflation, customer portfolio, multi-asset comparison, real returns",
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


def _close_stock_client_sync(client: YahooStockClient) -> None:
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

    stock_client = YahooStockClient(settings=settings)
    gold_client = DirectGoldClient(
        rate_limiter=RateLimiter.from_rps(settings.gold_rate_limit_rps)
    )
    fund_client = DirectFundClient(
        rate_limiter=RateLimiter.from_rps(settings.fund_rate_limit_rps)
    )
    portfolio_client = BackendPortfolioClient(settings=settings)
    server = create_server(
        stock_client=stock_client,
        gold_client=gold_client,
        fund_client=fund_client,
        portfolio_client=portfolio_client,
        settings=settings,
    )

    LOGGER.info("Starting investment MCP server on %s transport", transport)
    try:
        server.run(transport=transport)
    finally:
        _close_stock_client_sync(stock_client)
        _close_gold_client_sync(gold_client)
        _close_gold_client_sync(fund_client)
        _close_gold_client_sync(portfolio_client)
        LOGGER.info("Stock HTTP client closed")


def _validate_transport(value: str) -> Transport:
    allowed: set[Transport] = {"stdio", "sse", "streamable-http"}
    if value in allowed:
        return value  # type: ignore[return-value]

    options = ", ".join(sorted(allowed))
    raise ValueError(f"Unsupported MCP transport '{value}'. Expected one of: {options}.")


mcp = create_server()


if __name__ == "__main__":
    main()
