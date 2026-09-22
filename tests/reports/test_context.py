import json
from datetime import date
from datetime import datetime
from zoneinfo import ZoneInfo

from fitbit_report.db.models import (
    BodyMeasurement,
    DailyActivity,
    ExerciseSession,
    HeartRateDaily,
    HrvMeasurement,
    JournalEvent,
    MealPhotoAnalysis,
    MealTextAnalysis,
    ProductivityCheckin,
    SleepSession,
)
from fitbit_report.reports.context import build_report_context
from fitbit_report.reports.prompts import build_prompt
from fitbit_report.types import DateRange


def test_context_is_bounded(db_session):
    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
    )

    assert context.period.start == date(2026, 8, 12)
    assert len(context.recent_days) <= 7
    assert len(context.memories) <= 20


def test_context_includes_only_events_and_checkins_from_report_period(db_session):
    zone = ZoneInfo("Europe/Kiev")
    db_session.add_all([
        JournalEvent(
            category="meal",
            subtype="breakfast",
            occurred_at=datetime(2026, 8, 12, 8, 30, tzinfo=zone),
            note="овсянка",
            original_text="/log meal breakfast овсянка",
        ),
        JournalEvent(
            category="meal",
            subtype="dinner",
            occurred_at=datetime(2026, 8, 11, 20, 0, tzinfo=zone),
            note="паста",
            original_text="/log meal dinner паста",
        ),
        ProductivityCheckin(
            local_date=date(2026, 8, 12),
            period="evening",
            energy=8,
            original_text="/checkin evening energy=8",
        ),
        ProductivityCheckin(
            local_date=date(2026, 8, 11),
            period="evening",
            energy=2,
            original_text="/checkin evening energy=2",
        ),
    ])
    db_session.flush()

    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
    )

    assert len(context.events) == 1
    assert context.events[0]["subtype"] == "breakfast"
    assert len(context.recent_days) == 1
    assert context.recent_days[0]["energy"] == 8


def test_context_includes_google_health_measurements(db_session):
    db_session.add_all([
        SleepSession(
            record_date=date(2026, 8, 12),
            minutes_asleep=519,
            minutes_in_bed=523,
            efficiency=99.2,
        ),
        DailyActivity(
            record_date=date(2026, 8, 12),
            steps=1276,
            distance=0.9229,
            calories_out=1559.7,
            active_zone_minutes=68,
        ),
        HeartRateDaily(record_date=date(2026, 8, 12), resting_heart_rate=65),
        HrvMeasurement(record_date=date(2026, 8, 12), rmssd=92.6),
        BodyMeasurement(
            record_date=date(2026, 8, 12),
            measurement_type="weight",
            value=80.5,
            unit="kg",
        ),
    ])
    db_session.flush()

    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
    )

    assert context.health["sleep"][0]["minutes_asleep"] == 519
    assert context.health["activity"][0]["steps"] == 1276
    assert context.health["heart_rate"][0]["resting_heart_rate"] == 65
    assert context.health["hrv"][0]["rmssd"] == 92.6
    assert context.health["body"][0]["value"] == 80.5


def test_context_includes_recent_sleep_timing_history(db_session):
    zone = ZoneInfo("Europe/Kiev")
    db_session.add_all([
        SleepSession(
            record_date=date(2026, 8, 11),
            start_time=datetime(2026, 8, 10, 23, 30, tzinfo=zone),
            end_time=datetime(2026, 8, 11, 7, 10, tzinfo=zone),
            minutes_asleep=440,
        ),
        SleepSession(
            record_date=date(2026, 8, 12),
            start_time=datetime(2026, 8, 11, 22, 50, tzinfo=zone),
            end_time=datetime(2026, 8, 12, 6, 40, tzinfo=zone),
            minutes_asleep=450,
        ),
    ])
    db_session.flush()

    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
    )

    assert len(context.health["sleep"]) == 1
    assert len(context.health["sleep_timing_history"]) == 2
    assert context.personal_state["current"]["sleep_start_time"] is not None
    assert context.personal_state["current"]["sleep_end_time"] is not None


def test_context_includes_personal_baselines_from_completed_days(db_session):
    db_session.add_all([
        DailyActivity(record_date=date(2026, 8, 9), steps=1000),
        DailyActivity(record_date=date(2026, 8, 10), steps=2000),
        DailyActivity(record_date=date(2026, 8, 11), steps=3000),
        DailyActivity(record_date=date(2026, 8, 12), steps=9999),
    ])
    db_session.flush()

    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
    )

    metric = context.baselines["windows"]["7d"]["metrics"]["activity.steps"]
    assert metric["average"] == 2000.0
    assert metric["samples"] == 3
    assert context.baselines["as_of"] == date(2026, 8, 11)


