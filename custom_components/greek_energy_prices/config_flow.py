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
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
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
)
from .entsoe import EntsoeAuthError, EntsoeClient, EntsoeError

_LOGGER = logging.getLogger(__name__)

_API_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


def _price_selector(maximum: float) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=maximum,
            step="any",
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="€/kWh",
        )
    )


def _tariff_schema(defaults: Mapping[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_SUPPLIER_MARGIN,
                default=defaults.get(CONF_SUPPLIER_MARGIN, DEFAULT_SUPPLIER_MARGIN),
            ): _price_selector(1),
            vol.Required(
                CONF_OTHER_CHARGES,
                default=defaults.get(CONF_OTHER_CHARGES, DEFAULT_OTHER_CHARGES),
            ): _price_selector(1),
            vol.Required(
                CONF_VAT, default=defaults.get(CONF_VAT, DEFAULT_VAT)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=30,
                    step=0.5,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="%",
                )
            ),
            vol.Required(
                CONF_CHEAP_HOURS,
                default=defaults.get(CONF_CHEAP_HOURS, DEFAULT_CHEAP_HOURS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0.25,
                    max=24,
                    step=0.25,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="h",
                )
            ),
        }
    )


class GreekEnergyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup flow."""

    VERSION = 1

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
        """Ask for the token and tariff settings."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}
        if user_input is not None:
            if error := await self._async_validate_key(user_input[CONF_API_KEY]):
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="Τιμές ρεύματος Ελλάδας", data=user_input
                )

        schema = _API_KEY_SCHEMA.extend(_tariff_schema(user_input or {}).schema)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

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
    """Change tariff settings after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=_tariff_schema(current))
