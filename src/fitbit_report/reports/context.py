import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from statistics import fmean
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitbit_report.db.models import (
    BodyMeasurement,
    DailyActivity,
    ExerciseSession,
    HeartRateDaily,
    HeartRateIntraday,
    HrvMeasurement,
    JournalEvent,
    MealPhotoAnalysis,
    MealTextAnalysis,
    ProductivityCheckin,
    SleepSession,
    TrainingLog,
)
from fitbit_report.memory.service import list_relevant_memories
from fitbit_report.analytics.personal import build_personal_state
from fitbit_report.i18n import Locale
from fitbit_report.reports.baseline import build_personal_baselines
from fitbit_report.types import DateRange, ReportType


@dataclass(frozen=True)
class ReportContext:
    report_type: ReportType
    period: DateRange
    recent_days: list[dict]
    baselines: dict
    events: list[dict]
    memories: list[dict]
    corrections: list[int]
    productivity_context: dict = field(default_factory=dict)
    health: dict[str, object] = field(default_factory=dict)
    personal_factors: list[dict] = field(default_factory=list)
    personal_state: dict = field(default_factory=dict)
    confirmed_facts: list[dict] = field(default_factory=list)
    feedback: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__


def build_report_context(
    session: Session,
    report_type: ReportType,
    period: DateRange,
    timezone_name: str = "Europe/Kiev",
    locale: Locale = "ru",
) -> ReportContext:
    zone = ZoneInfo(timezone_name)
    all_events = list(session.scalars(select(JournalEvent).order_by(JournalEvent.occurred_at.desc())))
    factor_start = period.start - timedelta(days=27)
    events = [
        item for item in all_events
        if _local_date(item.occurred_at, zone) >= period.start
        and _local_date(item.occurred_at, zone) <= period.end
    ]
    checkins = list(session.scalars(
        select(ProductivityCheckin)
        .where(
            ProductivityCheckin.local_date >= period.start,
            ProductivityCheckin.local_date <= period.end,
        )
        .order_by(ProductivityCheckin.local_date.desc())
    ))
    factor_checkins = list(session.scalars(
        select(ProductivityCheckin)
        .where(
            ProductivityCheckin.local_date >= factor_start,
            ProductivityCheckin.local_date <= period.end,
        )
        .order_by(ProductivityCheckin.local_date.desc())
    ))
    factor_events = [
        item for item in all_events
        if factor_start <= _local_date(item.occurred_at, zone) <= period.end
    ]
    memory = list_relevant_memories(session, period.start, period.end, set(), limit=20)
    baselines = build_personal_baselines(session, period.start, timezone_name)
    health = _build_health_context(session, period, zone)
    text_meal_analyses = session.scalars(select(MealTextAnalysis)).all()
    health["nutrition"] = _structured_nutrition(
        health["nutrition"],
        events,
        text_meal_analyses,
        zone,
        health.get("fatsecret_food_entries", []),
        locale,
    )
    health.pop("fatsecret_food_entries", None)
    health["nutrition_summary"] = _nutrition_summary(health["nutrition"])
    health["data_completeness"]["categories"]["nutrition"]["records"] = len(
        health["nutrition"]
    )
    productivity_context = _build_productivity_context(
        session, period, zone, checkins, events, health, baselines
    )
    personal_factors = _build_personal_factors(
        factor_events, factor_checkins, period, zone, locale
    )
    return ReportContext(
        report_type=report_type,
        period=period,
        recent_days=[_checkin_record_payload(item, zone) for item in checkins],
        productivity_context=productivity_context,
        baselines=baselines,
        events=[_journal_event_payload(item, zone) for item in events],
        memories=[item.__dict__ for item in memory.items],
        corrections=memory.correction_ids,
        health=health,
        personal_factors=personal_factors,
        personal_state=build_personal_state(
            as_of=period.end,
            baselines=baselines,
            health=health,
            productivity_context=productivity_context,
            personal_factors=personal_factors,
            locale=locale,
        ),
        confirmed_facts=memory.facts,
        feedback=memory.feedback,
    )


