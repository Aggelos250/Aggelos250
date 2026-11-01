"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components in every test."""
    return


def make_document(
    series: Iterable[tuple[datetime, datetime, str, dict[int, float], str]],
) -> str:
    """Build a minimal A44 Publication_MarketDocument.

    Each series is (start, end, resolution, {position: price}, curve_type).
    """
    fmt = "%Y-%m-%dT%H:%MZ"
    parts = []
    for start, end, resolution, prices, curve in series:
        points = "".join(
            f"<Point><position>{pos}</position><price.amount>{price}</price.amount></Point>"
            for pos, price in sorted(prices.items())
        )
        parts.append(
            "<TimeSeries><mRID>1</mRID><curveType>"
            f"{curve}</curveType><Period><timeInterval><start>{start.strftime(fmt)}"
            f"</start><end>{end.strftime(fmt)}</end></timeInterval><resolution>"
            f"{resolution}</resolution>{points}</Period></TimeSeries>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">'
        + "".join(parts)
        + "</Publication_MarketDocument>"
    )


def hourly_day(local_midnight_utc: datetime, prices: list[float]) -> str:
    """One PT60M A01 series starting at the given UTC instant."""
    return make_document(
        [
            (
                local_midnight_utc,
                local_midnight_utc + timedelta(hours=len(prices)),
                "PT60M",
                {i + 1: p for i, p in enumerate(prices)},
                "A01",
            )
        ]
    )
