from __future__ import annotations

from dataclasses import dataclass

from fitbit_report.i18n import Locale


@dataclass(frozen=True)
class PersonalMetric:
    key: str
    label: str
    current: float | None
    baseline: float | None
    unit: str
    digits: int = 0
    lower_is_better: bool = False

    @property
    def comparable(self) -> bool:
        return self.current is not None and self.baseline not in (None, 0)

    @property
    def raw_delta_percent(self) -> float | None:
        if not self.comparable:
            return None
        return (self.current - self.baseline) / self.baseline * 100

    @property
    def quality_ratio(self) -> float | None:
        if not self.comparable:
            return None
        if self.lower_is_better:
            return self.baseline / self.current * 100
        return self.current / self.baseline * 100


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def personal_metrics(context: dict | None, locale: Locale = "ru") -> tuple[PersonalMetric, ...]:
    state = (context or {}).get("personal_state") or {}
    current = state.get("current") or {}
    baseline = state.get("baseline_28d") or {}
    copy = {
        "en": {
            "sleep": ("Sleep", "min"),
            "resting_hr": ("Resting HR", "bpm"),
            "hrv": ("HRV", "ms"),
            "energy": ("Energy", "/ 10"),
        },
        "ru": {
            "sleep": ("Сон", "мин"),
            "resting_hr": ("Пульс покоя", "уд/мин"),
            "hrv": ("ВСР", "мс"),
            "energy": ("Энергия", "/ 10"),
        },
    }[locale]
    return (
        PersonalMetric(
            key="sleep",
            label=copy["sleep"][0],
            current=_number(current.get("sleep_minutes")),
            baseline=_number(baseline.get("sleep_minutes")),
            unit=copy["sleep"][1],
        ),
        PersonalMetric(
            key="resting_hr",
            label=copy["resting_hr"][0],
            current=_number(current.get("resting_heart_rate")),
            baseline=_number(baseline.get("resting_heart_rate")),
            unit=copy["resting_hr"][1],
            digits=1,
            lower_is_better=True,
        ),
        PersonalMetric(
            key="hrv",
            label=copy["hrv"][0],
            current=_number(current.get("hrv_rmssd")),
            baseline=_number(baseline.get("hrv_rmssd")),
            unit=copy["hrv"][1],
            digits=1,
        ),
        PersonalMetric(
            key="energy",
            label=copy["energy"][0],
            current=_number(current.get("energy")),
            baseline=_number(baseline.get("energy")),
            unit=copy["energy"][1],
            digits=1,
        ),
    )


def format_metric_value(value: float | None, metric: PersonalMetric, locale: Locale) -> str:
    if value is None:
        return "not recorded" if locale == "en" else "нет записи"
    rendered = f"{value:.{metric.digits}f}"
    if metric.digits:
        rendered = rendered.rstrip("0").rstrip(".")
    if locale == "ru":
        rendered = rendered.replace(".", ",")
    return f"{rendered} {metric.unit}".strip()


def readiness(context: dict | None) -> tuple[float | None, str | None]:
    payload = ((context or {}).get("personal_state") or {}).get("readiness") or {}
    return _number(payload.get("score")), payload.get("status")
