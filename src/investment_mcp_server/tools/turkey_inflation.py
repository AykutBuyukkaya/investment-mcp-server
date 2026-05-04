"""Turkey consumer price inflation MCP tool implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from investment_mcp_server.errors import InputError, map_exception_to_error_payload

PERIOD_FORMAT = "%m-%Y"
ALT_PERIOD_FORMAT = "%Y-%m"

INFLATION_DATASET = """
04-2026 32.37 4.18
03-2026 30.87 1.94
02-2026 31.53 2.96
01-2026 30.65 4.84
12-2025 30.89 0.89
11-2025 31.07 0.87
10-2025 32.87 2.55
09-2025 33.29 3.23
08-2025 32.95 2.04
07-2025 33.52 2.06
06-2025 35.05 1.37
05-2025 35.41 1.53
04-2025 37.86 3.00
03-2025 38.10 2.46
02-2025 39.05 2.27
01-2025 42.12 5.03
12-2024 44.38 1.03
11-2024 47.09 2.24
10-2024 48.58 2.88
09-2024 49.38 2.97
08-2024 51.97 2.47
07-2024 61.78 3.23
06-2024 71.60 1.64
05-2024 75.45 3.37
04-2024 69.80 3.18
03-2024 68.50 3.16
02-2024 67.07 4.53
01-2024 64.86 6.70
12-2023 64.77 2.93
11-2023 61.98 3.28
10-2023 61.36 3.43
09-2023 61.53 4.75
08-2023 58.94 9.09
07-2023 47.83 9.49
06-2023 38.21 3.92
05-2023 39.59 0.04
04-2023 43.68 2.39
03-2023 50.51 2.29
02-2023 55.18 3.15
01-2023 57.68 6.65
12-2022 64.27 1.18
11-2022 84.39 2.88
10-2022 85.51 3.54
09-2022 83.45 3.08
08-2022 80.21 1.46
07-2022 79.60 2.37
06-2022 78.62 4.95
05-2022 73.50 2.98
04-2022 69.97 7.25
03-2022 61.14 5.46
02-2022 54.44 4.81
01-2022 48.69 11.10
12-2021 36.08 13.58
11-2021 21.31 3.51
10-2021 19.89 2.39
09-2021 19.58 1.25
08-2021 19.25 1.12
07-2021 18.95 1.80
06-2021 17.53 1.94
05-2021 16.59 0.89
04-2021 17.14 1.68
03-2021 16.19 1.08
02-2021 15.61 0.91
01-2021 14.97 1.68
12-2020 14.60 1.25
11-2020 14.03 2.30
10-2020 11.89 2.13
09-2020 11.75 0.97
08-2020 11.77 0.86
07-2020 11.76 0.58
06-2020 12.62 1.13
05-2020 11.39 1.36
04-2020 10.94 0.85
03-2020 11.86 0.57
02-2020 12.37 0.35
01-2020 12.15 1.35
12-2019 11.84 0.74
11-2019 10.56 0.38
10-2019 8.55 2.00
09-2019 9.26 0.99
08-2019 15.01 0.86
07-2019 16.65 1.36
06-2019 15.72 0.03
05-2019 18.71 0.95
04-2019 19.50 1.69
03-2019 19.71 1.03
02-2019 19.67 0.16
01-2019 20.35 1.06
12-2018 20.30 -0.40
11-2018 21.62 -1.44
10-2018 25.24 2.67
09-2018 24.52 6.30
08-2018 17.90 2.30
07-2018 15.85 0.55
06-2018 15.39 2.61
05-2018 12.15 1.62
04-2018 10.85 1.87
03-2018 10.23 0.99
02-2018 10.26 0.73
01-2018 10.35 1.02
12-2017 11.92 0.69
11-2017 12.98 1.49
10-2017 11.90 2.08
09-2017 11.20 0.65
08-2017 10.68 0.52
07-2017 9.79 0.15
06-2017 10.90 -0.27
05-2017 11.72 0.45
04-2017 11.87 1.31
03-2017 11.29 1.02
02-2017 10.13 0.81
01-2017 9.22 2.46
12-2016 8.53 1.64
11-2016 7.00 0.52
10-2016 7.16 1.44
09-2016 7.28 0.18
08-2016 8.05 -0.29
07-2016 8.79 1.16
06-2016 7.64 0.47
05-2016 6.58 0.58
04-2016 6.57 0.78
03-2016 7.46 -0.04
02-2016 8.78 -0.02
01-2016 9.58 1.82
12-2015 8.81 0.21
11-2015 8.10 0.67
10-2015 7.58 1.55
09-2015 7.95 0.89
08-2015 7.14 0.40
07-2015 6.81 0.09
06-2015 7.20 -0.51
05-2015 8.09 0.56
04-2015 7.91 1.63
03-2015 7.61 1.19
02-2015 7.55 0.71
01-2015 7.24 1.10
12-2014 8.17 -0.44
11-2014 9.15 0.18
10-2014 8.96 1.90
09-2014 8.86 0.14
08-2014 9.54 0.09
07-2014 9.32 0.45
06-2014 9.16 0.31
05-2014 9.66 0.40
04-2014 9.38 1.34
03-2014 8.39 1.13
02-2014 7.89 0.43
01-2014 7.75 1.98
12-2013 7.4 0.46
11-2013 7.32 0.01
10-2013 7.71 1.80
09-2013 7.88 0.77
08-2013 8.17 -0.10
07-2013 8.88 0.31
06-2013 8.30 0.76
05-2013 6.51 0.15
04-2013 6.13 0.42
03-2013 7.29 0.66
02-2013 7.03 0.30
01-2013 7.31 1.65
12-2012 6.16 0.38
11-2012 6.37 0.38
10-2012 7.80 1.96
09-2012 9.19 1.03
08-2012 8.88 0.56
07-2012 9.07 -0.23
06-2012 8.87 -0.90
05-2012 8.28 -0.21
04-2012 11.14 1.52
03-2012 10.43 0.41
02-2012 10.43 0.56
01-2012 10.61 0.56
12-2011 10.45 0.58
11-2011 9.48 1.73
10-2011 7.66 3.27
09-2011 6.15 0.75
08-2011 6.65 0.73
07-2011 6.31 -0.41
06-2011 6.24 -1.43
05-2011 7.17 2.42
04-2011 4.26 0.87
03-2011 3.99 0.42
02-2011 4.16 0.73
01-2011 4.90 0.41
12-2010 6.40 -0.30
11-2010 7.29 0.03
10-2010 8.62 1.83
09-2010 9.24 1.23
08-2010 8.33 0.40
07-2010 7.58 -0.48
06-2010 8.37 -0.56
05-2010 9.10 -0.36
04-2010 10.19 0.60
03-2010 9.56 0.58
02-2010 10.13 1.45
01-2010 8.19 1.85
12-2009 6.53 0.53
11-2009 5.53 1.27
10-2009 5.08 2.41
09-2009 5.27 0.39
08-2009 5.33 -0.30
07-2009 5.39 0.25
06-2009 5.73 0.11
05-2009 5.24 0.64
04-2009 6.13 0.02
03-2009 7.89 1.10
02-2009 7.73 -0.34
01-2009 9.50 0.29
12-2008 10.06 -0.41
11-2008 10.76 0.83
10-2008 11.99 2.60
09-2008 11.13 0.45
08-2008 11.77 -0.24
07-2008 12.06 0.58
06-2008 10.61 -0.36
05-2008 10.74 1.49
04-2008 9.66 1.68
03-2008 9.15 0.96
02-2008 9.10 1.29
01-2008 8.17 0.80
12-2007 8.39 0.22
11-2007 8.40 1.95
10-2007 7.70 1.81
09-2007 7.12 1.03
08-2007 7.39 0.02
07-2007 6.90 -0.73
06-2007 8.60 -0.24
05-2007 9.23 0.50
04-2007 10.72 1.21
03-2007 10.86 0.92
02-2007 10.16 0.43
01-2007 9.93 1.00
12-2006 9.65 0.23
11-2006 9.86 1.29
10-2006 9.98 1.27
09-2006 10.55 1.29
08-2006 10.26 -0.44
07-2006 11.69 0.85
06-2006 10.12 0.34
05-2006 9.86 1.88
04-2006 8.83 1.34
03-2006 8.16 0.27
02-2006 8.15 0.22
01-2006 7.93 0.75
12-2005 7.72 0.42
11-2005 7.61 1.40
10-2005 7.52 1.79
09-2005 7.99 1.02
08-2005 7.91 0.85
07-2005 7.82 -0.57
06-2005 8.95 0.10
05-2005 8.70 0.92
04-2005 8.18 0.71
03-2005 7.94 0.26
02-2005 8.69 0.02
01-2005 9.24 0.55
""".strip()


@dataclass(frozen=True, slots=True)
class TurkeyInflationPoint:
    period: str
    annual_percent: float
    monthly_percent: float

    @property
    def year(self) -> int:
        return int(self.period[3:])

    @property
    def month(self) -> int:
        return int(self.period[:2])

    @property
    def sort_key(self) -> tuple[int, int]:
        return self.year, self.month

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "year": self.year,
            "month": self.month,
            "annual_percent": self.annual_percent,
            "monthly_percent": self.monthly_percent,
        }


def _make_success_response(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "data": data, "error": None}


def _make_error_response(exc: Exception) -> dict[str, Any]:
    payload = map_exception_to_error_payload(exc)
    return {"ok": False, "data": None, "error": payload.to_dict()}


def _parse_dataset(raw_data: str) -> list[TurkeyInflationPoint]:
    points: list[TurkeyInflationPoint] = []
    for row in raw_data.splitlines():
        period, annual_percent, monthly_percent = row.split()
        points.append(
            TurkeyInflationPoint(
                period=period,
                annual_percent=float(annual_percent),
                monthly_percent=float(monthly_percent),
            )
        )
    return points


INFLATION_POINTS = _parse_dataset(INFLATION_DATASET)
INFLATION_BY_PERIOD = {point.period: point for point in INFLATION_POINTS}
LATEST_INFLATION_POINT = max(INFLATION_POINTS, key=lambda point: point.sort_key)
EARLIEST_INFLATION_POINT = min(INFLATION_POINTS, key=lambda point: point.sort_key)


def _normalize_period(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field_name} must be a non-empty period string")

    cleaned = value.strip()
    for date_format in (PERIOD_FORMAT, ALT_PERIOD_FORMAT):
        try:
            return datetime.strptime(cleaned, date_format).strftime(PERIOD_FORMAT)
        except ValueError:
            continue

    raise InputError(
        f"Invalid {field_name} '{value}'. Expected format: MM-YYYY or YYYY-MM"
    )


def _validate_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if not isinstance(limit, int) or limit <= 0:
        raise InputError("limit must be a positive integer when set")
    return limit


def _dataset_metadata() -> dict[str, Any]:
    return {
        "source": "provided_static_dataset",
        "country": "Turkey",
        "indicator": "Fiyat Endeksi (Tuketici Fiyatlari)",
        "index_base": "2025=100",
        "frequency": "monthly",
        "earliest_period": EARLIEST_INFLATION_POINT.period,
        "latest_period": LATEST_INFLATION_POINT.period,
    }


def _period_or_error(period: str) -> TurkeyInflationPoint:
    point = INFLATION_BY_PERIOD.get(period)
    if point is None:
        raise InputError(
            f"No Turkey inflation data is available for period '{period}'",
            details=_dataset_metadata(),
        )
    return point


async def execute_get_turkey_inflation(
    *,
    period: str | None = None,
    start_period: str | None = None,
    end_period: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Return Turkey CPI inflation data in a standard envelope."""
    try:
        normalized_period = _normalize_period(period, field_name="period")
        normalized_start_period = _normalize_period(start_period, field_name="start_period")
        normalized_end_period = _normalize_period(end_period, field_name="end_period")
        normalized_limit = _validate_limit(limit)

        has_range = normalized_start_period is not None or normalized_end_period is not None
        if normalized_period is not None and has_range:
            raise InputError("period cannot be combined with start_period or end_period")
        if (normalized_start_period is None) != (normalized_end_period is None):
            raise InputError("start_period and end_period must be provided together")

        if normalized_period is not None:
            point = _period_or_error(normalized_period)
            return _make_success_response(
                {
                    **_dataset_metadata(),
                    "period": point.period,
                    "annual_percent": point.annual_percent,
                    "monthly_percent": point.monthly_percent,
                    "records": [point.to_dict()],
                    "record_count": 1,
                }
            )

        if has_range:
            assert normalized_start_period is not None
            assert normalized_end_period is not None
            start_point = _period_or_error(normalized_start_period)
            end_point = _period_or_error(normalized_end_period)
            if end_point.sort_key < start_point.sort_key:
                raise InputError("end_period must be greater than or equal to start_period")

            records = [
                point
                for point in sorted(INFLATION_POINTS, key=lambda item: item.sort_key)
                if start_point.sort_key <= point.sort_key <= end_point.sort_key
            ]
            if normalized_limit is not None:
                records = records[-normalized_limit:]

            return _make_success_response(
                {
                    **_dataset_metadata(),
                    "start_period": normalized_start_period,
                    "end_period": normalized_end_period,
                    "records": [point.to_dict() for point in records],
                    "record_count": len(records),
                }
            )

        records = [LATEST_INFLATION_POINT]
        if normalized_limit is not None:
            records = sorted(INFLATION_POINTS, key=lambda item: item.sort_key)[-normalized_limit:]

        latest = records[-1]
        return _make_success_response(
            {
                **_dataset_metadata(),
                "period": latest.period,
                "annual_percent": latest.annual_percent,
                "monthly_percent": latest.monthly_percent,
                "records": [point.to_dict() for point in records],
                "record_count": len(records),
            }
        )
    except Exception as exc:
        return _make_error_response(exc)