def test_context_includes_exercise_sessions(db_session):
    db_session.add(
        ExerciseSession(
            record_date=date(2026, 8, 12),
            start_time=datetime(2026, 8, 12, 18, tzinfo=ZoneInfo("UTC")),
            end_time=datetime(2026, 8, 12, 18, 35, tzinfo=ZoneInfo("UTC")),
            exercise_type="RUNNING",
            display_name="Evening run",
            active_duration_min=30,
            calories_kcal=380,
            distance_km=5,
            steps=6200,
            average_heart_rate_bpm=148,
            active_zone_minutes=30,
        )
    )
    db_session.flush()

    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
    )

    assert context.health["exercise_sessions"][0]["exercise_type"] == "RUNNING"
    assert context.health["exercise_sessions"][0]["active_duration_min"] == 30

    prompt = build_prompt(context)
    assert '"start_time": "2026-08-12 21:00:00+03:00"' in prompt


def test_context_includes_weight_trend_full_workout_details_and_completeness(db_session):
    db_session.add_all([
        BodyMeasurement(
            record_date=date(2026, 8, 12),
            measurement_type="weight",
            value=80.0,
            unit="kg",
        ),
        BodyMeasurement(
            record_date=date(2026, 8, 13),
            measurement_type="weight",
            value=79.4,
            unit="kg",
        ),
        ExerciseSession(
            record_date=date(2026, 8, 13),
            exercise_type="RUNNING",
            active_duration_min=30,
            details_json=json.dumps({
                "exerciseEvents": [{"exerciseEventType": "PAUSE"}],
                "splitSummaries": [{"splitType": "DISTANCE"}],
            }),
        ),
    ])
    db_session.flush()

    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 13), date(2026, 8, 13)),
    )

    assert context.health["weight_summary"] == {
        "measurements": 1,
        "first_kg": 79.4,
        "last_kg": 79.4,
        "change_kg": 0.0,
        "unit": "kg",
    }
    details = context.health["exercise_sessions"][0]["details"]
    assert details["exerciseEvents"][0]["exerciseEventType"] == "PAUSE"
    assert details["splitSummaries"][0]["splitType"] == "DISTANCE"
    assert context.health["data_completeness"]["categories"]["exercise"]["records"] == 1
    assert context.health["data_completeness"]["categories"]["sleep"]["records"] == 0
    assert context.health["data_completeness"]["status"] == "partial"


def test_context_builds_detailed_productivity_timeline_and_prior_load(db_session):
    zone = ZoneInfo("Europe/Kiev")
    db_session.add_all([
        SleepSession(
            record_date=date(2026, 8, 13),
            minutes_asleep=480,
            minutes_in_bed=510,
        ),
        DailyActivity(record_date=date(2026, 8, 12), steps=7000),
        ExerciseSession(
            record_date=date(2026, 8, 12),
            exercise_type="RUNNING",
            active_duration_min=60,
            calories_kcal=650,
        ),
        ProductivityCheckin(
            local_date=date(2026, 8, 13),
            period="morning",
            energy=6,
            sleep_quality=8,
            mood=7,
            original_text="morning",
        ),
        ProductivityCheckin(
            local_date=date(2026, 8, 13),
            period="evening",
            energy=5,
            focus=4,
            work_quality=5,
            persistence=6,
            deep_work_min=90,
            priority="finish report",
            original_text="evening",
        ),
        JournalEvent(
            category="caffeine",
            subtype="coffee",
            occurred_at=datetime(2026, 8, 13, 9, 30, tzinfo=zone),
            quantity=150,
            unit="mg",
            original_text="coffee",
        ),
        JournalEvent(
            category="meal",
            subtype="lunch",
            occurred_at=datetime(2026, 8, 13, 13, 0, tzinfo=zone),
            note="rice and chicken",
            original_text="lunch",
        ),
    ])
    db_session.flush()

    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 13), date(2026, 8, 13)),
    )

    productivity = context.productivity_context
    assert productivity["summary"] == {
        "checkin_days": 1,
        "morning_checkins": 1,
        "evening_checkins": 1,
        "average_energy": 5.5,
        "average_focus": 4.0,
        "average_work_quality": 5.0,
        "average_persistence": 6.0,
        "total_deep_work_min": 90,
    }
    day = productivity["days"][0]
    assert day["morning"]["sleep_quality"] == 8
    assert day["evening"]["priority"] == "finish report"
    assert day["changes"]["energy_evening_minus_morning"] == -1
    assert day["health_before_day"]["sleep_minutes_asleep"] == 480
    assert day["health_before_day"]["previous_day_steps"] == 7000
    assert day["health_before_day"]["previous_day_exercise_minutes"] == 60.0
    assert {item["type"] for item in day["timeline"]} >= {"checkin", "journal"}


