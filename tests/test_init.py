"""Integration tests: config flow and entities inside Home Assistant."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.greek_energy_prices.const import (
    CONF_API_KEY,
    CONF_CHEAP_HOURS,
    CONF_HOURLY_PRICES,
    CONF_OTHER_CHARGES,
    CONF_PROFILE,
    CONF_SUPPLIER_MARGIN,
    CONF_VAT,
    CONF_WHOLESALE_MULTIPLIER,
    DOMAIN,
)
from custom_components.greek_energy_prices.entsoe import (
    EntsoeAuthError,
    EntsoeError,
    PricePoint,
)

CLIENT = "custom_components.greek_energy_prices.entsoe.EntsoeClient.async_get_prices"
TODAY_START = datetime(2026, 10, 31, 22, 0, tzinfo=UTC)  # 2026-11-01 00:00 Athens

USER_INPUT = {
    CONF_API_KEY: "token",
    CONF_SUPPLIER_MARGIN: 0.01,
    CONF_OTHER_CHARGES: 0.04,
    CONF_VAT: 6.0,
    CONF_CHEAP_HOURS: 2.0,
}


def _points(days: int = 1) -> list[PricePoint]:
    """Hourly prices: hour h costs (100 + h) €/MWh, except 03:00–05:00 = 10."""
    points = []
    for h in range(24 * days):
        price = 10.0 if h % 24 in (3, 4) else 100.0 + h % 24
        start = TODAY_START + timedelta(hours=h)
        points.append(PricePoint(start, start + timedelta(hours=1), price))
    return points


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    step1 = {CONF_API_KEY: "token", CONF_PROFILE: "dei_myhome_dynamic"}

    with patch(CLIENT, side_effect=EntsoeAuthError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], step1
        )
    assert result["errors"] == {"base": "invalid_auth"}

    with patch(CLIENT, side_effect=EntsoeError):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], step1
        )
    assert result["errors"] == {"base": "cannot_connect"}

    with patch(CLIENT, return_value=[]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], step1
        )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "tariff"
    assert "ΔΕΗ" in result["description_placeholders"]["profile"]
    # The form is pre-filled with the profile's published values.
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults[CONF_WHOLESALE_MULTIPLIER] == 1.19
    assert defaults[CONF_SUPPLIER_MARGIN] == 0.044
    assert defaults[CONF_HOURLY_PRICES] is True

    with patch(
        "custom_components.greek_energy_prices.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**defaults, CONF_OTHER_CHARGES: 0.05}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {**step1, **defaults, CONF_OTHER_CHARGES: 0.05}


@pytest.fixture
async def setup_entry(hass: HomeAssistant, freezer: FrozenDateTimeFactory):
    freezer.move_to(TODAY_START + timedelta(hours=3, minutes=20))  # 03:20 Athens
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    mock = AsyncMock(return_value=_points(2))
    with patch(CLIENT, mock):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, mock


async def test_entities(hass: HomeAssistant, setup_entry, freezer) -> None:
    entry, _ = setup_entry
    assert entry.state is ConfigEntryState.LOADED

    expected = (0.010 + 0.01 + 0.04) * 1.06
    state = hass.states.get("sensor.greek_electricity_prices_current_price")
    assert float(state.state) == pytest.approx(expected)
    assert state.attributes["unit_of_measurement"] == "EUR/kWh"
    assert len(state.attributes["today"]) == 24
    assert state.attributes["tomorrow_valid"] is True

    cheap = hass.states.get("binary_sensor.greek_electricity_prices_cheap_hour_now")
    assert cheap.state == "on"
    assert len(cheap.attributes["intervals"]) == 2

    window = hass.states.get("sensor.greek_electricity_prices_cheapest_window_start")
    assert window.state == (TODAY_START + timedelta(hours=3)).isoformat()

    # Move to 06:00 Athens: quarter-hour tick updates without API call.
    freezer.move_to(TODAY_START + timedelta(hours=6, seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert (
        hass.states.get("binary_sensor.greek_electricity_prices_cheap_hour_now").state
        == "off"
    )
    state = hass.states.get("sensor.greek_electricity_prices_current_price")
    assert float(state.state) == pytest.approx((0.106 + 0.05) * 1.06)


async def test_partial_tomorrow_ignored_and_refetched(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    current = "sensor.greek_electricity_prices_current_price"
    average = "sensor.greek_electricity_prices_tomorrow_average_price"
    freezer.move_to(TODAY_START + timedelta(hours=10))  # 10:00 Athens
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    # Today plus the one hour of tomorrow that the market day spills into.
    mock = AsyncMock(return_value=_points(2)[:25])
    with patch(CLIENT, mock):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        state = hass.states.get(current)
        assert state.attributes["tomorrow"] == []
        assert state.attributes["tomorrow_valid"] is False
        assert hass.states.get(average).state == "unknown"
        assert mock.await_count == 1

        # At 13:05 Athens tomorrow is fetched, well before the data gets stale.
        mock.return_value = _points(2)
        freezer.move_to(TODAY_START + timedelta(hours=13, minutes=5))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert mock.await_count == 2
        state = hass.states.get(current)
        assert len(state.attributes["tomorrow"]) == 24
        assert state.attributes["tomorrow_valid"] is True
        assert hass.states.get(average).state != "unknown"


async def test_options_switch_profile(hass: HomeAssistant, setup_entry) -> None:
    entry, _ = setup_entry
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROFILE: "zenith_power_home_flow"}
    )
    assert result["step_id"] == "tariff"
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults[CONF_SUPPLIER_MARGIN] == 0.100
    assert defaults[CONF_WHOLESALE_MULTIPLIER] == 1.2
    # Non-supplier values are kept from the existing entry.
    assert defaults[CONF_OTHER_CHARGES] == 0.04

    with patch(CLIENT, AsyncMock(return_value=_points(2))):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**defaults, CONF_OTHER_CHARGES: 0.0, CONF_VAT: 0.0}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    state = hass.states.get("sensor.greek_electricity_prices_current_price")
    # 03:20 → wholesale 10 €/MWh: 1.2 × 0.010 + 0.100
    assert float(state.state) == pytest.approx(0.112)
    assert state.attributes["supplier"] == "ZeniΘ"
    supply = hass.states.get("sensor.greek_electricity_prices_current_supply_price")
    assert float(supply.state) == pytest.approx(0.112)
    assert state.attributes["today"][3]["supply"] == pytest.approx(0.112)
    assert state.attributes["monthly_fee"] == 15.0


async def test_options_keep_custom_values(hass: HomeAssistant, setup_entry) -> None:
    entry, _ = setup_entry
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_PROFILE: "dei_myhome_dynamic",
            CONF_WHOLESALE_MULTIPLIER: 1.5,
            CONF_SUPPLIER_MARGIN: 0.05,
        },
    )
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PROFILE: "dei_myhome_dynamic"}
    )
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults[CONF_WHOLESALE_MULTIPLIER] == 1.5
    assert defaults[CONF_SUPPLIER_MARGIN] == 0.05


async def test_auth_failure_starts_reauth(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    with patch(CLIENT, side_effect=EntsoeAuthError):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert flows and flows[0]["context"]["source"] == "reauth"
