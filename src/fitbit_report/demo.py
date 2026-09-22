from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from fitbit_report.db.models import (
    Base,
    BodyMeasurement,
    DailyActivity,
    ExerciseSession,
    HeartRateDaily,
    HeartRateIntraday,
    HrvMeasurement,
    JournalEvent,
    MealTextAnalysis,
    MealTimeLog,
    PersonalFact,
    ProductivityCheckin,
    SleepSession,
    SyncRun,
)
from fitbit_report.private_storage import ensure_private_directory, restrict_private_file


def create_demo_database(
    output_path: Path,
    end_date: date,
    *,
    days: int = 35,
    seed: int = 20260915,
    timezone_name: str = "Europe/Kiev",
    force: bool = False,
) -> Path:
    """Create a deterministic SQLite database containing synthetic health data."""
    if days < 29:
        raise ValueError("Demo history must contain at least 29 days")
    output_path = Path(output_path)
    if output_path.exists():
        if not force:
            raise FileExistsError(f"Demo database already exists: {output_path}")
        output_path.unlink()

    ensure_private_directory(output_path.parent, restrict_existing=False)
    engine = create_engine(f"sqlite:///{output_path}", future=True)
    Base.metadata.create_all(engine)
    rng = random.Random(seed)
    start_date = end_date - timedelta(days=days - 1)

    with Session(engine) as session:
        for index in range(days):
            current_day = start_date + timedelta(days=index)
            is_target = current_day == end_date
            weekly_wave = math.sin(index * math.pi / 3.5)

            sleep_minutes = (
                545 if is_target else round(465 + weekly_wave * 28 + rng.uniform(-18, 18))
            )
            minutes_in_bed = sleep_minutes + round(rng.uniform(22, 42))
            bedtime_hour = 22 if index % 7 not in {4, 5} else 23
            bedtime_minute = round(28 + rng.uniform(-18, 20)) % 60
            sleep_start = _utc_datetime(
                current_day - timedelta(days=1),
                time(bedtime_hour, bedtime_minute),
                timezone_name,
            )
            sleep_end = sleep_start + timedelta(minutes=minutes_in_bed)
            session.add(
                SleepSession(
                    record_date=current_day,
                    source_record_id=10_000 + index,
                    start_time=sleep_start,
                    end_time=sleep_end,
                    minutes_asleep=sleep_minutes,
                    minutes_in_bed=minutes_in_bed,
                    efficiency=round(sleep_minutes / minutes_in_bed * 100, 1),
                    stages_json=json.dumps(
                        [
                            {"type": "LIGHT", "startTime": sleep_start.isoformat()},
                            {
                                "type": "DEEP",
                                "startTime": (sleep_start + timedelta(minutes=52)).isoformat(),
                            },
                            {
                                "type": "REM",
                                "startTime": (sleep_end - timedelta(minutes=78)).isoformat(),
                            },
                        ]
                    ),
                )
            )

            steps = (
                10_800 if is_target else round(7_600 + weekly_wave * 1_450 + rng.uniform(-850, 850))
            )
            active_minutes = (
                52 if is_target else max(12, round(34 + weekly_wave * 9 + rng.uniform(-7, 7)))
            )
            session.add(
                DailyActivity(
                    record_date=current_day,
                    source_record_id=20_000 + index,
                    steps=steps,
                    distance=round(steps * 0.00074, 2),
                    calories_out=round(1_920 + active_minutes * 7.4, 1),
                    active_zone_minutes=active_minutes,
                )
            )

            resting_hr = (
                56 if is_target else round(62 - weekly_wave * 1.8 + rng.uniform(-1.2, 1.2), 1)
            )
            session.add(
                HeartRateDaily(
                    record_date=current_day,
                    source_record_id=30_000 + index,
                    resting_heart_rate=resting_hr,
                    zones_json=json.dumps(
                        {
                            "rest": 1_020,
                            "light": 310,
                            "moderate": active_minutes,
                            "vigorous": max(0, active_minutes - 28),
                        }
                    ),
                )
            )
            for hour, offset in ((7, 4), (9, 12), (12, 18), (15, 10), (18, 24), (22, 7)):
                session.add(
                    HeartRateIntraday(
                        record_date=current_day,
                        measured_at=_utc_datetime(current_day, time(hour), timezone_name),
                        bpm=round(resting_hr + offset + rng.uniform(-3, 3)),
                        source_record_id=40_000 + index * 10 + hour,
                    )
                )

            hrv = 78 if is_target else round(58 + weekly_wave * 6 + rng.uniform(-4, 4), 1)
            session.add(
                HrvMeasurement(
                    record_date=current_day,
                    measured_at=_utc_datetime(current_day, time(6, 20), timezone_name),
                    rmssd=hrv,
                    coverage=0.96,
                    source_record_id=50_000 + index,
                )
            )

            morning_energy = 8 if is_target else _rating(6 + weekly_wave + rng.uniform(-0.8, 0.8))
            morning_focus = (
                8 if is_target else _rating(6.2 + weekly_wave * 0.7 + rng.uniform(-0.8, 0.8))
            )
            session.add(
                ProductivityCheckin(
                    local_date=current_day,
                    period="morning",
                    energy=morning_energy,
                    sleep_quality=9 if is_target else _rating(6.5 + weekly_wave),
                    persistence=None,
                    work_quality=None,
                    focus=morning_focus,
                    mood=8 if is_target else _rating(6.7 + weekly_wave * 0.6),
                    stress=3 if is_target else _rating(4.2 - weekly_wave * 0.5),
                    deep_work_min=None,
                    priority="Prepare the product release"
                    if is_target
                    else "Complete the main task",
                    note="Synthetic demo check-in",
                    original_text="synthetic morning check-in",
                )
            )
            session.add(
                ProductivityCheckin(
                    local_date=current_day,
                    period="evening",
                    energy=morning_energy,
                    sleep_quality=None,
                    persistence=_rating(morning_focus - 0.3),
                    work_quality=_rating(morning_focus + 0.2),
                    focus=morning_focus,
                    mood=_rating(morning_energy + 0.2),
                    stress=3 if is_target else _rating(4.4 - weekly_wave * 0.4),
                    deep_work_min=155 if is_target else max(35, round(105 + weekly_wave * 25)),
                    priority="Prepare the product release"
                    if is_target
                    else "Complete the main task",
                    note="Synthetic demo check-in",
                    original_text="synthetic evening check-in",
                )
            )

            _add_daily_journal(session, current_day, index, is_target, timezone_name)
            if index % 3 == 1:
                _add_exercise(session, current_day, index, timezone_name)
            if index % 7 == 0:
                session.add(
                    BodyMeasurement(
                        record_date=current_day,
                        measurement_type="weight",
                        value=round(74.8 - index * 0.018 + rng.uniform(-0.15, 0.15), 2),
                        unit="kg",
                        source_record_id=60_000 + index,
                    )
                )
            now = _utc_datetime(current_day, time(23, 55), timezone_name)
            session.add(
                SyncRun(
                    requested_date=current_day,
                    started_at=now - timedelta(seconds=7),
                    finished_at=now,
                    status="success",
                    fetched_count=13,
                    inserted_count=12,
                    normalized_count=12,
                )
            )

        session.add_all(
            [
                PersonalFact(
                    statement="A consistent bedtime is usually followed by steadier morning energy.",
                    status="active",
                    source_ids_json="[]",
                ),
                PersonalFact(
                    statement="Moderate training days generally fit the current recovery pattern.",
                    status="active",
                    source_ids_json="[]",
                ),
            ]
        )
        session.commit()

    engine.dispose()
    restrict_private_file(output_path)
    return output_path


