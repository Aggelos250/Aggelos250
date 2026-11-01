"""Constants for the Greek Energy Prices integration."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

DOMAIN = "greek_energy_prices"

# ENTSO-E bidding zone EIC code for Greece (IPTO / ΑΔΜΗΕ).
GREECE_BIDDING_ZONE = "10YGR-HTSO-----Y"
GREECE_TZ = ZoneInfo("Europe/Athens")

ENTSOE_API_URL = "https://web-api.tp.entsoe.eu/api"

CONF_API_KEY = "api_key"
CONF_SUPPLIER_MARGIN = "supplier_margin"
CONF_OTHER_CHARGES = "other_charges"
CONF_VAT = "vat"
CONF_CHEAP_HOURS = "cheap_hours"
CONF_PROFILE = "profile"
CONF_WHOLESALE_MULTIPLIER = "wholesale_multiplier"
CONF_HOURLY_PRICES = "hourly_prices"

DEFAULT_SUPPLIER_MARGIN = 0.0  # €/kWh
DEFAULT_OTHER_CHARGES = 0.0  # €/kWh (network, ΥΚΩ, ΕΤΜΕΑΡ, ΕΦΚ ...)
DEFAULT_VAT = 6.0  # % – VAT on electricity in Greece
DEFAULT_CHEAP_HOURS = 4
DEFAULT_WHOLESALE_MULTIPLIER = 1.0
# Greek dynamic products price on the hourly ΤΕΑ even though the market
# clears in 15-minute intervals.
DEFAULT_HOURLY_PRICES = True

# How often the coordinator runs. The API itself is only queried when the
# cached data is stale or tomorrow's prices are still missing.
UPDATE_INTERVAL = timedelta(minutes=15)
# Re-fetch at least this often even if we already have everything.
MAX_DATA_AGE = timedelta(hours=6)
# Greek day-ahead results (HEnEx / EUPHEMIA) are normally published shortly
# after 13:00 Athens time; don't hammer the API looking for them earlier.
TOMORROW_AVAILABLE_HOUR = 13
RETRY_MISSING_TOMORROW = timedelta(minutes=30)

UNIT_EUR_PER_KWH = "EUR/kWh"
