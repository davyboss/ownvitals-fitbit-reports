from datetime import date

from fitbit_report.i18n import Locale


def _metric_average(baselines: dict, metric: str, window: str = "28d") -> float | None:
    value = (
        baselines.get("windows", {})
        .get(window, {})
        .get("metrics", {})
        .get(metric, {})
        .get("average")
    )
    return float(value) if value is not None else None


def _latest(rows: list[dict], field: str, day: date | None = None):
    candidates = [row for row in rows if row.get(field) is not None]
    if day is not None:
        candidates = [row for row in candidates if str(row.get("record_date"))[:10] <= day.isoformat()]
    return candidates[-1] if candidates else None


def _mean(values: list[float | int | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return round(sum(usable) / len(usable), 1) if usable else None


def _deviation(value: float | None, baseline: float | None) -> dict:
    if value is None or baseline is None:
        return {"value": value, "baseline": baseline, "difference": None, "percent": None}
    difference = value - baseline
    return {
        "value": round(value, 1),
        "baseline": round(baseline, 1),
        "difference": round(difference, 1),
        "percent": round((difference / baseline) * 100, 1) if baseline else None,
    }


def _extract_current_values(health: dict, productivity_context: dict, day: date) -> dict:
    def latest_day_rows(rows: list[dict], key: str = "record_date") -> list[dict]:
        available = [row for row in rows if str(row.get(key))[:10] <= day.isoformat()]
        if not available:
            return []
        latest = max(str(row.get(key))[:10] for row in available)
        return [row for row in available if str(row.get(key))[:10] == latest]

    sleep = latest_day_rows(health.get("sleep", []))
    activity = latest_day_rows(health.get("activity", []))
    heart_rate = latest_day_rows(health.get("heart_rate", []))
    hrv = latest_day_rows(health.get("hrv", []))
    training = latest_day_rows(health.get("gym_training", []), "occurred_at")
    days = latest_day_rows(productivity_context.get("days", []), "date")
    current_day = days[-1] if days else {}
    checkin = current_day.get("evening") or current_day.get("morning") or {}
    sleep_starts = [row.get("start_time") for row in sleep if row.get("start_time") is not None]
    sleep_ends = [row.get("end_time") for row in sleep if row.get("end_time") is not None]
    return {
        "sleep_minutes": sum(row.get("minutes_asleep") or 0 for row in sleep) or None,
        "sleep_start_time": min(sleep_starts) if sleep_starts else None,
        "sleep_end_time": max(sleep_ends) if sleep_ends else None,
        "steps": activity[-1].get("steps") if activity else None,
        "resting_heart_rate": heart_rate[-1].get("resting_heart_rate") if heart_rate else None,
        "hrv_rmssd": _mean([row.get("rmssd") for row in hrv]),
        "energy": checkin.get("energy"),
        "focus": checkin.get("focus"),
        "training_count": len(training),
        "training_volume_kg": _mean([
            (row.get("analysis") or {}).get("total_volume_kg") for row in training
        ]),
    }


def build_personal_state(
    *,
    as_of: date,
    baselines: dict,
    health: dict,
    productivity_context: dict,
    personal_factors: list[dict],
    locale: Locale = "ru",
) -> dict:
    current = _extract_current_values(health, productivity_context, as_of)
    baseline = {
        "sleep_minutes": _metric_average(baselines, "sleep.minutes_asleep"),
        "steps": _metric_average(baselines, "activity.steps"),
        "resting_heart_rate": _metric_average(baselines, "heart_rate.resting_heart_rate"),
        "hrv_rmssd": _metric_average(baselines, "hrv.rmssd"),
        "energy": _metric_average(baselines, "productivity.energy"),
        "focus": _metric_average(baselines, "productivity.focus"),
    }
    deviations = {
        key: _deviation(current.get(key), value)
        for key, value in baseline.items()
    }

    score = 50.0
    component_count = 0
    reasons = []
    contribution_labels = {
        "en": {
            "sleep": "Sleep",
            "resting_heart_rate": "Resting HR",
            "hrv": "HRV",
            "energy": "Energy",
            "focus": "Focus",
        },
        "ru": {
            "sleep": "Сон",
            "resting_heart_rate": "Пульс покоя",
            "hrv": "ВСР",
            "energy": "Энергия",
            "focus": "Фокус",
        },
    }[locale]
    contributions = []

    def add_contribution(
        key: str,
        points: float,
        current_value: float | None,
        baseline_value: float | None,
    ) -> None:
        nonlocal score, component_count
        component_count += 1
        score += points
        contributions.append({
            "key": key,
            "label": contribution_labels[key],
            "points": round(points, 1),
            "current": current_value,
            "baseline": baseline_value,
        })

    sleep_delta = deviations["sleep_minutes"]["difference"]
    if sleep_delta is not None:
        points = 0
        if sleep_delta <= -60:
            points = -15
            reasons.append(
                "sleep is notably shorter than the personal baseline"
                if locale == "en"
                else "сон заметно короче личной нормы"
            )
        elif sleep_delta >= 30:
            points = 8
        add_contribution(
            "sleep",
            points,
            current["sleep_minutes"],
            baseline["sleep_minutes"],
        )
    heart_delta = deviations["resting_heart_rate"]["difference"]
    if heart_delta is not None:
        points = 0
        if heart_delta >= 5:
            points = -12
            reasons.append(
                "resting heart rate is above the personal baseline"
                if locale == "en"
                else "пульс покоя выше личной нормы"
            )
        elif heart_delta <= -3:
            points = 6
        add_contribution(
            "resting_heart_rate",
            points,
            current["resting_heart_rate"],
            baseline["resting_heart_rate"],
        )
    hrv_delta = deviations["hrv_rmssd"]["percent"]
    if hrv_delta is not None:
        points = 0
        if hrv_delta <= -10:
            points = -12
            reasons.append(
                "HRV is below the personal baseline"
                if locale == "en"
                else "ВСР ниже личной нормы"
            )
        elif hrv_delta >= 10:
            points = 7
        add_contribution(
            "hrv",
            points,
            current["hrv_rmssd"],
            baseline["hrv_rmssd"],
        )
    for key in ("energy", "focus"):
        delta = deviations[key]["difference"]
        if delta is not None:
            add_contribution(
                key,
                max(-8, min(8, delta * 2)),
                current[key],
                baseline[key],
            )

    score = round(max(0, min(100, score)))
    if score >= 68:
        status = "good" if locale == "en" else "хорошее"
    elif score <= 42:
        status = "reduced" if locale == "en" else "сниженное"
    else:
        status = "typical" if locale == "en" else "обычное"
    confidence = "insufficient" if component_count < 2 else "exploratory" if component_count < 4 else "usable"

    factor_signals = []
    for factor in personal_factors:
        for target, comparison in factor.get("next_day_comparisons", {}).items():
            difference = comparison.get("difference")
            if difference is not None and comparison.get("confidence") != "insufficient":
                factor_signals.append({
                    "factor": factor["factor"],
                    "target": target,
                    "difference_after_vs_control": difference,
                    "after_samples": comparison["after_samples"],
                    "control_samples": comparison["control_samples"],
                    "confidence": comparison["confidence"],
                })

    recommendations = []
    if score <= 42:
        recommendations.append(
            "Choose recovery or lighter activity today instead of chasing a personal best."
            if locale == "en"
            else "Сделать сегодня восстановительную или облегчённую нагрузку и не гнаться за рекордами."
        )
    elif score >= 68:
        recommendations.append(
            "The current data suggests readiness for the planned load if your subjective "
            "wellbeing agrees."
            if locale == "en"
            else "По текущим данным организм выглядит готовым к плановой нагрузке, если субъективное самочувствие это подтверждает."
        )
    else:
        recommendations.append(
            "Use your subjective wellbeing as a guide and avoid increasing training intensity."
            if locale == "en"
            else "Ориентироваться на самочувствие и оставить интенсивность тренировки без увеличения."
        )
    if not current["sleep_minutes"]:
        recommendations.append(
            "Today's sleep data is insufficient for a confident readiness conclusion."
            if locale == "en"
            else "Данных о сегодняшнем сне недостаточно — не делать уверенный вывод о готовности."
        )

    return {
        "as_of": as_of,
        "readiness": {
            "score": score,
            "status": status,
            "confidence": confidence,
            "components_used": component_count,
            "base_score": 50,
            "contributions": contributions,
            "reasons": reasons,
        },
        "current": current,
        "baseline_28d": baseline,
        "deviations": deviations,
        "factor_signals": factor_signals,
        "recommendations": recommendations,
        "disclaimer": (
            "This is an exploratory personal estimate, not a medical diagnosis."
            if locale == "en"
            else "Это персональная ориентировочная оценка, а не медицинская диагностика."
        ),
    }
