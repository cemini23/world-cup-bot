"""Kalshi read-only REST helpers for Module 6 cross-venue scanner."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
from dataclasses import dataclass
from typing import Any

from world_cup_bot.http_client import urlopen_get

DEFAULT_KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"

WC_GROUPS = tuple("ABCDEFGHIJKL")

# Event stems — append group letter (A–L) or fixed suffix (RO16)
_KALSHI_WC_EVENT_STEMS = (
    "KXWCGROUPWIN-26",
    "KXWCGROUPQUAL-26",
)
_KALSHI_WC_FIXED_EVENTS = ("KXWCROUND-26RO16",)

# Suffix on market tickers, e.g. KXWCGROUPWIN-26D-USA
_KALSHI_TEAM_SUFFIX = re.compile(r"-([A-Z]{2,4})$")

# Kalshi abbreviations → canonical team names (extend as new markets appear)
KALSHI_TEAM_CODES: dict[str, str] = {
    "USA": "USA",
    "SUI": "Switzerland",
    "ENG": "England",
    "CRO": "Croatia",
    "MEX": "Mexico",
    "CAN": "Canada",
    "QAT": "Qatar",
    "BIH": "Bosnia & Herzegovina",
    "BRA": "Brazil",
    "ARG": "Argentina",
    "FRA": "France",
    "GER": "Germany",
    "ESP": "Spain",
    "POR": "Portugal",
    "NED": "Netherlands",
    "BEL": "Belgium",
    "URU": "Uruguay",
    "JPN": "Japan",
    "KOR": "South Korea",
    "MAR": "Morocco",
    "SEN": "Senegal",
    "CIV": "Ivory Coast",
    "TUR": "Turkey",
    "AUS": "Australia",
    "COL": "Colombia",
    "ECU": "Ecuador",
    "PAR": "Paraguay",
    "CRC": "Costa Rica",
    "PAN": "Panama",
    "IRN": "Iran",
    "SAU": "Saudi Arabia",
    "ALG": "Algeria",
    "AUT": "Austria",
    "NOR": "Norway",
    "SCO": "Scotland",
    "WAL": "Wales",
    "UKR": "Ukraine",
    "POL": "Poland",
    "CZE": "Czech Republic",
    "DEN": "Denmark",
    "SWE": "Sweden",
    "FIN": "Finland",
    "HUN": "Hungary",
    "SRB": "Serbia",
    "UZB": "Uzbekistan",
    "CUW": "Curaçao",
    "DZA": "Algeria",
    "HTI": "Haiti",
    "JOR": "Jordan",
    "IRI": "Iran",
    "IRQ": "Iraq",
    "KSA": "Saudi Arabia",
    "NZL": "New Zealand",
    "EGY": "Egypt",
    "TUN": "Tunisia",
    "GHA": "Ghana",
    "CMR": "Cameroon",
    "NGA": "Nigeria",
    "RSA": "South Africa",
    "CPV": "Cape Verde",
    "COD": "DR Congo",
}


@dataclass(frozen=True)
class KalshiMarketSnapshot:
    ticker: str
    event_ticker: str
    title: str
    team: str | None
    market_type: str
    mid: float | None
    yes_bid: float | None
    yes_ask: float | None
    volume: float | None
    volume_24h: float | None
    open_interest: float | None
    status: str


def _optional_dollar(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _cents_to_prob(value: Any) -> float | None:
    if value is None or value == "":
        return None
    cents = float(value)
    if cents > 1.0:
        return cents / 100.0
    return cents


def implied_mid(market: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    """Return (mid, yes_bid, yes_ask) as 0–1 probabilities."""
    bid = _optional_dollar(market.get("yes_bid_dollars"))
    ask = _optional_dollar(market.get("yes_ask_dollars"))
    if bid is None:
        bid = _cents_to_prob(market.get("yes_bid"))
    if ask is None:
        ask = _cents_to_prob(market.get("yes_ask"))

    mid = None
    if bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
    else:
        last = _optional_dollar(market.get("last_price_dollars"))
        if last is None:
            last = _cents_to_prob(market.get("last_price"))
        mid = last
    return mid, bid, ask


def infer_market_type(ticker: str, title: str = "") -> str:
    upper = ticker.upper()
    text = f"{ticker} {title}".upper()
    if "GROUPWIN" in upper or "GROUP WIN" in text:
        return "group_winner"
    if "GROUPQUAL" in upper or "GROUP QUAL" in text:
        return "group_qualify"
    if "ROUND" in upper and "RO16" in upper:
        return "round_of_16_qualify"
    if "KXWCGAME" in upper or "MATCH" in text:
        return "match_winner"
    if "ADVANCE" in text or "KNOCKOUT" in text:
        return "advance_to_knockout"
    return "unknown"


def team_from_kalshi_ticker(ticker: str, title: str = "") -> str | None:
    m = _KALSHI_TEAM_SUFFIX.search(ticker.upper())
    if m:
        code = m.group(1)
        if code in KALSHI_TEAM_CODES:
            return KALSHI_TEAM_CODES[code]
        return code
    # Fallback: title like "USA to win Group D"
    for code, team in KALSHI_TEAM_CODES.items():
        if f" {code} " in f" {title.upper()} " or title.upper().startswith(f"{code} "):
            return team
    return None


def parse_kalshi_market(raw: dict[str, Any]) -> KalshiMarketSnapshot:
    ticker = str(raw.get("ticker") or "")
    title = str(raw.get("title") or raw.get("subtitle") or ticker)
    mid, bid, ask = implied_mid(raw)
    event = str(raw.get("event_ticker") or "")
    if not event and "-" in ticker:
        # KXWCGROUPWIN-26D-USA → event KXWCGROUPWIN-26D
        parts = ticker.rsplit("-", 1)
        if len(parts) == 2:
            event = parts[0]

    vol = _optional_dollar(raw.get("volume_fp")) or _optional_dollar(raw.get("volume"))
    vol24 = _optional_dollar(raw.get("volume_24h_fp")) or _optional_dollar(raw.get("volume_24h"))
    oi = _optional_dollar(raw.get("open_interest_fp")) or _optional_dollar(raw.get("open_interest"))

    return KalshiMarketSnapshot(
        ticker=ticker,
        event_ticker=event,
        title=title,
        team=team_from_kalshi_ticker(ticker, title),
        market_type=infer_market_type(ticker, title),
        mid=mid,
        yes_bid=bid,
        yes_ask=ask,
        volume=vol,
        volume_24h=vol24,
        open_interest=oi,
        status=str(raw.get("status") or "unknown"),
    )


def _get_json(url: str, *, opener: Any | None = None, timeout: float = 30) -> dict[str, Any]:
    if opener is not None:
        with opener(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    with urlopen_get(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_market(
    ticker: str,
    *,
    base_url: str = DEFAULT_KALSHI_BASE,
    opener: Any | None = None,
) -> KalshiMarketSnapshot:
    url = f"{base_url.rstrip('/')}/markets/{urllib.parse.quote(ticker, safe='')}"
    try:
        payload = _get_json(url, opener=opener)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Kalshi GET /markets/{ticker} failed: {exc}") from exc
    market = payload.get("market") or payload
    return parse_kalshi_market(market)


def list_markets(
    *,
    base_url: str = DEFAULT_KALSHI_BASE,
    status: str = "open",
    series_ticker: str | None = None,
    event_ticker: str | None = None,
    limit: int = 200,
    max_pages: int = 10,
    opener: Any | None = None,
) -> list[KalshiMarketSnapshot]:
    """Paginate Kalshi /markets; optional series/event filter."""
    out: list[KalshiMarketSnapshot] = []
    cursor: str | None = None
    base = base_url.rstrip("/")

    for _ in range(max_pages):
        params: dict[str, str] = {"status": status, "limit": str(limit)}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if event_ticker:
            params["event_ticker"] = event_ticker
        if cursor:
            params["cursor"] = cursor

        url = f"{base}/markets?{urllib.parse.urlencode(params)}"
        try:
            payload = _get_json(url, opener=opener)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Kalshi list markets failed: {exc}") from exc

        for raw in payload.get("markets") or []:
            out.append(parse_kalshi_market(raw))

        cursor = payload.get("cursor")
        if not cursor:
            break
        time.sleep(0.1)

    return out


def discover_wc_markets(
    *,
    ticker_prefixes: tuple[str, ...] = ("KXWCGROUPWIN", "KXWCGROUPQUAL", "KXWCROUND", "KXWCGAME"),
    base_url: str = DEFAULT_KALSHI_BASE,
    extra_event_tickers: tuple[str, ...] = (),
    opener: Any | None = None,
) -> list[KalshiMarketSnapshot]:
    """Fetch open Kalshi WC 2026 markets by event ticker (not global pagination)."""
    by_ticker: dict[str, KalshiMarketSnapshot] = {}
    prefixes = tuple(p.upper() for p in ticker_prefixes)

    event_tickers: list[str] = list(extra_event_tickers)
    for stem in _KALSHI_WC_EVENT_STEMS:
        for group in WC_GROUPS:
            event_tickers.append(f"{stem}{group}")
    event_tickers.extend(_KALSHI_WC_FIXED_EVENTS)

    for event in event_tickers:
        if not any(event.upper().startswith(p) for p in prefixes):
            continue
        try:
            snaps = list_markets(
                base_url=base_url,
                event_ticker=event,
                limit=50,
                max_pages=2,
                opener=opener,
            )
        except RuntimeError:
            continue
        for snap in snaps:
            by_ticker[snap.ticker] = snap
        if snaps:
            time.sleep(0.05)

    # Fallback: paginate open markets and filter (catches KXWCGAME match tickers)
    if not by_ticker:
        for snap in list_markets(base_url=base_url, opener=opener, max_pages=20):
            ticker = snap.ticker.upper()
            if not any(ticker.startswith(p) for p in prefixes):
                continue
            if "26" not in ticker:
                continue
            by_ticker[snap.ticker] = snap

    out = sorted(by_ticker.values(), key=lambda m: (m.market_type, m.team or "", m.ticker))
    return out