def _local_date(value: datetime, zone: ZoneInfo) -> date:
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    return value.astimezone(zone).date()


def _local_datetime(
    value: datetime | None,
    zone: ZoneInfo,
    naive_timezone: ZoneInfo | dt_timezone,
) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=naive_timezone)
    return value.astimezone(zone)


def _journal_event_payload(row: JournalEvent, zone: ZoneInfo) -> dict:
    return {
        "id": row.id,
        "category": row.category,
        "subtype": row.subtype,
        "occurred_at": _local_datetime(row.occurred_at, zone, zone),
        "quantity": row.quantity,
        "unit": row.unit,
        "dose": row.dose,
        "dose_unit": row.dose_unit,
        "duration_min": row.duration_min,
        "intensity": row.intensity,
        "note": row.note,
        "original_text": row.original_text,
        "created_at": _local_datetime(row.created_at, zone, dt_timezone.utc),
    }


_PRIVATE_FACTOR_TERMS = (
    "мастурбац",
    "masturb",
    "sexual_activity",
    "интим",
)


def _is_personal_factor(event: JournalEvent) -> bool:
    if event.category in {
        "caffeine",
        "nicotine",
        "training",
        "alcohol",
        "illness",
        "mood",
        "stress",
        "masturbation",
        "sexual_activity",
    }:
        return True
    if event.category != "note":
        return False
    text = f"{event.note or ''} {event.original_text or ''}".lower()
    return any(term in text for term in _PRIVATE_FACTOR_TERMS)


def _build_personal_factors(
    events: list[JournalEvent],
    checkins: list[ProductivityCheckin],
    period: DateRange,
    zone: ZoneInfo,
    locale: Locale = "ru",
) -> list[dict]:
    factors: dict[str, list[JournalEvent]] = {}
    for event in events:
        if _is_personal_factor(event):
            key = event.category if event.category != "note" else "private_note"
            factors.setdefault(key, []).append(event)

    checkins_by_day: dict[date, list[ProductivityCheckin]] = {}
    for checkin in checkins:
        checkins_by_day.setdefault(checkin.local_date, []).append(checkin)

    result = []
    for name, rows in sorted(factors.items()):
        daily_counts: dict[date, int] = {}
        for row in rows:
            local_day = _local_date(row.occurred_at, zone)
            daily_counts[local_day] = daily_counts.get(local_day, 0) + 1
        following_days = []
        for day in sorted(daily_counts):
            next_day = day.fromordinal(day.toordinal() + 1)
            if period.start <= next_day <= period.end and next_day in checkins_by_day:
                values = [
                    {
                        "period": item.period,
                        "energy": item.energy,
                        "mood": item.mood,
                        "stress": item.stress,
                        "focus": item.focus,
                        "work_quality": item.work_quality,
                    }
                    for item in checkins_by_day[next_day]
                ]
                following_days.append({"factor_day": day, "next_day": next_day, "checkins": values})
        outcome_by_day: dict[date, dict[str, float]] = {}
        for day, day_rows in checkins_by_day.items():
            numeric: dict[str, list[float]] = {}
            for item in day_rows:
                for field_name in ("energy", "mood", "stress", "focus", "work_quality"):
                    value = getattr(item, field_name)
                    if value is not None:
                        numeric.setdefault(field_name, []).append(float(value))
            outcome_by_day[day] = {
                field_name: fmean(values)
                for field_name, values in numeric.items()
                if values
            }
        factor_next_days = {
            day.fromordinal(day.toordinal() + 1)
            for day in daily_counts
            if day.fromordinal(day.toordinal() + 1) in outcome_by_day
        }
        comparisons = {}
        for field_name in ("energy", "mood", "stress", "focus", "work_quality"):
            with_factor = [
                values[field_name]
                for day, values in outcome_by_day.items()
                if day in factor_next_days and field_name in values
            ]
            without_factor = [
                values[field_name]
                for day, values in outcome_by_day.items()
                if day not in factor_next_days and field_name in values
            ]
            comparisons[field_name] = {
                "after_mean": round(fmean(with_factor), 2) if with_factor else None,
                "control_mean": round(fmean(without_factor), 2) if without_factor else None,
                "difference": round(fmean(with_factor) - fmean(without_factor), 2)
                if with_factor and without_factor else None,
                "after_samples": len(with_factor),
                "control_samples": len(without_factor),
                "confidence": "insufficient" if len(with_factor) < 3 or len(without_factor) < 3 else "exploratory",
            }
        result.append({
            "factor": name,
            "occurrences": len(rows),
            "days": sorted(daily_counts),
            "daily_counts": [{"day": day, "count": count} for day, count in sorted(daily_counts.items())],
            "following_day_checkins": following_days,
            "next_day_comparisons": comparisons,
            "interpretation_rule": (
                "A next-day observation does not establish causality; repeated comparisons are required."
                if locale == "en"
                else "Наблюдение следующего дня не доказывает причинность; нужны повторяющиеся сравнения."
            ),
        })
    return result


