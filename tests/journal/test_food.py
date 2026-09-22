import json
from datetime import datetime
from pathlib import Path

from fitbit_report.journal.food import (
    FoodAnalysis,
    FoodPhotoAnalyzer,
    FoodTextAnalyzer,
    format_food_analysis,
)


def test_food_analysis_accepts_ranges_and_formats_a_russian_confirmation_message():
    analysis = FoodAnalysis.model_validate(
        {
            "summary": "Овсянка с бананом и кофе",
            "items": [
                {
                    "name": "овсянка",
                    "portion": "примерно 250 г",
                    "calories_min": 250,
                    "calories_max": 320,
                    "protein_g_min": 8,
                    "protein_g_max": 12,
                    "confidence": "medium",
                }
            ],
            "total_calories_min": 300,
            "total_calories_max": 420,
            "total_carbohydrates_g_min": 40,
            "total_carbohydrates_g_max": 55,
            "total_fat_g_min": 10,
            "total_fat_g_max": 18,
            "uncertainty": "Размер порции и количество молока оценены приблизительно.",
            "confidence": "medium",
        }
    )

    text = format_food_analysis(analysis)

    assert "Овсянка с бананом и кофе" in text
    assert "300–420 ккал" in text
    assert "овсянка — примерно 250 г" in text
    assert "Уверенность: средняя" in text
    assert analysis.total_carbohydrates_g_max == 55
    assert analysis.total_fat_g_min == 10
    assert "Углеводы: 40–55 г" in text
    assert "Жиры: 10–18 г" in text


def test_food_photo_analysis_model_stores_pending_estimate(db_session):
    from fitbit_report.db.models import MealPhotoAnalysis

    record = MealPhotoAnalysis(
        occurred_at=datetime(2026, 8, 14, 13, 30),
        meal_type="lunch",
        photo_path=Path("data/food-photos/meal.jpg").as_posix(),
        analysis_json=json.dumps({"summary": "обед"}, ensure_ascii=False),
    )
    db_session.add(record)
    db_session.commit()

    stored = db_session.query(MealPhotoAnalysis).one()
    assert stored.status == "pending"
    assert stored.confirmed_json is None
    assert stored.photo_path.endswith("meal.jpg")


def test_text_food_confirmation_persists_report_ready_analysis(db_session):
    from types import SimpleNamespace

    from fitbit_report.db.models import JournalEvent, MealTextAnalysis
    from fitbit_report.integrations.telegram import _persist_text_food_analysis

    state = {
        "meal_type": "lunch",
        "occurred_at": "2026-09-22T13:15:00+03:00",
        "description": "Рис с курицей",
        "exact_details": "620 ккал; Б 35; Ж 20; У 70",
        "analysis": {
            "summary": "Рис с курицей",
            "items": [],
            "total_calories_min": 620,
            "total_calories_max": 620,
            "uncertainty": "Неизвестен состав соуса.",
            "confidence": "medium",
        },
    }

    event_id = _persist_text_food_analysis(
        state,
        SimpleNamespace(engine=db_session.bind),
    )
    db_session.expire_all()

    event = db_session.get(JournalEvent, event_id)
    analysis = db_session.query(MealTextAnalysis).one()
    assert event.note == "Рис с курицей. 620 ккал; Б 35; Ж 20; У 70"
    assert analysis.journal_event_id == event_id
    assert analysis.status == "success"
    assert json.loads(analysis.analysis_json)["total_calories_min"] == 620


def test_food_photo_analyzer_validates_claude_estimate(tmp_path):
    from fitbit_report.journal.food import FoodPhotoAnalyzer

    class FakeRunner:
        def __init__(self):
            self.calls = []

        def generate_json(self, prompt, image_path, max_turns):
            self.calls.append((prompt, image_path, max_turns))
            return {
                "summary": "Суп и хлеб",
                "items": [
                    {
                        "name": "суп",
                        "portion": "примерно 300 г",
                        "calories_min": 180,
                        "calories_max": 260,
                        "confidence": "low",
                    }
                ],
                "total_calories_min": 220,
                "total_calories_max": 340,
                "uncertainty": "Состав супа не виден полностью.",
                "confidence": "low",
            }

    runner = FakeRunner()
    image_path = tmp_path / "meal.jpg"
    analysis = FoodPhotoAnalyzer(runner).analyze(image_path, "dinner", "Было съедено всё")

    assert analysis.summary == "Суп и хлеб"
    assert runner.calls[0][1] == image_path
    assert "Было съедено всё" in runner.calls[0][0]
    assert runner.calls[0][2] == 2


