from datetime import date

from PIL import Image

from fitbit_report.reports.charts import generate_report_charts
from fitbit_report.types import DateRange


def _daily_context():
    return {
        "personal_state": {
            "readiness": {
                "score": 76,
                "status": "хорошее",
                "base_score": 50,
                "contributions": [
                    {"key": "sleep", "label": "Сон", "points": 8},
                    {
                        "key": "resting_heart_rate",
                        "label": "Пульс покоя",
                        "points": 6,
                    },
                    {"key": "hrv", "label": "ВСР", "points": 7},
                    {"key": "energy", "label": "Энергия", "points": 5},
                ],
            },
            "current": {
                "sleep_minutes": 652,
                "resting_heart_rate": 60,
                "hrv_rmssd": 137.6,
                "energy": 7,
            },
            "baseline_28d": {
                "sleep_minutes": 558.4,
                "resting_heart_rate": 64.8,
                "hrv_rmssd": 106.3,
                "energy": 4.3,
            },
        }
    }


def test_daily_chart_uses_fixed_high_resolution_canvas(tmp_path):
    day = date(2026, 9, 20)

    paths = generate_report_charts(
        _daily_context(), tmp_path, "daily", DateRange(day, day), "ru"
    )

    assert len(paths) == 1
    with Image.open(paths[0]) as image:
        assert image.size == (1800, 1080)


def test_daily_chart_is_generated_with_one_readiness_contribution(tmp_path):
    day = date(2026, 9, 20)
    context = {
        "personal_state": {
            "readiness": {
                "score": 58,
                "base_score": 50,
                "contributions": [
                    {"key": "sleep", "label": "Sleep", "points": 8},
                ],
            },
        }
    }

    paths = generate_report_charts(
        context, tmp_path, "daily", DateRange(day, day), "en"
    )

    assert len(paths) == 1


def test_daily_chart_is_skipped_without_readiness_contributions(tmp_path):
    day = date(2026, 9, 20)

    paths = generate_report_charts(
        {"personal_state": {"readiness": {"score": 50}}},
        tmp_path,
        "daily",
        DateRange(day, day),
        "en",
    )

    assert paths == []