def _checkin_record_payload(row: ProductivityCheckin, zone: ZoneInfo) -> dict:
    return {
        "id": row.id,
        "local_date": row.local_date,
        "original_text": row.original_text,
        **_checkin_payload(row, zone),
    }


def _structured_nutrition(
    photo_meals: list[dict],
    events: list[JournalEvent],
    text_analyses: list[MealTextAnalysis],
    zone: ZoneInfo,
    fatsecret_entries: list = (),
    locale: Locale = "ru",
) -> list[dict]:
    records = []
    for meal in photo_meals:
        analysis = meal.get("analysis") or {}
        records.append({
            "source": "photo",
            "record_id": meal["record_id"],
            "occurred_at": meal["occurred_at"],
            "meal_type": meal["meal_type"],
            "summary": analysis.get("summary"),
            "items": analysis.get("items") or [],
            "calories": {
                "min": analysis.get("total_calories_min"),
                "max": analysis.get("total_calories_max"),
            },
            "macros": {
                "protein_g": {
                    "min": analysis.get("total_protein_g_min"),
                    "max": analysis.get("total_protein_g_max"),
                },
                "carbohydrates_g": {
                    "min": analysis.get("total_carbohydrates_g_min"),
                    "max": analysis.get("total_carbohydrates_g_max"),
                },
                "fat_g": {
                    "min": analysis.get("total_fat_g_min"),
                    "max": analysis.get("total_fat_g_max"),
                },
            },
            "confidence": analysis.get("confidence", "insufficient"),
            "uncertainty": analysis.get("uncertainty"),
            "analysis": analysis,
        })
    analysis_by_event = {
        item.journal_event_id: _load_text_analysis(item)
        for item in text_analyses
    }
    for event in events:
        if event.category != "meal":
            continue
        analysis = analysis_by_event.get(event.id)
        item = {
            "name": event.note or event.original_text,
            "portion": None,
            "confidence": "insufficient",
        }
        record = {
            "source": "text",
            "record_id": event.id,
            "occurred_at": _local_datetime(event.occurred_at, zone, zone),
            "meal_type": event.subtype or "other",
            "summary": event.note or event.original_text,
            "items": [item],
            "calories": {"min": None, "max": None},
            "macros": {
                "protein_g": {"min": None, "max": None},
                "carbohydrates_g": {"min": None, "max": None},
                "fat_g": {"min": None, "max": None},
            },
            "confidence": "insufficient",
            "uncertainty": (
                "The meal was logged as text without portion or nutrient estimates."
                if locale == "en"
                else "Питание записано текстом без оценки порции и нутриентов."
            ),
            "analysis": analysis,
        }
        if analysis is not None:
            record["items"] = analysis.get("items") or record["items"]
            record["calories"] = {
                "min": analysis.get("total_calories_min"),
                "max": analysis.get("total_calories_max"),
            }
            record["macros"] = {
                "protein_g": {
                    "min": analysis.get("total_protein_g_min"),
                    "max": analysis.get("total_protein_g_max"),
                },
                "carbohydrates_g": {
                    "min": analysis.get("total_carbohydrates_g_min"),
                    "max": analysis.get("total_carbohydrates_g_max"),
                },
                "fat_g": {
                    "min": analysis.get("total_fat_g_min"),
                    "max": analysis.get("total_fat_g_max"),
                },
            }
            record["confidence"] = analysis.get("confidence", "insufficient")
            record["uncertainty"] = analysis.get(
                "uncertainty", record["uncertainty"]
            )
        records.append(record)
    records.extend(_fatsecret_nutrition(fatsecret_entries, zone, locale))
    return sorted(records, key=lambda item: str(item["occurred_at"]))


