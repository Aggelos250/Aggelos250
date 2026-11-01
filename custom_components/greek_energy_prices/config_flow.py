"""Config flow for Greek Energy Prices."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_API_KEY,
    CONF_CHEAP_HOURS,
    CONF_HOURLY_PRICES,
    CONF_OTHER_CHARGES,
    CONF_PROFILE,
    CONF_SUPPLIER_MARGIN,
    CONF_VAT,
    CONF_WHOLESALE_MULTIPLIER,
    DEFAULT_CHEAP_HOURS,
    DEFAULT_HOURLY_PRICES,
    DEFAULT_OTHER_CHARGES,
    DEFAULT_SUPPLIER_MARGIN,
    DEFAULT_VAT,
    DEFAULT_WHOLESALE_MULTIPLIER,
    DOMAIN,
)
from .entsoe import EntsoeAuthError, EntsoeClient, EntsoeError
from .tariffs import CUSTOM, PROFILES, get_profile

_LOGGER = logging.getLogger(__name__)

_API_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


def _profile_schema(default: str) -> vol.Schema:
    options = [SelectOptionDict(value=p.key, label=p.label) for p in PROFILES.values()]
    options.append(SelectOptionDict(value=CUSTOM, label="Άλλο / Χειροκίνητα"))
    return vol.Schema(
        {
            vol.Required(CONF_PROFILE, default=default): SelectSelector(
                SelectSelectorConfig(
                    options=options,
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key=CONF_PROFILE,
                )
            )
        }
    )


def _number(
    minimum: float, maximum: float, step: float | str, unit: str | None
) -> NumberSelector:
    config = NumberSelectorConfig(
        min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX
    )
    if unit is not None:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def tariff_defaults(
    profile_key: str | None, current: Mapping[str, Any]
) -> dict[str, Any]:
    """Defaults for the tariff form.

    When a supplier profile is chosen, its published values replace the
    supplier-specific fields; everything else keeps the current values.
    """
    defaults = {
        CONF_WHOLESALE_MULTIPLIER: current.get(
            CONF_WHOLESALE_MULTIPLIER, DEFAULT_WHOLESALE_MULTIPLIER
        ),
        CONF_SUPPLIER_MARGIN: current.get(
            CONF_SUPPLIER_MARGIN, DEFAULT_SUPPLIER_MARGIN
        ),
        CONF_OTHER_CHARGES: current.get(CONF_OTHER_CHARGES, DEFAULT_OTHER_CHARGES),
        CONF_VAT: current.get(CONF_VAT, DEFAULT_VAT),
        CONF_CHEAP_HOURS: current.get(CONF_CHEAP_HOURS, DEFAULT_CHEAP_HOURS),
        CONF_HOURLY_PRICES: current.get(CONF_HOURLY_PRICES, DEFAULT_HOURLY_PRICES),
    }
    if (profile := get_profile(profile_key)) is not None:
        defaults[CONF_WHOLESALE_MULTIPLIER] = profile.multiplier
        defaults[CONF_SUPPLIER_MARGIN] = profile.base_price
        defaults[CONF_HOURLY_PRICES] = profile.hourly_tea
    return defaults


def _tariff_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_WHOLESALE_MULTIPLIER,
                default=defaults[CONF_WHOLESALE_MULTIPLIER],
            ): _number(0, 3, "any", None),
            vol.Required(
                CONF_SUPPLIER_MARGIN, default=defaults[CONF_SUPPLIER_MARGIN]
            ): _number(-1, 1, "any", "€/kWh"),
            vol.Required(
                CONF_OTHER_CHARGES, default=defaults[CONF_OTHER_CHARGES]
            ): _number(0, 1, "any", "€/kWh"),
            vol.Required(CONF_VAT, default=defaults[CONF_VAT]): _number(
                0, 30, 0.5, "%"
            ),
            vol.Required(CONF_CHEAP_HOURS, default=defaults[CONF_CHEAP_HOURS]): _number(
                0.25, 24, 0.25, "h"
            ),
            vol.Required(
                CONF_HOURLY_PRICES, default=defaults[CONF_HOURLY_PRICES]
            ): BooleanSelector(),
        }
    )


def _profile_placeholders(profile_key: str | None) -> dict[str, str]:
    profile = get_profile(profile_key)
    if profile is None:
        return {
            "profile": "Χειροκίνητα",
            "monthly_fee": "-",
            "source": "-",
            "as_of": "-",
            "notes": "",
        }
    return {
        "profile": profile.label,
        "monthly_fee": f"{profile.monthly_fee:.2f}",
        "source": profile.source,
        "as_of": profile.as_of,
        "notes": profile.notes,
    }


class GreekEnergyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise."""
        self._data: dict[str, Any] = {}

    async def _async_validate_key(self, api_key: str) -> str | None:
        """Return an error key, or None if the token works."""
        client = EntsoeClient(async_get_clientsession(self.hass), api_key)
        now = dt_util.utcnow()
        try:
            await client.async_get_prices(now - timedelta(days=1), now)
        except EntsoeAuthError:
            return "invalid_auth"
        except EntsoeError:
            _LOGGER.exception("Error validating ENTSO-E token")
            return "cannot_connect"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the token and the supplier."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            if error := await self._async_validate_key(user_input[CONF_API_KEY]):
                errors["base"] = error
            else:
                self._data = dict(user_input)
                return await self.async_step_tariff()

        schema = _API_KEY_SCHEMA.extend(
            _profile_schema(
                (user_input or {}).get(CONF_PROFILE, next(iter(PROFILES)))
            ).schema
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm or adjust the tariff values."""
        profile_key = self._data.get(CONF_PROFILE)
        if user_input is not None:
            return self.async_create_entry(
                title="Τιμές ρεύματος Ελλάδας", data={**self._data, **user_input}
            )
        return self.async_show_form(
            step_id="tariff",
            data_schema=_tariff_schema(tariff_defaults(profile_key, {})),
            description_placeholders=_profile_placeholders(profile_key),
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := await self._async_validate_key(user_input[CONF_API_KEY]):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates=user_input
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=_API_KEY_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Options flow."""
        return GreekEnergyOptionsFlow()


class GreekEnergyOptionsFlow(OptionsFlow):
    """Change supplier and tariff settings after setup."""

    def __init__(self) -> None:
        """Initialise."""
        self._profile: str | None = None

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the supplier profile."""
        if user_input is not None:
            self._profile = user_input[CONF_PROFILE]
            return await self.async_step_tariff()
        return self.async_show_form(
            step_id="init",
            data_schema=_profile_schema(self._current.get(CONF_PROFILE, CUSTOM)),
        )

    async def async_step_tariff(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm or adjust the tariff values."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_PROFILE: self._profile, **user_input}
            )
        current = self._current
        # Keep the user's own tweaks if the profile did not change.
        profile_for_defaults = (
            None if self._profile == current.get(CONF_PROFILE) else self._profile
        )
        return self.async_show_form(
            step_id="tariff",
            data_schema=_tariff_schema(tariff_defaults(profile_for_defaults, current)),
            description_placeholders=_profile_placeholders(self._profile),
        )
