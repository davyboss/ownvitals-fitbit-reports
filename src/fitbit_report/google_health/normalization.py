import json
from datetime import date, datetime
from typing import Any

from fitbit_report.db.models import (
    BodyMeasurement,
    DailyActivity,
    ExerciseSession,
    HeartRateDaily,
    HeartRateIntraday,
    HrvMeasurement,
    SleepSession,
)


_DATA_KEYS = {
    "steps": "steps",
    "distance": "distance",
    "total-calories": "totalCalories",
    "active-zone-minutes": "activeZoneMinutes",
    "active-minutes": "activeMinutes",
    "heart-rate": "heartRate",
    "sleep": "sleep",
    "daily-resting-heart-rate": "dailyRestingHeartRate",
    "daily-heart-rate-variability": "dailyHeartRateVariability",
    "heart-rate-variability": "heartRateVariability",
    "weight": "weight",
    "body-fat": "bodyFat",
}


def normalize_data_points(
    payload: dict[str, Any], data_type: str, day: date
) -> list[object]:
    items = payload.get("dataPoints") or payload.get("rollupDataPoints") or []
    if not isinstance(items, list):
        return []
    if data_type == "sleep":
        return _normalize_sleep_items(items, day)
    if data_type == "exercise":
        return _normalize_exercise_items(items, day)
    if data_type in {"steps", "distance", "total-calories", "active-zone-minutes", "active-minutes"}:
        activity = _normalize_activity(items, data_type, day)
        return [activity] if activity is not None else []
    if data_type == "heart-rate":
        return _normalize_heart_rate(items, day)
    if data_type == "daily-resting-heart-rate":
        return _normalize_resting_heart_rate(items, day)
    if data_type in {"daily-heart-rate-variability", "heart-rate-variability"}:
        return _normalize_hrv(items, data_type, day)
    if data_type in {"weight", "body-fat"}:
        return _normalize_body(items, data_type, day)
    return []


def normalize_sleep(payload: dict[str, Any], day: date) -> list[SleepSession]:
    return [item for item in normalize_data_points(payload, "sleep", day) if isinstance(item, SleepSession)]


def _normalize_sleep_items(items: list[Any], day: date) -> list[SleepSession]:
    result: list[SleepSession] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sleep = item.get("sleep")
        if not isinstance(sleep, dict):
            continue
        interval = sleep.get("interval") or {}
        start = _parse_datetime(interval.get("startTime"))
        end = _parse_datetime(interval.get("endTime"))
        summary = sleep.get("summary") or {}
        result.append(
            SleepSession(
                record_date=day,
                start_time=start,
                end_time=end,
                minutes_asleep=_int_or_none(summary.get("minutesAsleep")),
                minutes_in_bed=_int_or_none(summary.get("minutesInSleepPeriod")),
                efficiency=None,
                stages_json=json.dumps(sleep.get("stages"), ensure_ascii=False)
                if sleep.get("stages")
                else None,
            )
        )
    return result


def _normalize_exercise_items(items: list[Any], day: date) -> list[ExerciseSession]:
    result: list[ExerciseSession] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        exercise = item.get("exercise")
        if not isinstance(exercise, dict):
            continue
        interval = exercise.get("interval") or {}
        metrics = exercise.get("metricsSummary") or {}
        start = _parse_datetime(interval.get("startTime"))
        end = _parse_datetime(interval.get("endTime"))
        result.append(
            ExerciseSession(
                record_date=day,
                start_time=start,
                end_time=end,
                exercise_type=exercise.get("exerciseType"),
                display_name=exercise.get("displayName"),
                active_duration_min=_duration_minutes(exercise.get("activeDuration")),
                calories_kcal=_float_or_none(metrics.get("caloriesKcal")),
                distance_km=_distance_km(metrics.get("distanceMillimeters")),
                steps=_int_or_none(metrics.get("steps")),
                average_heart_rate_bpm=_float_or_none(
                    metrics.get("averageHeartRateBeatsPerMinute")
                ),
                active_zone_minutes=_int_or_none(metrics.get("activeZoneMinutes")),
                details_json=json.dumps(exercise, ensure_ascii=False, sort_keys=True),
            )
        )
    return result