def _fatsecret_nutrition(
    entries: list,
    zone: ZoneInfo,
    locale: Locale = "ru",
) -> list[dict]:
    grouped: dict[tuple[date, str, object], list] = {}
    for entry in entries:
        meal_time = entry.meal_time
        key = (entry.report_date, entry.meal_type, meal_time)
        grouped.setdefault(key, []).append(entry)

    def total(rows: list, field: str) -> float | None:
        values = [getattr(row, field) for row in rows if getattr(row, field) is not None]
        return round(sum(values), 2) if values else None

    records = []
    for (report_date, meal_type, meal_time), rows in grouped.items():
        occurred_at = (
            _local_datetime(meal_time, zone, zone)
            if meal_time is not None
            else datetime.combine(report_date, time(12, 0), tzinfo=zone)
        )
        items = [
            {
                "name": row.food_name,
                "portion": row.serving,
                "calories": row.calories,
                "fat_g": row.fat_g,
                "saturated_fat_g": row.saturated_fat_g,
                "carbohydrates_g": row.carbohydrates_g,
                "fiber_g": row.fiber_g,
                "sugar_g": row.sugar_g,
                "protein_g": row.protein_g,
                "sodium_mg": row.sodium_mg,
                "cholesterol_mg": row.cholesterol_mg,
                "potassium_mg": row.potassium_mg,
            }
            for row in rows
        ]
        calories = total(rows, "calories")
        fat = total(rows, "fat_g")
        carbohydrates = total(rows, "carbohydrates_g")
        protein = total(rows, "protein_g")
        records.append(
            {
                "source": "fatsecret",
                "record_id": f"fatsecret:{report_date}:{meal_type}",
                "occurred_at": occurred_at,
                "meal_type": meal_type,
                "summary": ", ".join(row.food_name for row in rows),
                "items": items,
                "calories": {"min": calories, "max": calories},
                "macros": {
                    "protein_g": {"min": protein, "max": protein},
                    "carbohydrates_g": {"min": carbohydrates, "max": carbohydrates},
                    "fat_g": {"min": fat, "max": fat},
                },
                "confidence": "high",
                "uncertainty": (
                    "Exact values come from the FatSecret export; the timestamp uses the saved meal time."
                    if locale == "en"
                    else "Точные значения взяты из выгрузки FatSecret; время привязано к сохранённому времени приёма пищи."
                ),
                "analysis": {"source": "fatsecret"},
            }
        )
    return records


def _load_text_analysis(record: MealTextAnalysis) -> dict | None:
    if record.status != "success" or not record.analysis_json:
        return None
    try:
        payload = json.loads(record.analysis_json)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _nutrition_summary(records: list[dict]) -> dict:
    photo_count = sum(item["source"] == "photo" for item in records)
    text_count = sum(item["source"] == "text" for item in records)
    calorie_mins = [item["calories"]["min"] for item in records if item["calories"]["min"] is not None]
    calorie_maxs = [item["calories"]["max"] for item in records if item["calories"]["max"] is not None]
    summary = {
        "meals": len(records),
        "photo_meals": photo_count,
        "text_meals": text_count,
        "estimated_calories_min": round(sum(calorie_mins), 1) if calorie_mins else None,
        "estimated_calories_max": round(sum(calorie_maxs), 1) if calorie_maxs else None,
    }
    fatsecret_count = sum(item["source"] == "fatsecret" for item in records)
    if fatsecret_count:
        summary["fatsecret_meals"] = fatsecret_count
    return summary


