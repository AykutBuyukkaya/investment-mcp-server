"""Typed data models used by parsers and MCP tool responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class QuoteMeta:
    currency: str | None = None
    symbol: str | None = None
    exchange_name: str | None = None
    regular_market_price: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    regular_market_volume: int | None = None
    previous_close: float | None = None
    timezone: str | None = None
    data_granularity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "symbol": self.symbol,
            "exchangeName": self.exchange_name,
            "regularMarketPrice": self.regular_market_price,
            "fiftyTwoWeekHigh": self.fifty_two_week_high,
            "fiftyTwoWeekLow": self.fifty_two_week_low,
            "regularMarketVolume": self.regular_market_volume,
            "previousClose": self.previous_close,
            "timezone": self.timezone,
            "dataGranularity": self.data_granularity,
        }


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp: int
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None

    @property
    def datetime_utc(self) -> str:
        return datetime.fromtimestamp(self.timestamp, tz=timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "datetime_utc": self.datetime_utc,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass(frozen=True, slots=True)
class GoldHistoricalBar:
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
        }


@dataclass(frozen=True, slots=True)
class GoldPriceSummary:
    asset: str
    currency: str
    opening_price: float
    closing_price: float
    average_price: float
    start_date: str
    end_date: str
    bar_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "currency": self.currency,
            "opening_price": self.opening_price,
            "closing_price": self.closing_price,
            "average_price": self.average_price,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "bar_count": self.bar_count,
        }


@dataclass(frozen=True, slots=True)
class FundPricePoint:
    date: str
    price: float
    fund_code: str | None = None
    fund_name: str | None = None
    outstanding_shares: float | None = None
    investor_count: int | None = None
    portfolio_size: float | None = None
    exchange_bulletin_price: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "price": self.price,
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "outstanding_shares": self.outstanding_shares,
            "investor_count": self.investor_count,
            "portfolio_size": self.portfolio_size,
            "exchange_bulletin_price": self.exchange_bulletin_price,
        }


@dataclass(frozen=True, slots=True)
class FundPriceSummary:
    fund_code: str
    fund_name: str | None
    opening_price: float
    closing_price: float
    average_price: float
    total_return_percent: float | None
    annualized_return_percent: float | None
    start_date: str
    end_date: str
    point_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "fund_code": self.fund_code,
            "fund_name": self.fund_name,
            "opening_price": self.opening_price,
            "closing_price": self.closing_price,
            "average_price": self.average_price,
            "total_return_percent": self.total_return_percent,
            "annualized_return_percent": self.annualized_return_percent,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "point_count": self.point_count,
        }


@dataclass(frozen=True, slots=True)
class SessionPeriod:
    timezone: str | None = None
    start: int | None = None
    end: int | None = None
    gmtoffset: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "timezone": self.timezone,
            "start": self.start,
            "end": self.end,
            "gmtoffset": self.gmtoffset,
        }


@dataclass(frozen=True, slots=True)
class MarketSessionInfo:
    timezone: str | None
    current_trading_period: dict[str, SessionPeriod | None]
    trading_periods: list[list[SessionPeriod]] | None = None

    def to_dict(self) -> dict[str, Any]:
        current = {
            "pre": self.current_trading_period.get("pre").to_dict()
            if self.current_trading_period.get("pre")
            else None,
            "regular": self.current_trading_period.get("regular").to_dict()
            if self.current_trading_period.get("regular")
            else None,
            "post": self.current_trading_period.get("post").to_dict()
            if self.current_trading_period.get("post")
            else None,
        }

        trading_periods_payload: list[list[dict[str, Any]]] | None = None
        if self.trading_periods is not None:
            trading_periods_payload = [
                [session.to_dict() for session in daily_sessions]
                for daily_sessions in self.trading_periods
            ]

        return {
            "timezone": self.timezone,
            "currentTradingPeriod": current,
            "tradingPeriods": trading_periods_payload,
        }
