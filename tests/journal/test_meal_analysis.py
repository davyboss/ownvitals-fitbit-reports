import json
from datetime import datetime

from fitbit_report.db.models import JournalEvent
from fitbit_report.journal.food import FoodAnalysis
from fitbit_report.journal.meal_analysis import MealTextAnalysisService


def _meal_event(db_session, description: str) -> JournalEvent:
    event = JournalEvent(
        category="meal",
        subtype="snack",
        occurred_at=datetime(2026, 8, 16, 12, 0),
        note=description,
        original_text=f"/log meal snack {description}",
    )
    db_session.add(event)
    db_session.flush()
    return event


class FakeFoodTextAnalyzer:
    def __init__(self, minimum=45, maximum=70):
        self.minimum = minimum
        self.maximum = maximum
        self.calls = 0

    def analyze(self, description: str, meal_type: str) -> FoodAnalysis:
        self.calls += 1
        return FoodAnalysis.model_validate({
            "summary": description,
            "items": [{
                "name": description,
                "portion": "1 порция",
                "confidence": "low",
            }],
            "total_calories_min": self.minimum,
            "total_calories_max": self.maximum,
            "uncertainty": "Размер порции оценён приблизительно.",
            "confidence": "low",
        })


def test_meal_analysis_service_persists_successful_text_estimate(db_session):
    event = _meal_event(db_session, "чайная ложка Nutella")
    service = MealTextAnalysisService(FakeFoodTextAnalyzer())

    stored = service.analyze_event(db_session, event)

    assert stored.status == "success"
    assert json.loads(stored.analysis_json)["total_calories_min"] == 45


def test_meal_analysis_service_does_not_reanalyze_successful_event(db_session):
    event = _meal_event(db_session, "Баунти 55 г")
    analyzer = FakeFoodTextAnalyzer()
    service = MealTextAnalysisService(analyzer)

    service.analyze_event(db_session, event)
    service.analyze_event(db_session, event)

    assert analyzer.calls == 1


def test_meal_analysis_service_keeps_event_when_claude_fails(db_session):
    event = _meal_event(db_session, "неизвестное блюдо")

    class FailingAnalyzer:
        def analyze(self, description, meal_type):
            raise RuntimeError("Claude unavailable")

    stored = MealTextAnalysisService(FailingAnalyzer()).analyze_event(db_session, event)

    assert stored.status == "failed"
    assert stored.error_message == "Claude unavailable"
    assert db_session.get(JournalEvent, event.id).note == "неизвестное блюдо"
