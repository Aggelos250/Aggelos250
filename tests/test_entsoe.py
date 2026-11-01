"""Tests for the ENTSO-E XML parser."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.greek_energy_prices.entsoe import (
    EntsoeError,
    format_period,
    parse_day_ahead_prices,
)

from .conftest import make_document

START = datetime(2026, 10, 31, 22, 0, tzinfo=UTC)  # 2026-11-01 00:00 Athens


def test_a03_curve_fills_gaps_forward() -> None:
    xml = make_document(
        [(START, START + timedelta(hours=1), "PT15M", {1: 100.0, 3: 50.0}, "A03")]
    )
    points = parse_day_ahead_prices(xml)
    assert [p.price_eur_mwh for p in points] == [100.0, 100.0, 50.0, 50.0]
    assert points[0].start == START
    assert points[-1].end == START + timedelta(hours=1)
    assert points[0].price_eur_kwh == pytest.approx(0.1)


def test_a01_curve_skips_missing_points() -> None:
    xml = make_document(
        [(START, START + timedelta(hours=1), "PT15M", {1: 10.0, 3: 30.0}, "A01")]
    )
    assert [p.price_eur_mwh for p in parse_day_ahead_prices(xml)] == [10.0, 30.0]


def test_finest_resolution_wins() -> None:
    end = START + timedelta(hours=1)
    xml = make_document(
        [
            (START, end, "PT60M", {1: 80.0}, "A01"),
            (START, end, "PT15M", {1: 1.0, 2: 2.0, 3: 3.0, 4: 4.0}, "A01"),
        ]
    )
    points = parse_day_ahead_prices(xml)
    assert [p.price_eur_mwh for p in points] == [1.0, 2.0, 3.0, 4.0]


def test_negative_prices_supported() -> None:
    xml = make_document(
        [(START, START + timedelta(hours=1), "PT60M", {1: -5.5}, "A01")]
    )
    assert parse_day_ahead_prices(xml)[0].price_eur_mwh == -5.5


def test_no_data_acknowledgement_returns_empty() -> None:
    xml = (
        '<Acknowledgement_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0">'
        "<Reason><code>999</code><text>No matching data found</text></Reason>"
        "</Acknowledgement_MarketDocument>"
    )
    assert parse_day_ahead_prices(xml) == []


def test_other_acknowledgement_raises() -> None:
    xml = (
        "<Acknowledgement_MarketDocument><Reason><code>500</code>"
        "<text>boom</text></Reason></Acknowledgement_MarketDocument>"
    )
    with pytest.raises(EntsoeError, match="500"):
        parse_day_ahead_prices(xml)


def test_invalid_xml_raises() -> None:
    with pytest.raises(EntsoeError):
        parse_day_ahead_prices("<html>Unauthorized")


def test_format_period_is_utc() -> None:
    from custom_components.greek_energy_prices.const import GREECE_TZ

    local = datetime(2026, 11, 1, 0, 0, tzinfo=GREECE_TZ)
    assert format_period(local) == "202610312200"