def _build_health_context(
    session: Session, period: DateRange, zone: ZoneInfo
) -> dict[str, list[dict]]:
    sleep_history_start = period.start - timedelta(days=27)
    sleep_history = session.scalars(
        select(SleepSession)
        .where(
            SleepSession.record_date >= sleep_history_start,
            SleepSession.record_date <= period.end,
        )
        .order_by(SleepSession.record_date)
    ).all()
    sleep = [row for row in sleep_history if period.start <= row.record_date <= period.end]
    activity = session.scalars(
        select(DailyActivity)
        .where(DailyActivity.record_date >= period.start, DailyActivity.record_date <= period.end)
        .order_by(DailyActivity.record_date)
    ).all()
    heart_rate = session.scalars(
        select(HeartRateDaily)
        .where(HeartRateDaily.record_date >= period.start, HeartRateDaily.record_date <= period.end)
        .order_by(HeartRateDaily.record_date)
    ).all()
    hrv = session.scalars(
        select(HrvMeasurement)
        .where(HrvMeasurement.record_date >= period.start, HrvMeasurement.record_date <= period.end)
        .order_by(HrvMeasurement.record_date, HrvMeasurement.measured_at)
    ).all()
    body = session.scalars(
        select(BodyMeasurement)
        .where(BodyMeasurement.record_date >= period.start, BodyMeasurement.record_date <= period.end)
        .order_by(BodyMeasurement.record_date, BodyMeasurement.measurement_type)
    ).all()
    exercise_sessions = session.scalars(
        select(ExerciseSession)
        .where(
            ExerciseSession.record_date >= period.start,
            ExerciseSession.record_date <= period.end,
        )
        .order_by(ExerciseSession.record_date, ExerciseSession.start_time)
    ).all()
    photo_meals = session.scalars(
        select(MealPhotoAnalysis)
        .where(MealPhotoAnalysis.status == "confirmed")
        .order_by(MealPhotoAnalysis.occurred_at)
    ).all()
    intraday = session.scalars(
        select(HeartRateIntraday)
        .where(
            HeartRateIntraday.record_date >= period.start,
            HeartRateIntraday.record_date <= period.end,
        )
    ).all()
    training_logs = session.scalars(
        select(TrainingLog)
        .where(
            TrainingLog.status == "success",
            TrainingLog.occurred_at >= datetime.combine(period.start, datetime.min.time()),
            TrainingLog.occurred_at < datetime.combine(period.end + timedelta(days=1), datetime.min.time()),
        )
        .order_by(TrainingLog.occurred_at)
    ).all()
    from fitbit_report.journal.fatsecret import latest_fatsecret_entries

    fatsecret_entries = latest_fatsecret_entries(session, period.start, period.end)

    return {
        "sleep": [
            {
                "record_date": row.record_date,
                "start_time": _local_datetime(row.start_time, zone, dt_timezone.utc),
                "end_time": _local_datetime(row.end_time, zone, dt_timezone.utc),
                "minutes_asleep": row.minutes_asleep,
                "minutes_in_bed": row.minutes_in_bed,
                "efficiency": row.efficiency,
            }
            for row in sleep
        ],
        "sleep_timing_history": [
            {
                "record_date": row.record_date,
                "start_time": _local_datetime(row.start_time, zone, dt_timezone.utc),
                "end_time": _local_datetime(row.end_time, zone, dt_timezone.utc),
                "minutes_asleep": row.minutes_asleep,
                "minutes_in_bed": row.minutes_in_bed,
            }
            for row in sleep_history
        ],
        "activity": [
            {
                "record_date": row.record_date,
                "steps": row.steps,
                "distance": row.distance,
                "calories_out": row.calories_out,
                "active_zone_minutes": row.active_zone_minutes,
            }
            for row in activity
        ],
        "exercise_sessions": [
            {
                "record_date": row.record_date,
                "start_time": _local_datetime(row.start_time, zone, dt_timezone.utc),
                "end_time": _local_datetime(row.end_time, zone, dt_timezone.utc),
                "exercise_type": row.exercise_type,
                "display_name": row.display_name,
                "active_duration_min": row.active_duration_min,
                "calories_kcal": row.calories_kcal,
                "distance_km": row.distance_km,
                "steps": row.steps,
                "average_heart_rate_bpm": row.average_heart_rate_bpm,
                "active_zone_minutes": row.active_zone_minutes,
                "details": _parse_json_object(row.details_json),
            }
            for row in exercise_sessions
        ],
        "gym_training": [
            {
                "record_id": row.id,
                "occurred_at": _local_datetime(row.occurred_at, zone, zone),
                "source": row.source_type,
                "analysis": _parse_json_object(row.analysis_json),
            }
            for row in training_logs
        ],
        "nutrition": _confirmed_photo_meals(photo_meals, period, zone),
        "fatsecret_food_entries": fatsecret_entries,
        "heart_rate": [
            {
                "record_date": row.record_date,
                "resting_heart_rate": row.resting_heart_rate,
            }
            for row in heart_rate
        ],
        "heart_rate_intraday_summary": _summarize_intraday_heart_rate(intraday),
        "hrv": [
            {
                "record_date": row.record_date,
                "measured_at": _local_datetime(row.measured_at, zone, dt_timezone.utc),
                "rmssd": row.rmssd,
                "coverage": row.coverage,
            }
            for row in hrv
        ],
        "body": [
            {
                "record_date": row.record_date,
                "measurement_type": row.measurement_type,
                "value": row.value,
                "unit": row.unit,
            }
            for row in body
        ],
        "weight_summary": _weight_summary(body),
        "data_completeness": _data_completeness(
            sleep=sleep,
            activity=activity,
            exercise=exercise_sessions,
            gym_training=training_logs,
            weight=[row for row in body if row.measurement_type == "weight"],
            heart_rate=heart_rate,
            hrv=hrv,
            nutrition=_confirmed_photo_meals(photo_meals, period, zone) + fatsecret_entries,
        ),
    }


