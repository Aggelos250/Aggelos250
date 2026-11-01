"""ENTSO-E Transparency Platform client for Greek day-ahead prices.

The parsing functions in this module are pure (no Home Assistant imports) so
they can be unit tested in isolation.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiohttp

from .const import ENTSOE_API_URL, GREECE_BIDDING_ZONE

_RESOLUTION_RE = re.compile(r"^PT(\d+)M$")
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class EntsoeError(Exception):
    """Generic error talking to ENTSO-E."""


class EntsoeAuthError(EntsoeError):
    """The security token was rejected."""


@dataclass(frozen=True, slots=True)
class PricePoint:
    """Wholesale price for one market time unit."""

    start: datetime  # timezone-aware, UTC
    end: datetime  # timezone-aware, UTC
    price_eur_mwh: float

    @property
    def price_eur_kwh(self) -> float:
        """Price converted to €/kWh."""
        return self.price_eur_mwh / 1000.0


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(elem: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in elem if _strip_ns(child.tag) == name]


def _child(elem: ET.Element, name: str) -> ET.Element | None:
    found = _children(elem, name)
    return found[0] if found else None


def _child_text(elem: ET.Element, name: str) -> str | None:
    child = _child(elem, name)
    return child.text.strip() if child is not None and child.text else None


def _parse_time(value: str) -> datetime:
    # ENTSO-E uses e.g. 2026-11-01T23:00Z
    return datetime.strptime(value, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


def _parse_resolution(value: str) -> timedelta:
    match = _RESOLUTION_RE.match(value)
    if not match:
        raise EntsoeError(f"Unsupported resolution {value!r}")
    return timedelta(minutes=int(match.group(1)))


def format_period(moment: datetime) -> str:
    """Format a datetime as an ENTSO-E periodStart/periodEnd value (UTC)."""
    return moment.astimezone(UTC).strftime("%Y%m%d%H%M")


def parse_day_ahead_prices(xml_text: str) -> list[PricePoint]:
    """Parse an A44 (price document) response into sorted price points.

    * An ``Acknowledgement_MarketDocument`` with "no matching data" yields an
      empty list (prices not yet published).
    * Curve type A03 omits points whose price equals the previous one; those
      gaps are filled forward.
    * When the same interval is covered by several series (e.g. PT15M and
      PT60M), the finest resolution wins.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as err:
        raise EntsoeError(f"Invalid XML from ENTSO-E: {err}") from err

    root_name = _strip_ns(root.tag)
    if root_name == "Acknowledgement_MarketDocument":
        reason = _child(root, "Reason")
        code = _child_text(reason, "code") if reason is not None else None
        text = _child_text(reason, "text") if reason is not None else None
        if code == "999":
            return []
        raise EntsoeError(f"ENTSO-E error {code}: {text}")
    if root_name != "Publication_MarketDocument":
        raise EntsoeError(f"Unexpected document type {root_name}")

    # key: start time -> (resolution, PricePoint)
    best: dict[datetime, tuple[timedelta, PricePoint]] = {}

    for series in _children(root, "TimeSeries"):
        curve_type = _child_text(series, "curveType") or "A01"
        for period in _children(series, "Period"):
            interval = _child(period, "timeInterval")
            resolution_text = _child_text(period, "resolution")
            if interval is None or resolution_text is None:
                continue
            start_text = _child_text(interval, "start")
            end_text = _child_text(interval, "end")
            if start_text is None or end_text is None:
                continue
            period_start = _parse_time(start_text)
            period_end = _parse_time(end_text)
            resolution = _parse_resolution(resolution_text)
            slots = int((period_end - period_start) / resolution)

            prices: dict[int, float] = {}
            for point in _children(period, "Point"):
                position = _child_text(point, "position")
                amount = _child_text(point, "price.amount")
                if position is None or amount is None:
                    continue
                prices[int(position)] = float(amount)
            if not prices:
                continue

            last: float | None = None
            for position in range(1, slots + 1):
                if position in prices:
                    last = prices[position]
                elif curve_type != "A03" or last is None:
                    # A01 curves must be complete; skip unknown slots.
                    continue
                start = period_start + resolution * (position - 1)
                current = best.get(start)
                if current is not None and current[0] <= resolution:
                    continue
                best[start] = (
                    resolution,
                    PricePoint(start, start + resolution, last),
                )

    points = sorted((p for _, p in best.values()), key=lambda p: p.start)
    # A coarse slot may overlap finer ones already chosen; drop overlaps.
    result: list[PricePoint] = []
    for point in points:
        if result and point.start < result[-1].end:
            continue
        result.append(point)
    return result


class EntsoeClient:
    """Minimal async client for day-ahead prices."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        bidding_zone: str = GREECE_BIDDING_ZONE,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._zone = bidding_zone

    async def async_get_prices(
        self, start: datetime, end: datetime
    ) -> list[PricePoint]:
        """Fetch day-ahead prices for [start, end)."""
        params = {
            "securityToken": self._api_key,
            "documentType": "A44",
            "in_Domain": self._zone,
            "out_Domain": self._zone,
            "periodStart": format_period(start),
            "periodEnd": format_period(end),
        }
        try:
            async with self._session.get(
                ENTSOE_API_URL, params=params, timeout=_REQUEST_TIMEOUT
            ) as resp:
                text = await resp.text()
                if resp.status == 401:
                    raise EntsoeAuthError("Invalid ENTSO-E security token")
                # "No data" is returned as an acknowledgement document,
                # sometimes with HTTP 200 and sometimes with 400.
                if resp.status not in (200, 400):
                    raise EntsoeError(f"HTTP {resp.status} from ENTSO-E")
        except aiohttp.ClientError as err:
            raise EntsoeError(f"Error connecting to ENTSO-E: {err}") from err
        except TimeoutError as err:
            raise EntsoeError("Timeout connecting to ENTSO-E") from err

        points = parse_day_ahead_prices(text)
        return [p for p in points if start <= p.start < end]
