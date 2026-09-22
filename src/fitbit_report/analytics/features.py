from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitbit_report.db.models import DailyActivity, JournalEvent, ProductivityCheckin, SleepSession


@dataclass(frozen=True)
class DayFeatures:
    day: date
    sleep_duration_min: float | None
    steps: float | None
    caffeine_total_mg: float | None
    nicotine_events: int
    morning_energy: int | None
    evening_productivity: float | None
    stress: int | None


def build_day_features(session: Session, day: date, timezone: ZoneInfo) -> DayFeatures:
    del timezone
    sleep = session.scalar(select(SleepSession).where(SleepSession.record_date == day))
    activity = session.scalar(select(DailyActivity).where(DailyActivity.record_date == day))
    morning = session.scalar(
        select(ProductivityCheckin).where(
            ProductivityCheckin.local_date == day, ProductivityCheckin.period == "morning"
        )
    )
    evening = session.scalar(
        select(ProductivityCheckin).where(
            ProductivityCheckin.local_date == day, ProductivityCheckin.period == "evening"
        )
    )
    events = list(session.scalars(select(JournalEvent).where(JournalEvent.occurred_at.is_not(None))))
    day_events = [event for event in events if event.occurred_at.date() == day]
    caffeine = sum(event.quantity or 0 for event in day_events if event.category == "caffeine")
    nicotine = sum(1 for event in day_events if event.category == "nicotine")
    return DayFeatures(
        day=day,
        sleep_duration_min=sleep.minutes_asleep if sleep else None,
        steps=activity.steps if activity else None,
        caffeine_total_mg=caffeine or None,
        nicotine_events=nicotine,
        morning_energy=morning.energy if morning else None,
        evening_productivity=evening.work_quality if evening else None,
        stress=evening.stress if evening else None,
    )
