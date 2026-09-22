from datetime import datetime
import json
from zoneinfo import ZoneInfo

from fitbit_report.journal.training import TrainingAnalysisService, build_training_prompt


class FakeRunner:
    def generate_json(self, prompt, image_path=None):
        assert "упражнения" in prompt
        return {
            "title": "Грудь",
            "training_type": "силовая",
            "exercises": [{"name": "Жим лёжа", "sets": 3, "reps": [8, 8, 6], "weight_kg": [80, 80, 85]}],
            "total_duration_min": 60,
            "total_volume_kg": 1820,
            "intensity": 8,
            "summary": "Тяжёлая силовая тренировка.",
            "confidence": "medium",
            "uncertainty": None,
        }


def test_training_prompt_accepts_free_form_text():
    assert "свободный текст" in build_training_prompt("жим 80 кг 3x8")
    assert "пустой массив" in build_training_prompt("жим 80 кг 3x8")


def test_training_analysis_is_persisted(db_session):
    record = TrainingAnalysisService(FakeRunner()).analyze(
        db_session,
        datetime(2026, 8, 12, 18, 0, tzinfo=ZoneInfo("Europe/Kiev")),
        text="жим 80 кг 3x8",
    )

    assert record.status == "success"
    assert record.analysis_json is not None


class LooseFormatRunner:
    def generate_json(self, prompt, image_path=None):
        return {
            "title": "Руки и пресс",
            "exercises": [
                {
                    "name": "Сгибание рук на бицепс",
                    "sets": 2,
                    "reps": [15, 13],
                    "weight_kg": [10, None],
                },
                {
                    "name": "Разгибания на трицепс в блоке",
                    "sets": 2,
                    "reps": [13, 12],
                    "weight_kg": None,
                },
                {"name": "Пресс", "reps": [60], "weight_kg": None},
            ],
            "intensity": "не указана явно из-за отсутствия рабочего веса",
            "summary": "Руки и пресс.",
            "confidence": "medium",
            "uncertainty": ["Неизвестен вес одного подхода", "Неясен формат гиперсета"],
        }


def test_training_analysis_keeps_workout_when_llm_returns_loose_json(db_session):
    record = TrainingAnalysisService(LooseFormatRunner()).analyze(
        db_session,
        datetime(2026, 8, 24, 21, 17, tzinfo=ZoneInfo("Europe/Moscow")),
        text="сгибание рук 15 раз 10 кг; пресс: гиперсет из 60 повторений",
    )

    assert record.status == "success"
    analysis = json.loads(record.analysis_json)
    assert analysis["exercises"][0]["weight_kg"] == [10.0]
    assert analysis["exercises"][1]["weight_kg"] == []
    assert analysis["intensity"] is None
    assert analysis["uncertainty"] == "Неизвестен вес одного подхода; Неясен формат гиперсета"


def test_english_training_prompt_requests_english_output():
    prompt = build_training_prompt("bench press 80 kg 3x8", "en")

    assert "Parse the user's workout in English" in prompt
    assert "bench press 80 kg 3x8" in prompt
    assert "пустой массив" not in prompt
