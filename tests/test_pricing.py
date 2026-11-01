"""Tests for price calculations."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from custom_components.greek_energy_prices.const import GREECE_TZ
from custom_components.greek_energy_prices.entsoe import PricePoint
from custom_components.greek_energy_prices.pricing import (
    TariffSettings,
    build_intervals,
    cheapest_intervals,
    cheapest_window,
    day_stats,
    interval_at,
    intervals_for_day,
    next_interval,
)

START = datetime(2026, 10, 31, 22, 0, tzinfo=UTC)  # 2026-11-01 00:00 Athens


def _hourly(prices_mwh: list[float], start: datetime = START):
    points = [
        PricePoint(start + timedelta(hours=i), start + timedelta(hours=i + 1), p)
        for i, p in enumerate(prices_mwh)
    ]
    return build_intervals(points, TariffSettings(vat_percent=0))


def test_retail_formula() -> None:
    settings = TariffSettings(supplier_margin=0.02, other_charges=0.05, vat_percent=6)
    assert settings.retail(0.10) == pytest.approx((0.10 + 0.02 + 0.05) * 1.06)


def test_lookup_and_stats() -> None:
    intervals = _hourly([100, 50, 200, 80])
    now = START + timedelta(minutes=90)
    assert interval_at(intervals, now).wholesale == pytest.approx(0.05)
    assert next_interval(intervals, now).wholesale == pytest.approx(0.2)
    stats = day_stats(intervals)
    assert stats.average == pytest.approx(0.1075)
    assert stats.minimum == pytest.approx(0.05)
    assert stats.maximum == pytest.approx(0.2)
    assert stats.cheapest_start == START + timedelta(hours=1)
    assert stats.most_expensive_start == START + timedelta(hours=2)
    assert day_stats([]) is None


def test_cheapest_intervals_chronological() -> None:
    intervals = _hourly([100, 50, 200, 40, 300])
    chosen = cheapest_intervals(intervals, 2)
    assert [i.start for i in chosen] == [
        START + timedelta(hours=1),
        START + timedelta(hours=3),
    ]
    assert cheapest_intervals(intervals, 0) == []


def test_cheapest_window_contiguous() -> None:
    intervals = _hourly([10, 300, 20, 30, 300, 5])
    window = cheapest_window(intervals, timedelta(hours=2))
    assert window.start == START + timedelta(hours=2)
    assert window.end == START + timedelta(hours=4)
    assert window.average == pytest.approx(0.025)
    # Respect not_before
    later = cheapest_window(
        intervals, timedelta(hours=2), not_before=START + timedelta(hours=3)
    )
    assert later.start == START + timedelta(hours=4)
    # Too long for remaining data
    assert cheapest_window(intervals, timedelta(hours=7)) is None


def test_cheapest_window_breaks_on_gap() -> None:
    a = _hourly([10])
    b = _hourly([10], start=START + timedelta(hours=2))
    assert cheapest_window(a + b, timedelta(hours=2)) is None


def test_intervals_for_day_uses_athens_time() -> None:
    intervals = _hourly([1.0] * 26, start=START - timedelta(hours=1))
    nov1 = intervals_for_day(intervals, date(2026, 11, 1), GREECE_TZ)
    assert len(nov1) == 24
    assert nov1[0].start == START


def test_dst_day_has_25_hours() -> None:
    # 2026-10-25: clocks go back in Athens, day spans 25 hours.
    start = datetime(2026, 10, 24, 21, 0, tzinfo=UTC)
    intervals = _hourly([1.0] * 25, start=start)
    assert len(intervals_for_day(intervals, date(2026, 10, 25), GREECE_TZ)) == 25
