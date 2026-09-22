from collections import defaultdict
from datetime import date, timedelta
from statistics import mean, median, pstdev
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitbit_report.db.models import (
    BodyMeasurement,
    DailyActivity,
    ExerciseSession,
    HeartRateDaily,
    HrvMeasurement,
    ProductivityCheckin,
    SleepSession,
)


WINDOW_DAYS = (7, 14, 28)
MIN_USABLE_SAMPLES = 3
PRODUCTIVITY_FIELDS = (
    "energy",
    "sleep_quality",
    "persistence",
    "work_quality",
    "focus",
    "mood",
    "stress",
    "deep_work_min",
)
SUM_METRICS = {
    "sleep.minutes_asleep",
    "sleep.minutes_in_bed",
    "activity.steps",
    "activity.distance",
    "activity.calories_out",
    "activity.active_zone_minutes",
    "exercise.active_duration_min",
    "exercise.calories_kcal",
    "exercise.distance_km",
    "exercise.steps",
    "exercise.active_zone_minutes",
}


def build_personal_baselines(
    session: Session,
    period_start: date,
    timezone_name: str = "Europe/Kiev",
) -> dict:
    completed_end = period_start - timedelta(days=1)
    longest_start = period_start - timedelta(days=max(WINDOW_DAYS))
    daily_observations = _collect_daily_observations(
        session, longest_start, completed_end, ZoneInfo(timezone_name)
    )
    windows = {}
    for window_days in WINDOW_DAYS:
        window_start = period_start - timedelta(days=window_days)
        metrics = {}
        for metric, values_by_day in daily_observations.items():
            values = [
                value
                for day, value in values_by_day.items()
                if window_start <= day <= completed_end
            ]
            if values:
                metrics[metric] = _summarize(values)
        windows[f"{window_days}d"] = {
            "window_days": window_days,
            "period_start": window_start,
            "period_end": completed_end,
            "metrics": metrics,
        }
    return {
        "as_of": completed_end,
        "excluded_period_start": period_start,
        "windows": windows,
    }


def _collect_daily_observations(
    session: Session,
    start: date,
    end: date,
    zone: ZoneInfo,
) -> dict[str, dict[date, float]]:
    raw: dict[str, dict[date, list[float]]] = defaultdict(lambda: defaultdict(list))

    def add(metric: str, day: date, value: float | int | None) -> None:
        if value is not None:
            raw[metric][day].append(float(value))

    sleep = session.scalars(
        select(SleepSession).where(
            SleepSession.record_date >= start,
            SleepSession.record_date <= end,
        )
    ).all()
    for row in sleep:
        add("sleep.minutes_asleep", row.record_date, row.minutes_asleep)
        add("sleep.minutes_in_bed", row.record_date, row.minutes_in_bed)
        add("sleep.efficiency", row.record_date, row.efficiency)

    activity = session.scalars(
        select(DailyActivity).where(
            DailyActivity.record_date >= start,
            DailyActivity.record_date <= end,
        )
    ).all()
    for row in activity:
        for field in ("steps", "distance", "calories_out", "active_zone_minutes"):
            add(f"activity.{field}", row.record_date, getattr(row, field))

    heart_rate = session.scalars(
        select(HeartRateDaily).where(
            HeartRateDaily.record_date >= start,
            HeartRateDaily.record_date <= end,
        )
    ).all()
    for row in heart_rate:
        add("heart_rate.resting_heart_rate", row.record_date, row.resting_heart_rate)

    hrv = session.scalars(
        select(HrvMeasurement).where(
            HrvMeasurement.record_date >= start,
            HrvMeasurement.record_date <= end,
        )
    ).all()
    for row in hrv:
        add("hrv.rmssd", row.record_date, row.rmssd)

    body = session.scalars(
        select(BodyMeasurement).where(
            BodyMeasurement.record_date >= start,
            BodyMeasurement.record_date <= end,
        )
    ).all()
    for row in body:
        add(f"body.{row.measurement_type}", row.record_date, row.value)

    exercises = session.scalars(
        select(ExerciseSession).where(
            ExerciseSession.record_date >= start,
            ExerciseSession.record_date <= end,
        )
    ).all()
    for row in exercises:
        for field in (
            "active_duration_min",
            "calories_kcal",
            "distance_km",
            "steps",
            "active_zone_minutes",
        ):
            add(f"exercise.{field}", row.record_date, getattr(row, field))
        add("exercise.average_heart_rate_bpm", row.record_date, row.average_heart_rate_bpm)

    checkins = session.scalars(
        select(ProductivityCheckin).where(
            ProductivityCheckin.local_date >= start,
            ProductivityCheckin.local_date <= end,
        )
    ).all()
    by_day: dict[date, list[ProductivityCheckin]] = defaultdict(list)
    for row in checkins:
        by_day[row.local_date].append(row)
    for day, rows in by_day.items():
        for field in PRODUCTIVITY_FIELDS:
            preferred_period = "morning" if field == "sleep_quality" else "evening"
            selected = next(
                (row for row in rows if row.period == preferred_period and getattr(row, field) is not None),
                None,
            )
            if selected is None:
                selected = next((row for row in rows if getattr(row, field) is not None), None)
            if selected is not None:
                add(f"productivity.{field}", day, getattr(selected, field))

    result = {}
    for metric, values_by_day in raw.items():
        result[metric] = {
            day: round(sum(values) if metric in SUM_METRICS else mean(values), 2)
            for day, values in values_by_day.items()
        }
    return result


def _summarize(values: list[float]) -> dict:
    samples = len(values)
    return {
        "samples": samples,
        "average": round(mean(values), 1),
        "median": round(median(values), 1),
        "minimum": round(min(values), 1),
        "maximum": round(max(values), 1),
        "standard_deviation": round(pstdev(values), 1),
        "sample_status": _sample_status(samples),
    }


def _sample_status(samples: int) -> str:
    if samples < MIN_USABLE_SAMPLES:
        return "insufficient"
    if samples < 7:
        return "limited"
    return "usable"
