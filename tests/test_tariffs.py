"""Tests for supplier profiles and hourly averaging."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.greek_energy_prices.entsoe import PricePoint
from custom_components.greek_energy_prices.pricing import (
    TariffSettings,
    average_hourly,
)
from custom_components.greek_energy_prices.tariffs import (
    CUSTOM,
    PROFILES,
    get_profile,
)

START = datetime(2026, 10, 31, 22, 0, tzinfo=UTC)


def test_profiles_are_sane() -> None:
    assert PROFILES
    for key, profile in PROFILES.items():
        assert profile.key == key
        assert 1.0 <= profile.multiplier <= 1.5
        assert 0 <= profile.base_price < 0.5
        assert profile.source.startswith("https://")
        datetime.fromisoformat(profile.as_of)


def test_get_profile() -> None:
    assert get_profile(CUSTOM) is None
    assert get_profile(None) is None
    assert get_profile("nope") is None
    assert get_profile("dei_myhome_dynamic").supplier == "ΔΕΗ"


def test_dei_formula() -> None:
    profile = PROFILES["dei_myhome_dynamic"]
    settings = TariffSettings(
        wholesale_multiplier=profile.multiplier,
        supplier_margin=profile.base_price,
        other_charges=0.05,
        vat_percent=6,
    )
    # ΤΕΑ 100 €/MWh = 0.1 €/kWh
    assert settings.supply(0.1) == pytest.approx(1.19 * 0.1 + 0.044)
    assert settings.retail(0.1) == pytest.approx((0.119 + 0.044 + 0.05) * 1.06)


def test_average_hourly() -> None:
    quarter = timedelta(minutes=15)
    points = [
        PricePoint(START + quarter * i, START + quarter * (i + 1), price)
        for i, price in enumerate([10, 20, 30, 40, 100, 100, 100, 100])
    ]
    hourly = average_hourly(points)
    assert [(p.start, p.price_eur_mwh) for p in hourly] == [
        (START, 25.0),
        (START + timedelta(hours=1), 100.0),
    ]
    assert hourly[0].end == START + timedelta(hours=1)


def test_average_hourly_keeps_hourly_points() -> None:
    points = [PricePoint(START, START + timedelta(hours=1), 42.0)]
    assert average_hourly(points) == points
