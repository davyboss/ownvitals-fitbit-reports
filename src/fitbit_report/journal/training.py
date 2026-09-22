import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fitbit_report.db.models import TrainingLog
from fitbit_report.i18n import Locale
from fitbit_report.reports.llm_runner import ClaudeCliRunner


class TrainingExercise(BaseModel):
    name: str
    muscle_group: str | None = None
    sets: int | None = Field(default=None, ge=0)
    reps: list[int] = Field(default_factory=list)
    weight_kg: list[float] = Field(default_factory=list)
    duration_min: float | None = None
    rpe: float | None = None
    notes: str | None = None


class TrainingAnalysis(BaseModel):
    title: str
    training_type: str | None = None
    exercises: list[TrainingExercise] = Field(default_factory=list)
    total_duration_min: float | None = None
    total_volume_kg: float | None = None
    intensity: float | None = None
    summary: str
    confidence: str = "insufficient"
    uncertainty: str | None = None


def _as_text(value: object) -> str | None:
    """Convert a loose Claude value to the string expected by the journal schema."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        parts = [_as_text(item) for item in value]
        joined = "; ".join(part for part in parts if part)
        return joined or None
    text = str(value).strip()
    return text or None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _as_int(value: object) -> int | None:
    number = _as_float(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _normalize_training_payload(payload: object, locale: Locale = "ru") -> object:
    """Make a best-effort journal entry from a useful but schema-imperfect LLM reply.

    The model sometimes correctly extracts the workout but formats unknown data as
    ``null`` inside numeric lists or writes explanatory text in a numeric field.
    Such details must not make the entire workout disappear from the journal.
    """
    if not isinstance(payload, dict):
        return payload

    normalized: dict[str, Any] = dict(payload)
    normalized["title"] = _as_text(payload.get("title")) or (
        "Workout" if locale == "en" else "Тренировка"
    )
    normalized["training_type"] = _as_text(payload.get("training_type"))
    normalized["summary"] = (
        _as_text(payload.get("summary"))
        or (
            "Workout saved; some details could not be determined."
            if locale == "en"
            else "Тренировка сохранена; часть деталей не удалось определить."
        )
    )
    normalized["confidence"] = _as_text(payload.get("confidence")) or "insufficient"
    normalized["uncertainty"] = _as_text(payload.get("uncertainty"))

    for field in ("total_duration_min", "total_volume_kg", "intensity"):
        normalized[field] = _as_float(payload.get(field))

    exercises: list[dict[str, Any]] = []
    for index, exercise in enumerate(_as_list(payload.get("exercises")), start=1):
        if not isinstance(exercise, dict):
            continue

        reps = [
            number
            for value in _as_list(exercise.get("reps"))
            if (number := _as_int(value)) is not None and number >= 0
        ]
        weights = [
            number
            for value in _as_list(exercise.get("weight_kg"))
            if (number := _as_float(value)) is not None and number >= 0
        ]
        sets = _as_int(exercise.get("sets"))
        if sets is not None and sets < 0:
            sets = None
        if sets is None and (reps or weights):
            sets = max(len(reps), len(weights))

        duration_min = _as_float(exercise.get("duration_min"))
        rpe = _as_float(exercise.get("rpe"))
        exercises.append(
            {
                "name": _as_text(exercise.get("name"))
                or (
                    f"Unspecified exercise {index}"
                    if locale == "en"
                    else f"Неуточнённое упражнение {index}"
                ),
                "muscle_group": _as_text(exercise.get("muscle_group")),
                "sets": sets,
                "reps": reps,
                "weight_kg": weights,
                "duration_min": duration_min if duration_min is None or duration_min >= 0 else None,
                "rpe": rpe if rpe is None or rpe >= 0 else None,
                "notes": _as_text(exercise.get("notes")),
            }
        )
    normalized["exercises"] = exercises
    return normalized


def build_training_prompt(text: str | None = None, locale: Locale = "ru") -> str:
    if locale == "en":
        source = text or "The workout was provided as an image."
        return (
            "Parse the user's workout in English. The input may be free-form text, a screenshot, "
            "or a photo of gym notes. Extract only what is visible or explicitly written. Do not "
            "invent weights, repetitions, or exercises. Normalize variants of the same exercise "
            "to a short, clear name. Return JSON only with these fields: title, training_type, "
            "exercises, total_duration_min, total_volume_kg, intensity, summary, confidence, "
            "uncertainty. Each exercise must use name, muscle_group, sets, reps, weight_kg, "
            "duration_min, rpe, notes. reps and weight_kg must be numeric arrays by set when "
            "possible. Use null for an unknown scalar and [] for unknown reps or weight_kg. Never "
            "put text in numeric fields. uncertainty must be one string or null, never an array.\n\n"
            f"Original entry:\n{source}"
        )
    source = text or "Тренировка передана на фотографии."
    return (
        "Разбери тренировку пользователя на русском языке. Это может быть свободный текст, "
        "скриншот или фотография записи из зала. Извлеки только то, что видно или явно написано. "
        "Не выдумывай веса, повторы и упражнения. Сохрани разные варианты записи одного упражнения "
        "под нормальным коротким названием. Верни только JSON с полями title, training_type, exercises, "
        "total_duration_min, total_volume_kg, intensity, summary, confidence, uncertainty. "
        "В exercises используй name, muscle_group, sets, reps, weight_kg, duration_min, rpe, notes. "
        "reps и weight_kg — массивы чисел по подходам, если это возможно. Для неизвестного числа "
        "верни null, а для неизвестных reps или weight_kg — пустой массив []. Не пиши текст в "
        "числовых полях (total_duration_min, total_volume_kg, intensity, duration_min, rpe); "
        "используй число или null. uncertainty верни одной строкой или null, не массивом.\n\n"
        f"Исходная запись:\n{source}"
    )


class TrainingAnalysisService:
    def __init__(self, runner: ClaudeCliRunner, locale: Locale = "ru"):
        self.runner = runner
        self.locale = locale

    def analyze(
        self,
        session: Session,
        occurred_at: datetime,
        text: str | None = None,
        photo_path: Path | None = None,
    ) -> TrainingLog:
        record = TrainingLog(
            occurred_at=occurred_at,
            source_type="photo" if photo_path is not None else "text",
            original_text=text,
            photo_path=str(photo_path) if photo_path else None,
            status="running",
        )
        session.add(record)
        session.flush()
        try:
            payload = self.runner.generate_json(
                build_training_prompt(text, self.locale), image_path=photo_path
            )
            analysis = TrainingAnalysis.model_validate(
                _normalize_training_payload(payload, self.locale)
            )
            record.analysis_json = analysis.model_dump_json()
            record.status = "success"
            record.error_message = None
        except Exception as exc:
            record.status = "failed"
            record.error_message = str(exc)
        session.flush()
        return record


def load_training_analysis(record: TrainingLog) -> dict | None:
    if record.status != "success" or not record.analysis_json:
        return None
    try:
        payload = json.loads(record.analysis_json)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