def _rating(value: float) -> int:
    return max(1, min(10, round(value)))


def _utc_datetime(day: date, clock: time, timezone_name: str) -> datetime:
    local_value = datetime.combine(day, clock, tzinfo=ZoneInfo(timezone_name))
    return local_value.astimezone(timezone.utc)


def _add_daily_journal(
    session: Session,
    current_day: date,
    index: int,
    is_target: bool,
    timezone_name: str,
) -> None:
    caffeine_at = _utc_datetime(current_day, time(8, 35), timezone_name)
    session.add(
        JournalEvent(
            category="caffeine",
            subtype="coffee",
            occurred_at=caffeine_at,
            quantity=1,
            unit="cup",
            dose=None,
            dose_unit=None,
            duration_min=None,
            intensity=None,
            note="Morning coffee",
            original_text=f"synthetic caffeine {current_day}",
        )
    )

    meals = (
        ("breakfast", time(7, 50), "Oatmeal with berries and yogurt", 485, 24, 14, 68),
        ("lunch", time(13, 10), "Chicken, rice and vegetable salad", 690, 48, 21, 76),
        ("dinner", time(19, 20), "Salmon, potatoes and greens", 640, 43, 26, 57),
    )
    for meal_index, (meal_type, meal_time, name, calories, protein, fat, carbs) in enumerate(meals):
        occurred_at = _utc_datetime(current_day, meal_time, timezone_name)
        event = JournalEvent(
            category="meal",
            subtype=meal_type,
            occurred_at=occurred_at,
            quantity=None,
            unit=None,
            dose=None,
            dose_unit=None,
            duration_min=None,
            intensity=None,
            note=name,
            original_text=f"synthetic meal {current_day} {meal_type}",
        )
        session.add(event)
        session.flush()
        analysis = {
            "summary": name,
            "items": [
                {
                    "name": name,
                    "portion": "one serving",
                    "calories_min": calories,
                    "calories_max": calories,
                    "protein_g_min": protein,
                    "protein_g_max": protein,
                    "carbohydrates_g_min": carbs,
                    "carbohydrates_g_max": carbs,
                    "fat_g_min": fat,
                    "fat_g_max": fat,
                    "confidence": "high",
                }
            ],
            "total_calories_min": calories,
            "total_calories_max": calories,
            "total_protein_g_min": protein,
            "total_protein_g_max": protein,
            "total_carbohydrates_g_min": carbs,
            "total_carbohydrates_g_max": carbs,
            "total_fat_g_min": fat,
            "total_fat_g_max": fat,
            "uncertainty": "Synthetic nutrition values for a public demo.",
            "confidence": "high",
        }
        session.add(
            MealTextAnalysis(
                journal_event_id=event.id,
                analysis_json=json.dumps(analysis),
                status="success",
                model="synthetic-demo",
            )
        )
        session.add(
            MealTimeLog(
                meal_date=current_day,
                meal_type=meal_type,
                occurred_at=occurred_at,
                source="synthetic-demo",
            )
        )

    if is_target or index % 4 == 0:
        session.add(
            JournalEvent(
                category="mood",
                subtype="calm",
                occurred_at=_utc_datetime(current_day, time(20, 15), timezone_name),
                quantity=None,
                unit=None,
                dose=None,
                dose_unit=None,
                duration_min=None,
                intensity=8 if is_target else 7,
                note="Calm and productive day",
                original_text=f"synthetic mood {current_day}",
            )
        )


def _add_exercise(
    session: Session,
    current_day: date,
    index: int,
    timezone_name: str,
) -> None:
    start = _utc_datetime(current_day, time(17, 40), timezone_name)
    session.add(
        ExerciseSession(
            record_date=current_day,
            source_record_id=70_000 + index,
            start_time=start,
            end_time=start + timedelta(minutes=48),
            exercise_type="strength_training",
            display_name="Full-body strength",
            active_duration_min=48,
            calories_kcal=315,
            distance_km=None,
            steps=1_250,
            average_heart_rate_bpm=126,
            active_zone_minutes=34,
            details_json=json.dumps({"source": "synthetic-demo", "sets": 16}),
        )
    )