def _normalize_activity(
    items: list[Any], data_type: str, day: date
) -> DailyActivity | None:
    steps = distance = calories = active_zone_minutes = None
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(_DATA_KEYS[data_type])
        if not isinstance(value, dict):
            continue
        if data_type == "steps":
            steps = _add_number(steps, value.get("countSum", value.get("count")))
        elif data_type == "distance":
            millimeters = value.get("millimetersSum", value.get("millimeters"))
            if millimeters is not None:
                distance = (distance or 0) + float(millimeters) / 1_000_000
        elif data_type == "total-calories":
            calories = _add_number(
                calories,
                value.get(
                    "kcalSum",
                    value.get("kilocaloriesSum", value.get("kilocalories")),
                )
            )
        elif data_type == "active-zone-minutes":
            zone_total = 0
            has_zone_value = False
            for field in (
                "sumInCardioHeartZone",
                "sumInPeakHeartZone",
                "sumInFatBurnHeartZone",
            ):
                number = _number(value.get(field))
                if number is not None:
                    zone_total += number
                    has_zone_value = True
            if has_zone_value:
                active_zone_minutes = _add_number(active_zone_minutes, zone_total)
            else:
                active_zone_minutes = _add_number(
                    active_zone_minutes,
                    value.get("activeZoneMinutesSum", value.get("activeZoneMinutes")),
                )
        elif data_type == "active-minutes":
            level_rollups = value.get("activeMinutesRollupByActivityLevel")
            if isinstance(level_rollups, list):
                minutes_total = 0
                has_minutes_value = False
                for level_rollup in level_rollups:
                    if not isinstance(level_rollup, dict):
                        continue
                    number = _number(level_rollup.get("activeMinutesSum"))
                    if number is not None:
                        minutes_total += number
                        has_minutes_value = True
                if has_minutes_value:
                    active_zone_minutes = _add_number(
                        active_zone_minutes, minutes_total
                    )
            else:
                active_zone_minutes = _add_number(
                    active_zone_minutes,
                    value.get("minutesSum", value.get("minutes")),
                )
    if all(value is None for value in (steps, distance, calories, active_zone_minutes)):
        return None
    return DailyActivity(
        record_date=day,
        steps=int(steps) if steps is not None else None,
        distance=distance,
        calories_out=calories,
        active_zone_minutes=(
            int(active_zone_minutes) if active_zone_minutes is not None else None
        ),
    )


def _normalize_heart_rate(items: list[Any], day: date) -> list[HeartRateIntraday]:
    result: list[HeartRateIntraday] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get("heartRate")
        if not isinstance(value, dict):
            continue
        sample_time = value.get("sampleTime") or {}
        measured_at = _parse_datetime(sample_time.get("physicalTime"))
        bpm = value.get("beatsPerMinute")
        if measured_at is not None and bpm is not None:
            result.append(
                HeartRateIntraday(
                    record_date=day,
                    measured_at=measured_at,
                    bpm=int(bpm),
                )
            )
    return result


def _normalize_resting_heart_rate(items: list[Any], day: date) -> list[HeartRateDaily]:
    result: list[HeartRateDaily] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get("dailyRestingHeartRate")
        if isinstance(value, dict) and value.get("beatsPerMinute") is not None:
            result.append(
                HeartRateDaily(
                    record_date=day,
                    resting_heart_rate=float(value["beatsPerMinute"]),
                    zones_json=None,
                )
            )
    return result


def _normalize_hrv(items: list[Any], data_type: str, day: date) -> list[HrvMeasurement]:
    result: list[HrvMeasurement] = []
    key = _DATA_KEYS[data_type]
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        if data_type == "daily-heart-rate-variability":
            rmssd = value.get("averageHeartRateVariabilityMilliseconds")
            measured_at = None
        else:
            rmssd = value.get("rootMeanSquareOfSuccessiveDifferencesMilliseconds")
            sample_time = value.get("sampleTime") or {}
            measured_at = _parse_datetime(sample_time.get("physicalTime"))
        if rmssd is not None:
            result.append(
                HrvMeasurement(
                    record_date=day,
                    measured_at=measured_at,
                    rmssd=float(rmssd),
                    coverage=None,
                )
            )
    return result


def _normalize_body(items: list[Any], data_type: str, day: date) -> list[BodyMeasurement]:
    result: list[BodyMeasurement] = []
    key = _DATA_KEYS[data_type]
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        if data_type == "weight":
            grams = value.get("weightGrams")
            if grams is not None:
                result.append(
                    BodyMeasurement(
                        record_date=day,
                        measurement_type="weight",
                        value=float(grams) / 1000,
                        unit="kg",
                    )
                )
        elif value.get("percentage") is not None:
            result.append(
                BodyMeasurement(
                    record_date=day,
                    measurement_type="body_fat",
                    value=float(value["percentage"]),
                    unit="percent",
                )
            )
    return result


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _add_number(current: float | int | None, value: Any) -> float | int | None:
    number = _number(value)
    if number is None:
        return current
    return (current or 0) + number


def _int_or_none(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _float_or_none(value: Any) -> float | None:
    number = _number(value)
    return float(number) if number is not None else None


def _duration_minutes(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / 60
    text = str(value).strip()
    if text.endswith("s"):
        return float(text[:-1]) / 60
    return _float_or_none(text)


def _distance_km(value: Any) -> float | None:
    number = _float_or_none(value)
    return number / 1_000_000 if number is not None else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