_PRODUCTIVITY_FIELDS = (
    "energy",
    "sleep_quality",
    "persistence",
    "work_quality",
    "focus",
    "mood",
    "stress",
    "deep_work_min",
    "priority",
    "note",
)


def _build_productivity_context(
    session: Session,
    period: DateRange,
    zone: ZoneInfo,
    checkins: list[ProductivityCheckin],
    events: list[JournalEvent],
    health: dict[str, object],
    baselines: dict,
) -> dict:
    previous_start = period.start - timedelta(days=1)
    previous_end = period.end - timedelta(days=1)
    previous_activity = session.scalars(
        select(DailyActivity).where(
            DailyActivity.record_date >= previous_start,
            DailyActivity.record_date <= previous_end,
        )
    ).all()
    previous_exercises = session.scalars(
        select(ExerciseSession).where(
            ExerciseSession.record_date >= previous_start,
            ExerciseSession.record_date <= previous_end,
        )
    ).all()
    activity_by_day = {row.record_date: row for row in previous_activity}
    exercises_by_day: dict[date, list[ExerciseSession]] = {}
    for row in previous_exercises:
        exercises_by_day.setdefault(row.record_date, []).append(row)

    checkins_by_day: dict[date, dict[str, dict]] = {}
    for row in checkins:
        checkins_by_day.setdefault(row.local_date, {})[row.period] = _checkin_payload(row, zone)

    current_exercises = health.get("exercise_sessions", [])
    current_sleep = health.get("sleep", [])
    current_nutrition = health.get("nutrition", [])
    exercise_by_day: dict[date, list[dict]] = {}
    for row in current_exercises:
        exercise_by_day.setdefault(row["record_date"], []).append(row)
    nutrition_by_day: dict[date, list[dict]] = {}
    for row in current_nutrition:
        nutrition_by_day.setdefault(_local_date(row["occurred_at"], zone), []).append(row)
    events_by_day: dict[date, list[JournalEvent]] = {}
    for row in events:
        events_by_day.setdefault(_local_date(row.occurred_at, zone), []).append(row)

    days = []
    current_day = period.start
    while current_day <= period.end:
        day_checkins = checkins_by_day.get(current_day, {})
        previous_day = current_day - timedelta(days=1)
        previous_activity_row = activity_by_day.get(previous_day)
        previous_day_exercises = exercises_by_day.get(previous_day, [])
        sleep_rows = [row for row in current_sleep if row["record_date"] == current_day]
        same_day_activity = next(
            (
                row
                for row in health.get("activity", [])
                if row["record_date"] == current_day
            ),
            None,
        )
        timeline = _productivity_timeline(
            current_day,
            day_checkins,
            events_by_day.get(current_day, []),
            exercise_by_day.get(current_day, []),
            nutrition_by_day.get(current_day, []),
            zone,
        )
        days.append({
            "date": current_day,
            "morning": day_checkins.get("morning"),
            "evening": day_checkins.get("evening"),
            "changes": _checkin_changes(day_checkins),
            "health_before_day": {
                "sleep_minutes_asleep": sum(
                    row["minutes_asleep"] or 0 for row in sleep_rows
                ) or None,
                "sleep_minutes_in_bed": sum(
                    row["minutes_in_bed"] or 0 for row in sleep_rows
                ) or None,
                "same_day_steps": same_day_activity["steps"] if same_day_activity else None,
                "previous_day_steps": previous_activity_row.steps if previous_activity_row else None,
                "previous_day_exercise_minutes": round(
                    sum(row.active_duration_min or 0 for row in previous_day_exercises), 1
                ) or None,
                "previous_day_exercise_count": len(previous_day_exercises),
            },
            "timeline": timeline,
        })
        current_day += timedelta(days=1)

    baseline_metrics = (
        baselines.get("windows", {}).get("28d", {}).get("metrics", {})
    )
    baseline_reference = {
        key: baseline_metrics[key]
        for key in (
            "productivity.energy",
            "productivity.focus",
            "productivity.work_quality",
            "productivity.persistence",
            "productivity.deep_work_min",
        )
        if key in baseline_metrics
    }
    return {
        "period": {"start": period.start, "end": period.end},
        "summary": _productivity_summary(checkins),
        "baseline_28d": baseline_reference,
        "days": days,
    }


