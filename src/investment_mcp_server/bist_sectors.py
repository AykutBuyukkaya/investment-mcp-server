"""Static curated BIST sector ticker groupings.

These lists are a best-effort snapshot of well-known, liquid constituents per
BIST sector and are used only as a convenience default for
``screen_bist_stocks`` when the caller does not supply an explicit
``tickers`` list. They are NOT exhaustive, guaranteed to be current, or free
of delisted/renamed tickers, and a company's "true" sector classification
can be debatable (e.g. conglomerate holdings, glass/chemicals crossovers).
Callers who need authoritative, up-to-date sector membership should consult
Borsa Istanbul's official index constituent lists and pass an explicit
``tickers`` list instead.
"""

from __future__ import annotations

from investment_mcp_server.errors import InputError


BIST_FINANCIALS_TICKERS: tuple[str, ...] = (
    # Banks
    "AKBNK", "GARAN", "ISCTR", "YKBNK", "HALKB", "VAKBN", "TSKB", "ICBCT", "QNBFB", "SKBNK", "ALBRK",
    # Insurance
    "AKGRT", "ANHYT", "ANSGR", "AGESA", "TURSG", "RAYSG",
    # Financial leasing / factoring
    "ISFIN", "LIDFA", "GARFA", "ULUFA", "CRDFA", "SEKFK",
    # Brokerage / financial holding
    "ISMEN", "GEDIK", "OYAYO",
)

BIST_INDUSTRIALS_TICKERS: tuple[str, ...] = (
    # Steel / metal / mining-adjacent manufacturing
    "EREGL", "KRDMD",
    # Automotive
    "TOASO", "FROTO", "TTRAK", "OTKAR",
    # Defense / heavy industry
    "ASELS", "BRSAN", "EGEEN",
    # White goods / electronics manufacturing
    "ARCLK", "VESTL",
    # Chemicals / petrochemicals / refining
    "TUPRS", "PETKM", "SASA", "GUBRF", "KORDS",
    # Glass
    "SISE",
)

BIST_TECHNOLOGY_TICKERS: tuple[str, ...] = (
    "LOGO", "KAREL", "NETAS", "ARENA", "INDES", "ALCTL", "LINK", "DESPC",
)

BIST_HOLDING_INVESTMENT_TICKERS: tuple[str, ...] = (
    "KCHOL", "SAHOL", "DOHOL", "TKFEN", "ALARK", "ENKAI", "AGHOL", "YAZIC", "GSDHO", "GLYHO",
)

BIST_RETAIL_TRADE_TICKERS: tuple[str, ...] = (
    "BIMAS", "MGROS", "SOKM", "MAVI", "BIZIM", "TKNSA",
)

BIST_FOOD_BEVERAGE_TICKERS: tuple[str, ...] = (
    "ULKER", "CCOLA", "AEFES", "TATGD", "PINSU", "PNSUT", "BANVT",
)

BIST_TELECOMMUNICATIONS_TICKERS: tuple[str, ...] = (
    "TCELL", "TTKOM",
)

BIST_TRANSPORTATION_TICKERS: tuple[str, ...] = (
    "THYAO", "PGSUS", "CLEBI", "TAVHL", "RYSAS",
)

BIST_ENERGY_UTILITIES_TICKERS: tuple[str, ...] = (
    "AKSEN", "ENJSA", "ZOREN", "ODAS", "AYEN",
)

BIST_CONSTRUCTION_MATERIALS_TICKERS: tuple[str, ...] = (
    "CIMSA", "AKCNS", "NUHCM",
)

BIST_REAL_ESTATE_TICKERS: tuple[str, ...] = (
    "EKGYO", "ISGYO", "TRGYO", "HLGYO",
)

BIST_HEALTH_PHARMA_TICKERS: tuple[str, ...] = (
    "DEVA", "SELEC", "ECZYT",
)

BIST_SECTOR_TICKERS: dict[str, tuple[str, ...]] = {
    "financials": BIST_FINANCIALS_TICKERS,
    "industrials": BIST_INDUSTRIALS_TICKERS,
    "technology": BIST_TECHNOLOGY_TICKERS,
    "holding_investment": BIST_HOLDING_INVESTMENT_TICKERS,
    "retail_trade": BIST_RETAIL_TRADE_TICKERS,
    "food_beverage": BIST_FOOD_BEVERAGE_TICKERS,
    "telecommunications": BIST_TELECOMMUNICATIONS_TICKERS,
    "transportation": BIST_TRANSPORTATION_TICKERS,
    "energy_utilities": BIST_ENERGY_UTILITIES_TICKERS,
    "construction_materials": BIST_CONSTRUCTION_MATERIALS_TICKERS,
    "real_estate": BIST_REAL_ESTATE_TICKERS,
    "health_pharma": BIST_HEALTH_PHARMA_TICKERS,
}


def resolve_sector_tickers(sector: str) -> tuple[str, ...]:
    """Return the curated ticker tuple for a supported sector preset name."""
    if not isinstance(sector, str):
        raise InputError("sector must be a string")

    normalized = sector.strip().lower()
    tickers = BIST_SECTOR_TICKERS.get(normalized)
    if tickers is None:
        allowed = ", ".join(sorted(BIST_SECTOR_TICKERS))
        raise InputError(f"Unsupported sector '{sector}'. Valid sectors: {allowed}")
    return tickers
