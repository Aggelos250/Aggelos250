"""Data update coordinator for Greek Energy Prices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_KEY,
    CONF_CHEAP_HOURS,
    CONF_OTHER_CHARGES,
    CONF_SUPPLIER_MARGIN,
    CONF_VAT,
    DEFAULT_CHEAP_HOURS,
    DEFAULT_OTHER_CHARGES,
    DEFAULT_SUPPLIER_MARGIN,
    DEFAULT_VAT,
    DOMAIN,
    GREECE_TZ,
    MAX_DATA_AGE,
    RETRY_MISSING_TOMORROW,
    TOMORROW_AVAILABLE_HOUR,
    UPDATE_INTERVAL,
)
from .entsoe import EntsoeAuthError, EntsoeClient, EntsoeError, PricePoint
from .pricing import (
    PriceInterval,
    TariffSettings,
    build_intervals,
    intervals_for_day,
)

_LOGGER = logging.getLogger(__name__)

type GreekEnergyConfigEntry = ConfigEntry[GreekEnergyCoordinator]


@dataclass(slots=True)
class PriceData:
    """Everything the entities need."""

    intervals: list[PriceInterval]
    today: list[PriceInterval]
    tomorrow: list[PriceInterval]
    settings: TariffSettings
    cheap_hours: float
    fetched_at: datetime


def settings_from_entry(entry: ConfigEntry) -> tuple[TariffSettings, float]:
    """Read tariff settings (options override initial data)."""
    merged = {**entry.data, **entry.options}
    settings = TariffSettings(
        supplier_margin=float(
            merged.get(CONF_SUPPLIER_MARGIN, DEFAULT_SUPPLIER_MARGIN)
        ),
        other_charges=float(merged.get(CONF_OTHER_CHARGES, DEFAULT_OTHER_CHARGES)),
        vat_percent=float(merged.get(CONF_VAT, DEFAULT_VAT)),
    )
    cheap_hours = float(merged.get(CONF_CHEAP_HOURS, DEFAULT_CHEAP_HOURS))
    return settings, cheap_hours


class GreekEnergyCoordinator(DataUpdateCoordinator[PriceData]):
    """Fetches prices from ENTSO-E and caches them."""

    config_entry: GreekEnergyConfigEntry

    def __init__(self, hass: HomeAssistant, entry: GreekEnergyConfigEntry) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._client = EntsoeClient(
            async_get_clientsession(hass), entry.data[CONF_API_KEY]
        )
        self._points: list[PricePoint] = []
        self._fetched_at: datetime | None = None
        self._last_attempt: datetime | None = None
        self._unsub_tick: CALLBACK_TYPE | None = None

    @callback
    def async_start_ticks(self) -> None:
        """Refresh entity states at every quarter-hour boundary."""

        @callback
        def _tick(_now: datetime) -> None:
            if self.data is not None:
                self.async_set_updated_data(self._build(self._points))

        self._unsub_tick = async_track_utc_time_change(
            self.hass, _tick, minute=[0, 15, 30, 45], second=1
        )

    @callback
    def async_stop_ticks(self) -> None:
        """Stop the quarter-hour ticks."""
        if self._unsub_tick:
            self._unsub_tick()
            self._unsub_tick = None

    def _needs_fetch(self, now: datetime) -> bool:
        if not self._points or self._fetched_at is None:
            return True
        local_now = now.astimezone(GREECE_TZ)
        today = local_now.date()
        if not intervals_for_day(self._build_raw(), today, GREECE_TZ):
            return True
        if now - self._fetched_at > MAX_DATA_AGE:
            return True
        tomorrow = today + timedelta(days=1)
        has_tomorrow = bool(intervals_for_day(self._build_raw(), tomorrow, GREECE_TZ))
        if (
            not has_tomorrow
            and local_now.hour >= TOMORROW_AVAILABLE_HOUR
            and (
                self._last_attempt is None
                or now - self._last_attempt >= RETRY_MISSING_TOMORROW
            )
        ):
            return True
        return False

    def _build_raw(self) -> list[PriceInterval]:
        return build_intervals(self._points, TariffSettings())

    def _build(self, points: list[PricePoint]) -> PriceData:
        settings, cheap_hours = settings_from_entry(self.config_entry)
        intervals = build_intervals(points, settings)
        today = dt_util.utcnow().astimezone(GREECE_TZ).date()
        return PriceData(
            intervals=intervals,
            today=intervals_for_day(intervals, today, GREECE_TZ),
            tomorrow=intervals_for_day(intervals, today + timedelta(days=1), GREECE_TZ),
            settings=settings,
            cheap_hours=cheap_hours,
            fetched_at=self._fetched_at or dt_util.utcnow(),
        )

    async def _async_update_data(self) -> PriceData:
        now = dt_util.utcnow()
        if self._needs_fetch(now):
            self._last_attempt = now
            local_midnight = now.astimezone(GREECE_TZ).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            # Yesterday → day after tomorrow, so local days are always complete.
            # zoneinfo arithmetic is wall-clock based, so this is DST safe.
            start = local_midnight - timedelta(days=1)
            end = local_midnight + timedelta(days=2)
            try:
                points = await self._client.async_get_prices(start, end)
            except EntsoeAuthError as err:
                raise ConfigEntryAuthFailed(
                    translation_domain=DOMAIN, translation_key="invalid_auth"
                ) from err
            except EntsoeError as err:
                if not self._points:
                    raise UpdateFailed(
                        translation_domain=DOMAIN,
                        translation_key="update_failed",
                        translation_placeholders={"error": str(err)},
                    ) from err
                _LOGGER.warning("Keeping cached prices, update failed: %s", err)
            else:
                if points:
                    self._points = points
                    self._fetched_at = now
                elif not self._points:
                    raise UpdateFailed(
                        translation_domain=DOMAIN,
                        translation_key="no_data",
                    )
        # Drop data older than yesterday to keep memory bounded.
        cutoff = now - timedelta(days=2)
        self._points = [p for p in self._points if p.end > cutoff]
        return self._build(self._points)
