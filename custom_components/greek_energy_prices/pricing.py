"""Pure price calculations (retail price, statistics, cheapest windows)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import fmean
from zoneinfo import ZoneInfo

from .entsoe import PricePoint


@dataclass(frozen=True, slots=True)
class TariffSettings:
    """How a retail price is derived from the wholesale price (all €/kWh).

    retail = (multiplier × wholesale + supplier_margin + other_charges) × (1 + VAT)
    """

    supplier_margin: float = 0.0
    other_charges: float = 0.0
    vat_percent: float = 6.0
    wholesale_multiplier: float = 1.0

    def supply(self, wholesale_eur_kwh: float) -> float:
        """Supplier's energy price (B × ΤΕΑ + A), excluding VAT."""
        return self.wholesale_multiplier * wholesale_eur_kwh + self.supplier_margin

    def retail(self, wholesale_eur_kwh: float) -> float:
        """Final price per kWh paid by the household."""
        net = self.supply(wholesale_eur_kwh) + self.other_charges
        return net * (1 + self.vat_percent / 100)


@dataclass(frozen=True, slots=True)
class PriceInterval:
    """One market interval with both wholesale and retail price in €/kWh."""

    start: datetime
    end: datetime
    wholesale: float
    retail: float

    def as_dict(self, tz: ZoneInfo) -> dict[str, object]:
        """Serialisable form for state attributes."""
        return {
            "start": self.start.astimezone(tz).isoformat(),
            "end": self.end.astimezone(tz).isoformat(),
            "price": round(self.retail, 5),
            "wholesale": round(self.wholesale, 5),
        }


def average_hourly(points: list[PricePoint]) -> list[PricePoint]:
    """Collapse sub-hourly points into hourly averages (ΤΕΑ ώρας).

    Hours are aligned to UTC hour boundaries, which coincide with Athens hours.
    Partial hours are averaged over the points that exist.
    """
    buckets: dict[datetime, list[PricePoint]] = {}
    for point in points:
        hour = point.start.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(hour, []).append(point)
    result = []
    for hour, members in sorted(buckets.items()):
        seconds = sum((m.end - m.start).total_seconds() for m in members)
        price = (
            sum(m.price_eur_mwh * (m.end - m.start).total_seconds() for m in members)
            / seconds
        )
        result.append(PricePoint(hour, hour + timedelta(hours=1), price))
    return result


def build_intervals(
    points: list[PricePoint], settings: TariffSettings
) -> list[PriceInterval]:
    """Convert wholesale points into priced intervals."""
    return [
        PriceInterval(
            start=p.start,
            end=p.end,
            wholesale=p.price_eur_kwh,
            retail=settings.retail(p.price_eur_kwh),
        )
        for p in points
    ]


def intervals_for_day(
    intervals: list[PriceInterval], day: date, tz: ZoneInfo
) -> list[PriceInterval]:
    """Intervals whose start falls on the given local calendar day."""
    return [i for i in intervals if i.start.astimezone(tz).date() == day]


def interval_at(
    intervals: list[PriceInterval], moment: datetime
) -> PriceInterval | None:
    """Interval containing ``moment``."""
    for interval in intervals:
        if interval.start <= moment < interval.end:
            return interval
    return None


def next_interval(
    intervals: list[PriceInterval], moment: datetime
) -> PriceInterval | None:
    """First interval starting after the one containing ``moment``."""
    for interval in intervals:
        if interval.start > moment:
            return interval
    return None


@dataclass(frozen=True, slots=True)
class DayStats:
    """Retail price statistics for a day."""

    average: float
    minimum: float
    maximum: float
    cheapest_start: datetime
    most_expensive_start: datetime


def day_stats(intervals: list[PriceInterval]) -> DayStats | None:
    """Time-weighted statistics, or None without data."""
    if not intervals:
        return None
    total_seconds = sum((i.end - i.start).total_seconds() for i in intervals)
    average = (
        sum(i.retail * (i.end - i.start).total_seconds() for i in intervals)
        / total_seconds
    )
    cheapest = min(intervals, key=lambda i: i.retail)
    dearest = max(intervals, key=lambda i: i.retail)
    return DayStats(
        average=average,
        minimum=cheapest.retail,
        maximum=dearest.retail,
        cheapest_start=cheapest.start,
        most_expensive_start=dearest.start,
    )


def cheapest_intervals(
    intervals: list[PriceInterval], hours: float
) -> list[PriceInterval]:
    """The cheapest (not necessarily contiguous) intervals totalling ``hours``.

    Returned in chronological order.
    """
    if not intervals or hours <= 0:
        return []
    budget = timedelta(hours=hours)
    chosen: list[PriceInterval] = []
    used = timedelta()
    for interval in sorted(intervals, key=lambda i: (i.retail, i.start)):
        if used >= budget:
            break
        chosen.append(interval)
        used += interval.end - interval.start
    return sorted(chosen, key=lambda i: i.start)


@dataclass(frozen=True, slots=True)
class Window:
    """A contiguous block of intervals."""

    start: datetime
    end: datetime
    average: float


def cheapest_window(
    intervals: list[PriceInterval],
    duration: timedelta,
    not_before: datetime | None = None,
) -> Window | None:
    """Cheapest contiguous window of ``duration`` starting at/after ``not_before``.

    Intervals must be sorted and contiguous for a window to be considered;
    gaps in the data break windows.
    """
    candidates = [i for i in intervals if not_before is None or i.start >= not_before]
    best: Window | None = None
    for start_idx, first in enumerate(candidates):
        block: list[PriceInterval] = []
        covered = timedelta()
        expected_start = first.start
        for interval in candidates[start_idx:]:
            if interval.start != expected_start:
                break
            block.append(interval)
            covered += interval.end - interval.start
            expected_start = interval.end
            if covered >= duration:
                break
        if covered < duration:
            continue
        average = fmean(i.retail for i in block)
        if best is None or average < best.average:
            best = Window(first.start, block[-1].end, average)
    return best