def test_food_photo_analyzer_combines_caption_and_exact_details(tmp_path):
    class FakeRunner:
        def __init__(self):
            self.prompt = ""

        def generate_json(self, prompt, image_path, max_turns):
            self.prompt = prompt
            return {
                "summary": "Рис с курицей",
                "items": [],
                "total_calories_min": 620,
                "total_calories_max": 620,
                "uncertainty": "Неизвестен состав соуса.",
                "confidence": "medium",
            }

    runner = FakeRunner()
    FoodPhotoAnalyzer(runner).analyze(
        tmp_path / "meal.jpg",
        "lunch",
        description="Рис, курица и овощи",
        exact_details="620 ккал; Б 35; Ж 20; У 70",
    )

    assert "Рис, курица и овощи" in runner.prompt
    assert "620 ккал; Б 35; Ж 20; У 70" in runner.prompt
    assert "Считай эти значения фактами" in runner.prompt


def test_food_text_analyzer_returns_calorie_range():
    class FakeRunner:
        def generate_json(self, prompt, image_path, max_turns):
            assert image_path is None
            assert "Баунти 55 г" in prompt
            return {
                "summary": "Баунти",
                "items": [{
                    "name": "Баунти",
                    "portion": "55 г",
                    "calories_min": 260,
                    "calories_max": 300,
                    "confidence": "high",
                }],
                "total_calories_min": 260,
                "total_calories_max": 300,
                "uncertainty": "Марка и состав оценены по описанию.",
                "confidence": "high",
            }

    analysis = FoodTextAnalyzer(FakeRunner()).analyze("Баунти 55 г", "snack")

    assert analysis.total_calories_min == 260
    assert analysis.total_calories_max == 300


def test_food_text_analyzer_preserves_exact_user_details():
    class FakeRunner:
        def __init__(self):
            self.prompt = ""

        def generate_json(self, prompt, image_path, max_turns):
            self.prompt = prompt
            return {
                "summary": "Овсянка",
                "items": [],
                "total_calories_min": 420,
                "total_calories_max": 420,
                "uncertainty": "Нет данных о составе.",
                "confidence": "high",
            }

    runner = FakeRunner()
    FoodTextAnalyzer(runner).analyze(
        "Овсянка с молоком",
        "breakfast",
        exact_details="420 ккал",
    )

    assert "420 ккал" in runner.prompt
    assert "Считай их фактами" in runner.prompt


def test_exact_nutrition_overrides_model_ranges():
    class FakeRunner:
        def generate_json(self, prompt, image_path, max_turns):
            return {
                "summary": "Обед",
                "items": [],
                "total_calories_min": 500,
                "total_calories_max": 800,
                "total_protein_g_min": 20,
                "total_protein_g_max": 50,
                "uncertainty": "Порции оценены приблизительно.",
                "confidence": "medium",
            }

    analysis = FoodTextAnalyzer(FakeRunner()).analyze(
        "Рис с курицей",
        "lunch",
        exact_details="620 ккал; Б 35; Ж 20; У 70",
    )

    assert analysis.total_calories_min == analysis.total_calories_max == 620
    assert analysis.total_protein_g_min == analysis.total_protein_g_max == 35
    assert analysis.total_fat_g_min == analysis.total_fat_g_max == 20
    assert analysis.total_carbohydrates_g_min == 70
    assert analysis.total_carbohydrates_g_max == 70


def test_english_food_photo_analyzer_requests_english_text(tmp_path):
    class FakeRunner:
        def __init__(self):
            self.prompt = ""

        def generate_json(self, prompt, image_path, max_turns):
            self.prompt = prompt
            return {
                "summary": "Soup and bread",
                "items": [],
                "uncertainty": "The portion size is unclear.",
                "confidence": "low",
            }

    runner = FakeRunner()
    FoodPhotoAnalyzer(runner, locale="en").analyze(
        tmp_path / "meal.jpg",
        "dinner",
        "The whole portion was eaten",
    )

    assert "Write every textual field in English" in runner.prompt
    assert "The whole portion was eaten" in runner.prompt


def test_english_food_text_analyzer_requests_english_text():
    class FakeRunner:
        def __init__(self):
            self.prompt = ""

        def generate_json(self, prompt, image_path, max_turns):
            self.prompt = prompt
            return {
                "summary": "Oatmeal",
                "items": [],
                "uncertainty": "The amount of milk is unclear.",
                "confidence": "medium",
            }

    runner = FakeRunner()
    FoodTextAnalyzer(runner, locale="en").analyze("Oatmeal with milk", "breakfast")

    assert "Write every textual field in English" in runner.prompt
    assert "Oatmeal with milk" in runner.prompt


def test_food_analysis_formats_english_labels():
    analysis = FoodAnalysis.model_validate(
        {
            "summary": "Oatmeal with banana",
            "items": [
                {
                    "name": "oatmeal",
                    "portion": "about 250 g",
                    "calories_min": 250,
                    "calories_max": 320,
                    "confidence": "medium",
                }
            ],
            "total_calories_min": 300,
            "total_calories_max": 420,
            "total_protein_g_min": 8,
            "total_protein_g_max": 12,
            "uncertainty": "The amount of milk is approximate.",
            "confidence": "medium",
        }
    )

    text = format_food_analysis(analysis, "en")

    assert "Estimated composition:" in text
    assert "300–420 kcal" in text
    assert "Protein: 8–12 g" in text
    assert "Confidence: medium" in text
