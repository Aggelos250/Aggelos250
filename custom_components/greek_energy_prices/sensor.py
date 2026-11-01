"""Sensors for Greek Energy Prices."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import GREECE_TZ, UNIT_EUR_PER_KWH
from .coordinator import GreekEnergyConfigEntry, PriceData
from .entity import GreekEnergyEntity
from .pricing import cheapest_window, day_stats, interval_at, next_interval

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class GreekEnergySensorDescription(SensorEntityDescription):
    """Describes a price sensor."""

    value_fn: Callable[[PriceData, datetime], float | datetime | None]
    attrs_fn: Callable[[PriceData, datetime], dict[str, Any]] | None = None


def _current(data: PriceData, now: datetime) -> float | None:
    interval = interval_at(data.intervals, now)
    return interval.retail if interval else None


def _current_wholesale(data: PriceData, now: datetime) -> float | None:
    interval = interval_at(data.intervals, now)
    return interval.wholesale if interval else None


def _next(data: PriceData, now: datetime) -> float | None:
    interval = next_interval(data.intervals, now)
    return interval.retail if interval else None


def _current_attrs(data: PriceData, now: datetime) -> dict[str, Any]:
    stats = day_stats(data.today)
    return {
        "today": [i.as_dict(GREECE_TZ) for i in data.today],
        "tomorrow": [i.as_dict(GREECE_TZ) for i in data.tomorrow],
        "tomorrow_valid": bool(data.tomorrow),
        "today_average": round(stats.average, 5) if stats else None,
        "wholesale_multiplier": data.settings.wholesale_multiplier,
        "supplier_margin": data.settings.supplier_margin,
        "other_charges": data.settings.other_charges,
        "vat_percent": data.settings.vat_percent,
        "hourly_prices": data.hourly,
        "last_fetch": data.fetched_at.isoformat(),
        **_profile_attrs(data),
    }


def _profile_attrs(data: PriceData) -> dict[str, Any]:
    profile = data.profile
    if profile is None:
        return {"supplier_profile": "custom"}
    return {
        "supplier_profile": profile.key,
        "supplier": profile.supplier,
        "product": profile.product,
        "monthly_fee": profile.monthly_fee,
        "profile_source": profile.source,
        "profile_checked": profile.as_of,
    }


def _stat(day: str, field: str) -> Callable[[PriceData, datetime], Any]:
    def _value(data: PriceData, _now: datetime) -> Any:
        stats = day_stats(data.today if day == "today" else data.tomorrow)
        return getattr(stats, field) if stats else None

    return _value


def _cheapest_window_start(data: PriceData, now: datetime) -> datetime | None:
    current = interval_at(data.intervals, now)
    window = cheapest_window(
        data.intervals,
        timedelta(hours=data.cheap_hours),
        not_before=current.start if current else now,
    )
    return window.start if window else None


def _cheapest_window_attrs(data: PriceData, now: datetime) -> dict[str, Any]:
    current = interval_at(data.intervals, now)
    window = cheapest_window(
        data.intervals,
        timedelta(hours=data.cheap_hours),
        not_before=current.start if current else now,
    )
    if window is None:
        return {"duration_hours": data.cheap_hours}
    return {
        "duration_hours": data.cheap_hours,
        "end": window.end.astimezone(GREECE_TZ).isoformat(),
        "average_price": round(window.average, 5),
    }


_PRICE = {
    "native_unit_of_measurement": UNIT_EUR_PER_KWH,
    "suggested_display_precision": 4,
}

SENSORS: tuple[GreekEnergySensorDescription, ...] = (
    GreekEnergySensorDescription(
        key="current_price",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_current,
        attrs_fn=_current_attrs,
        **_PRICE,
    ),
    GreekEnergySensorDescription(
        key="current_wholesale_price",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_current_wholesale,
        entity_registry_enabled_default=False,
        **_PRICE,
    ),
    GreekEnergySensorDescription(
        key="next_price",
        value_fn=_next,
        **_PRICE,
    ),
    GreekEnergySensorDescription(
        key="today_average",
        value_fn=_stat("today", "average"),
        **_PRICE,
    ),
    GreekEnergySensorDescription(
        key="today_min",
        value_fn=_stat("today", "minimum"),
        **_PRICE,
    ),
    GreekEnergySensorDescription(
        key="today_max",
        value_fn=_stat("today", "maximum"),
        **_PRICE,
    ),
    GreekEnergySensorDescription(
        key="tomorrow_average",
        value_fn=_stat("tomorrow", "average"),
        **_PRICE,
    ),
    GreekEnergySensorDescription(
        key="today_cheapest_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_stat("today", "cheapest_start"),
    ),
    GreekEnergySensorDescription(
        key="today_most_expensive_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_stat("today", "most_expensive_start"),
    ),
    GreekEnergySensorDescription(
        key="cheapest_window_start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_cheapest_window_start,
        attrs_fn=_cheapest_window_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GreekEnergyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        GreekEnergySensor(coordinator, description) for description in SENSORS
    )


class GreekEnergySensor(GreekEnergyEntity, SensorEntity):
    """A price sensor."""

    entity_description: GreekEnergySensorDescription

    def __init__(self, coordinator, description: GreekEnergySensorDescription) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | datetime | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data, dt_util.utcnow())