def _checkin_payload(row: ProductivityCheckin, zone: ZoneInfo) -> dict:
    return {
        "period": row.period,
        "recorded_at": _local_datetime(row.created_at, zone, dt_timezone.utc),
        **{field: getattr(row, field) for field in _PRODUCTIVITY_FIELDS},
    }


def _productivity_summary(rows: list[ProductivityCheckin]) -> dict:
    return {
        "checkin_days": len({row.local_date for row in rows}),
        "morning_checkins": sum(row.period == "morning" for row in rows),
        "evening_checkins": sum(row.period == "evening" for row in rows),
        "average_energy": _average_field(rows, "energy"),
        "average_focus": _average_field(rows, "focus"),
        "average_work_quality": _average_field(rows, "work_quality"),
        "average_persistence": _average_field(rows, "persistence"),
        "total_deep_work_min": sum(row.deep_work_min or 0 for row in rows),
    }


def _average_field(rows: list[ProductivityCheckin], field: str) -> float | None:
    values = [getattr(row, field) for row in rows if getattr(row, field) is not None]
    return round(sum(values) / len(values), 1) if values else None


def _checkin_changes(checkins: dict[str, dict]) -> dict:
    morning = checkins.get("morning") or {}
    evening = checkins.get("evening") or {}
    changes = {}
    for metric in ("energy", "mood", "stress", "focus", "work_quality", "persistence"):
        before = morning.get(metric)
        after = evening.get(metric)
        if before is not None and after is not None:
            changes[f"{metric}_evening_minus_morning"] = after - before
    return changes


