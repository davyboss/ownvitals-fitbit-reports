import json
from datetime import date

from fitbit_report.db.models import (
    BodyMeasurement,
    DailyActivity,
    ExerciseSession,
    HeartRateDaily,
    HrvMeasurement,
    SleepSession,
)
from fitbit_report.google_health.normalization import normalize_data_points


def test_normalize_steps_rollup_maps_count_sum_to_daily_activity():
    result = normalize_data_points(
        {"rollupDataPoints": [{"steps": {"countSum": "8123"}}]},
        "steps",
        date(2026, 8, 12),
    )

    assert isinstance(result[0], DailyActivity)
    assert result[0].steps == 8123


def test_normalize_total_calories_rollup_maps_kcal_sum_to_daily_activity():
    result = normalize_data_points(
        {"rollupDataPoints": [{"totalCalories": {"kcalSum": 2345.5}}]},
        "total-calories",
        date(2026, 8, 12),
    )

    assert isinstance(result[0], DailyActivity)
    assert result[0].calories_out == 2345.5


def test_normalize_active_zone_minutes_rollup_sums_heart_rate_zones():
    result = normalize_data_points(
        {
            "rollupDataPoints": [
                {
                    "activeZoneMinutes": {
                        "sumInCardioHeartZone": "20",
                        "sumInPeakHeartZone": "5",
                        "sumInFatBurnHeartZone": "30",
                    }
                }
            ]
        },
        "active-zone-minutes",
        date(2026, 8, 12),
    )

    assert isinstance(result[0], DailyActivity)
    assert result[0].active_zone_minutes == 55


def test_normalize_active_minutes_rollup_sums_activity_levels():
    result = normalize_data_points(
        {
            "rollupDataPoints": [
                {
                    "activeMinutes": {
                        "activeMinutesRollupByActivityLevel": [
                            {"activityLevel": "MODERATE", "activeMinutesSum": "25"},
                            {"activityLevel": "VIGOROUS", "activeMinutesSum": "10"},
                        ]
                    }
                }
            ]
        },
        "active-minutes",
        date(2026, 8, 12),
    )

    assert isinstance(result[0], DailyActivity)
    assert result[0].active_zone_minutes == 35


def test_normalize_sleep_preserves_interval_and_summary():
    result = normalize_data_points(
        {
            "dataPoints": [
                {
                    "sleep": {
                        "interval": {
                            "startTime": "2026-08-12T22:00:00Z",
                            "endTime": "2026-08-13T06:00:00Z",
                        },
                        "stages": [{"type": "DEEP", "startTime": "2026-08-13T01:00:00Z"}],
                        "summary": {"minutesAsleep": "420", "minutesInSleepPeriod": "480"},
                    }
                }
            ]
        },
        "sleep",
        date(2026, 8, 12),
    )

    assert isinstance(result[0], SleepSession)
    assert result[0].start_time.isoformat() == "2026-08-12T22:00:00+00:00"
    assert result[0].minutes_asleep == 420
    assert result[0].minutes_in_bed == 480
    assert '"type": "DEEP"' in result[0].stages_json


def test_normalize_exercise_session_preserves_workout_metrics():
    result = normalize_data_points(
        {
            "dataPoints": [
                {
                    "exercise": {
                        "interval": {
                            "startTime": "2026-08-12T18:00:00Z",
                            "endTime": "2026-08-12T18:35:00Z",
                        },
                        "exerciseType": "RUNNING",
                        "displayName": "Evening run",
                        "activeDuration": "1800s",
                        "metricsSummary": {
                            "caloriesKcal": 380.0,
                            "distanceMillimeters": 5000000,
                            "steps": "6200",
                            "averageHeartRateBeatsPerMinute": "148",
                            "activeZoneMinutes": "30",
                        },
                    }
                }
            ]
        },
        "exercise",
        date(2026, 8, 12),
    )

    assert isinstance(result[0], ExerciseSession)
    assert result[0].exercise_type == "RUNNING"
    assert result[0].display_name == "Evening run"
    assert result[0].active_duration_min == 30
    assert result[0].calories_kcal == 380
    assert result[0].distance_km == 5
    assert result[0].steps == 6200
    assert result[0].average_heart_rate_bpm == 148
    assert result[0].active_zone_minutes == 30


def test_normalize_exercise_session_preserves_full_workout_details():
    payload = {
        "dataPoints": [
            {
                "exercise": {
                    "interval": {
                        "startTime": "2026-08-12T18:00:00Z",
                        "endTime": "2026-08-12T18:35:00Z",
                    },
                    "exerciseType": "RUNNING",
                    "activeDuration": "1800s",
                    "metricsSummary": {
                        "averageSpeedMillimetersPerSecond": 2777.78,
                        "averagePaceSecondsPerMeter": 360,
                        "elevationGainMillimeters": 12500,
                    },
                    "exerciseMetadata": {"hasGps": True},
                    "exerciseEvents": [{"exerciseEventType": "PAUSE"}],
                    "splitSummaries": [{"splitType": "DISTANCE"}],
                }
            }
        ]
    }

    workout = normalize_data_points(payload, "exercise", date(2026, 8, 12))[0]

    details = json.loads(workout.details_json)
    assert details["metricsSummary"]["averagePaceSecondsPerMeter"] == 360
    assert details["exerciseMetadata"]["hasGps"] is True
    assert details["exerciseEvents"][0]["exerciseEventType"] == "PAUSE"
    assert details["splitSummaries"][0]["splitType"] == "DISTANCE"


def test_normalize_daily_resting_heart_rate():
    result = normalize_data_points(
        {"dataPoints": [{"dailyRestingHeartRate": {"beatsPerMinute": "55"}}]},
        "daily-resting-heart-rate",
        date(2026, 8, 12),
    )

    assert isinstance(result[0], HeartRateDaily)
    assert result[0].resting_heart_rate == 55


def test_normalize_daily_hrv_and_weight_units():
    hrv = normalize_data_points(
        {
            "dataPoints": [
                {
                    "dailyHeartRateVariability": {
                        "averageHeartRateVariabilityMilliseconds": 42.5
                    }
                }
            ]
        },
        "daily-heart-rate-variability",
        date(2026, 8, 12),
    )
    weight = normalize_data_points(
        {"dataPoints": [{"weight": {"weightGrams": 80000}}]},
        "weight",
        date(2026, 8, 12),
    )

    assert isinstance(hrv[0], HrvMeasurement)
    assert hrv[0].rmssd == 42.5
    assert isinstance(weight[0], BodyMeasurement)
    assert weight[0].value == 80
    assert weight[0].unit == "kg"


def test_normalize_missing_data_returns_empty_list():
    assert normalize_data_points({}, "heart-rate", date(2026, 8, 12)) == []
