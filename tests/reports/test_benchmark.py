from datetime import date

import pytest

from fitbit_report.reports.benchmark import (
    calculate_api_cost,
    normalize_model_name,
    pricing_for_model,
    score_draft,
)
from fitbit_report.reports.context import ReportContext
from fitbit_report.reports.schemas import ReportClaim, ReportDraft
from fitbit_report.types import DateRange


def test_benchmark_uses_exact_model_ids_and_current_prices():
    assert normalize_model_name("haiku-4.5") == "claude-haiku-4-5-20251001"
    assert pricing_for_model("claude-opus-5") == {"input": 5.0, "output": 25.0}
    assert pricing_for_model("claude-sonnet-5") == {"input": 2.0, "output": 10.0}
    assert pricing_for_model("claude-haiku-4-5-20251001") == {"input": 1.0, "output": 5.0}


def test_benchmark_api_cost_includes_cache_rates():
    cost = calculate_api_cost(
        {
            "input_tokens": 1_000_000,
            "output_tokens": 100_000,
            "cache_read_input_tokens": 100_000,
            "cache_creation_input_tokens": 100_000,
        },
        {"input": 2.0, "output": 10.0},
    )

    assert cost == pytest.approx(3.27)


def test_score_draft_rewards_sources_personal_coverage_and_actions():
    context = ReportContext(
        report_type="daily",
        period=DateRange(date(2026, 8, 19), date(2026, 8, 19)),
        recent_days=[],
        baselines={"sleep": {"status": "ok"}},
        events=[],
        memories=[],
        corrections=[],
        productivity_context={"focus": 7},
        health={
            "sleep": [{"duration_minutes": 480}],
            "nutrition": [{"source": "fatsecret", "calories": 2200}],
            "gym_training": [{"exercise": "squat", "weight_kg": 100}],
        },
        personal_factors=[{"category": "masturbation", "count": 2}],
        personal_state={"readiness": 62},
    )
    draft = ReportDraft(
        summary="Персональное состояние и готовность к тренировке связаны со сном и восстановлением.",
        claims=[
            ReportClaim(
                statement="Сон ниже личной нормы, поэтому readiness ниже обычного.",
                kind="association",
                evidence_count=4,
                confidence="medium",
                source_ids=["health.sleep:2026-08-19"],
            )
        ],
        recommendations=["Сегодня оставить интенсивность тренировки умеренной и оценить энергию после разминки."],
        experiments=["В течение семи дней сравнивать время ужина FatSecret со сном и утренним фокусом."],
        confidence="medium",
    )

    score = score_draft(draft, context)

    assert score["score"] > 70
    assert "nutrition" in score["available_topics"]
    assert "training" in score["detected_topics"]