def _productivity_timeline(
    day: date,
    checkins: dict[str, dict],
    events: list[JournalEvent],
    exercises: list[dict],
    meals: list[dict],
    zone: ZoneInfo,
) -> list[dict]:
    timeline = []
    for period, row in checkins.items():
        timeline.append({
            "type": "checkin",
            "at": row["recorded_at"],
            "period": period,
            "energy": row["energy"],
            "focus": row["focus"],
            "mood": row["mood"],
            "stress": row["stress"],
        })
    for row in events:
        if row.category == "meal":
            continue
        timeline.append({
            "type": "journal",
            "at": _local_datetime(row.occurred_at, zone, zone),
            "category": row.category,
            "subtype": row.subtype,
            "quantity": row.quantity,
            "unit": row.unit,
            "dose": row.dose,
            "dose_unit": row.dose_unit,
            "note": row.note,
        })
    for row in exercises:
        timeline.append({
            "type": "exercise",
            "at": row["start_time"] or row["record_date"],
            "exercise_type": row["exercise_type"],
            "active_duration_min": row["active_duration_min"],
            "calories_kcal": row["calories_kcal"],
            "average_heart_rate_bpm": row["average_heart_rate_bpm"],
        })
    for row in meals:
        analysis = row.get("analysis") or {}
        timeline.append({
            "type": "meal",
            "at": row["occurred_at"],
            "meal_type": row["meal_type"],
            "summary": analysis.get("summary"),
        })
    timeline.sort(key=lambda item: (item["at"] is None, str(item["at"])))
    return timeline


def _confirmed_photo_meals(
    rows: list[MealPhotoAnalysis], period: DateRange, zone: ZoneInfo
) -> list[dict]:
    result = []
    for row in rows:
        if not period.start <= _local_date(row.occurred_at, zone) <= period.end:
            continue
        try:
            analysis = json.loads(row.confirmed_json or "")
        except json.JSONDecodeError:
            continue
        result.append({
            "record_id": row.id,
            "occurred_at": _local_datetime(row.occurred_at, zone, zone),
            "meal_type": row.meal_type,
            "analysis": analysis,
        })
    return result


def _parse_json_object(value: str | None) -> dict | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _weight_summary(rows: list[BodyMeasurement]) -> dict:
    weights = [row for row in rows if row.measurement_type == "weight"]
    if not weights:
        return {
            "measurements": 0,
            "first_kg": None,
            "last_kg": None,
            "change_kg": None,
            "unit": "kg",
        }
    weights.sort(key=lambda row: row.record_date)
    first = float(weights[0].value)
    last = float(weights[-1].value)
    units = Counter(row.unit for row in weights)
    return {
        "measurements": len(weights),
        "first_kg": round(first, 2),
        "last_kg": round(last, 2),
        "change_kg": round(last - first, 2),
        "unit": units.most_common(1)[0][0],
    }


def _data_completeness(**groups: list[object]) -> dict:
    counts = {name: {"records": len(rows)} for name, rows in groups.items()}
    core_names = ("sleep", "activity", "heart_rate", "hrv")
    core_present = sum(bool(groups[name]) for name in core_names)
    if core_present == len(core_names):
        status = "complete"
    elif any(groups.values()):
        status = "partial"
    else:
        status = "missing"
    return {
        "status": status,
        "core_categories": list(core_names),
        "categories": counts,
    }


def _summarize_intraday_heart_rate(rows: list[HeartRateIntraday]) -> list[dict]:
    grouped: dict[date, list[int]] = {}
    for row in rows:
        grouped.setdefault(row.record_date, []).append(row.bpm)
    return [
        {
            "record_date": day,
            "samples": len(values),
            "minimum_bpm": min(values),
            "maximum_bpm": max(values),
            "average_bpm": round(sum(values) / len(values), 1),
        }
        for day, values in sorted(grouped.items())
    ]