def test_context_includes_only_confirmed_photo_meals_without_local_paths(db_session):
    analysis = {
        "summary": "Овсянка с бананом",
        "items": [{"name": "овсянка", "portion": "250 г", "confidence": "medium"}],
        "total_calories_min": 300,
        "total_calories_max": 420,
        "uncertainty": "Порция оценена приблизительно.",
        "confidence": "medium",
    }
    db_session.add_all([
        MealPhotoAnalysis(
            occurred_at=datetime(2026, 8, 12, 8, tzinfo=ZoneInfo("Europe/Kiev")),
            meal_type="breakfast",
            photo_path="data/food-photos/confirmed.jpg",
            analysis_json=json.dumps(analysis, ensure_ascii=False),
            confirmed_json=json.dumps(analysis, ensure_ascii=False),
            status="confirmed",
        ),
        MealPhotoAnalysis(
            occurred_at=datetime(2026, 8, 12, 13, tzinfo=ZoneInfo("Europe/Kiev")),
            meal_type="lunch",
            photo_path="data/food-photos/pending.jpg",
            analysis_json=json.dumps(analysis, ensure_ascii=False),
            status="pending",
        ),
    ])
    db_session.flush()

    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
    )

    assert len(context.health["nutrition"]) == 1
    assert context.health["nutrition"][0]["meal_type"] == "breakfast"
    assert context.health["nutrition"][0]["analysis"]["summary"] == "Овсянка с бананом"
    assert "photo_path" not in context.health["nutrition"][0]


def test_context_normalizes_photo_and_text_meals_into_structured_nutrition(db_session):
    analysis = {
        "summary": "Овсянка с бананом",
        "items": [
            {
                "name": "овсянка",
                "portion": "250 г",
                "calories_min": 250,
                "calories_max": 320,
                "confidence": "medium",
            }
        ],
        "total_calories_min": 300,
        "total_calories_max": 420,
        "total_protein_g_min": 10,
        "total_protein_g_max": 15,
        "uncertainty": "Порция оценена приблизительно.",
        "confidence": "medium",
    }
    text_event = JournalEvent(
        category="meal",
        subtype="dinner",
        occurred_at=datetime(2026, 8, 12, 19, tzinfo=ZoneInfo("Europe/Kiev")),
        note="курица с рисом",
        original_text="ужин",
    )
    db_session.add_all([
        MealPhotoAnalysis(
            occurred_at=datetime(2026, 8, 12, 8, tzinfo=ZoneInfo("Europe/Kiev")),
            meal_type="breakfast",
            photo_path="data/food-photos/confirmed.jpg",
            analysis_json=json.dumps(analysis, ensure_ascii=False),
            confirmed_json=json.dumps(analysis, ensure_ascii=False),
            status="confirmed",
        ),
        text_event,
    ])
    db_session.flush()
    db_session.add(MealTextAnalysis(
        journal_event_id=text_event.id,
        analysis_json=json.dumps({
            **analysis,
            "summary": "Курица с рисом",
            "total_calories_min": 260,
            "total_calories_max": 300,
        }, ensure_ascii=False),
        status="success",
        model="sonnet",
    ))
    db_session.flush()

    context = build_report_context(
        db_session,
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
    )

    nutrition = context.health["nutrition"]
    assert [item["source"] for item in nutrition] == ["photo", "text"]
    assert nutrition[0]["items"][0]["name"] == "овсянка"
    assert nutrition[0]["calories"]["min"] == 300
    assert nutrition[0]["macros"]["protein_g"]["max"] == 15
    assert nutrition[1]["summary"] == "курица с рисом"
    assert nutrition[1]["calories"] == {"min": 260, "max": 300}
    assert context.health["nutrition_summary"] == {
        "meals": 2,
        "photo_meals": 1,
        "text_meals": 1,
        "estimated_calories_min": 560.0,
        "estimated_calories_max": 720.0,
    }
