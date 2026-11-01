"""Supplier tariff profiles for Greek dynamic ("orange") electricity contracts.

Greek dynamic contracts price the *supply* component per market interval as::

    supply €/kWh = B × ΤΕΑ + A

where ΤΕΑ is the HEnEx day-ahead clearing price in €/kWh, B is a fixed
coefficient (≈ low-voltage loss factor) and A a fixed base price. Regulated
charges (network, ΥΚΩ, ΕΤΜΕΑΡ, ...) and VAT come on top and are the same for
every supplier.

The values below were collected from public product pages and price
comparison sites. Suppliers change them; every profile records where the
numbers came from and when, and users can override A and B after choosing a
profile. Keep this module free of Home Assistant imports so it is unit
testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupplierProfile:
    """Published pricing of one dynamic product (supply component, excl. VAT)."""

    key: str
    supplier: str
    product: str
    multiplier: float  # B, applied to ΤΕΑ
    base_price: float  # A, €/kWh
    monthly_fee: float  # €/month, informational (not per kWh)
    hourly_tea: bool  # True: priced on the hourly ΤΕΑ, not the 15-min one
    source: str
    as_of: str  # ISO date the values were checked
    notes: str = ""

    @property
    def label(self) -> str:
        """Human readable name for selectors."""
        return f"{self.supplier} – {self.product}"


CUSTOM = "custom"

PROFILES: dict[str, SupplierProfile] = {
    profile.key: profile
    for profile in (
        SupplierProfile(
            key="dei_myhome_dynamic",
            supplier="ΔΕΗ",
            product="myHome Dynamic",
            multiplier=1.19,
            base_price=0.044,
            monthly_fee=9.0,
            hourly_tea=True,
            source="https://techmaniacs.gr/dei-myhome-dynamic-gia-idiotes-anakoinothike-to-neo-programma-ilektrikis-energeias/",
            as_of="2026-11-01",
            notes="1,19 × ΤΕΑ ώρας + 0,044 €/kWh, πάγιο 9 €/μήνα.",
        ),
        SupplierProfile(
            key="protergia_dynamic_one_home",
            supplier="Protergia",
            product="Dynamic One Home",
            multiplier=1.2,
            base_price=0.035,
            monthly_fee=9.90,
            hourly_tea=True,
            source="https://www.protergia.gr/en/home/electric-energy/dynamic-one-home/",
            as_of="2026-11-01",
            notes=(
                "1,2 × ΤΕΑ ώρας + 0,035 €/kWh, πάγιο 9,90 €/μήνα. Επιβεβαιώθηκε "
                "με τις ωριαίες τιμές του Dynamic Home Check Tool (Σεπτ. 2026)."
            ),
        ),
        SupplierProfile(
            key="zenith_power_home_flow",
            supplier="ZeniΘ",
            product="Power Home Flow",
            multiplier=1.2,
            base_price=0.100,
            monthly_fee=15.0,
            hourly_tea=True,
            source="https://zenith.gr/el/for-the-home/electricity/power-home-flow/",
            as_of="2026-11-01",
            notes="Βασική τιμή 0,100 €/kWh, Β = 1,2, πάγιο 15 €/μήνα.",
        ),
    )
}


def get_profile(key: str | None) -> SupplierProfile | None:
    """Profile by key, or None for custom/unknown."""
    if key is None or key == CUSTOM:
        return None
    return PROFILES.get(key)
