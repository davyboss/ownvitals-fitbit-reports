from datetime import date

from fitbit_report.reports.renderer import (
    render_markdown,
    render_telegram,
    render_telegram_rich,
)
from fitbit_report.reports.prompts import build_prompt
from fitbit_report.reports.context import ReportContext
from fitbit_report.types import DateRange


def test_daily_report_has_frontmatter_and_claim_sections():
    markdown = render_markdown(
        {"type": "daily", "period_start": date(2026, 8, 12), "period_end": date(2026, 8, 12), "model": "sonnet", "context_hash": "abc"},
        {"summary": "ok", "claims": [{"statement": "sleep was short", "kind": "fact", "evidence_count": 1, "confidence": "low", "alternatives": [], "source_ids": []}], "recommendations": [], "experiments": [], "confidence": "low"},
        timezone_name="Europe/Kiev",
    )
    assert markdown.startswith("---\n")
    assert "+03:00" in next(line for line in markdown.splitlines() if line.startswith("generated_at:"))
    assert "## Что попробовать" in markdown
    assert "## Личный эксперимент" in markdown
    assert "evidence_count" not in markdown


def test_telegram_renderer_is_russian_and_does_not_include_obsidian_frontmatter():
    text = render_telegram(
        {"type": "daily", "period_start": date(2026, 8, 12), "period_end": date(2026, 8, 12)},
        {
            "summary": "День прошёл стабильно.",
            "claims": [{
                "statement": "Завтрак был записан утром.",
                "kind": "fact",
                "evidence_count": 1,
                "confidence": "high",
                "alternatives": [],
                "source_ids": [],
            }],
            "recommendations": ["Продолжать записывать питание."],
            "experiments": ["Сравнивать завтрак с энергией."],
            "confidence": "medium",
        },
    )

    assert "<b>Дневной отчёт</b>" in text
    assert "<b>Главный вывод</b>" in text
    assert "Завтрак был записан утром." in text
    assert "📊" not in text
    assert "🧭" not in text
    assert "---" not in text
    assert "period_start" not in text


def test_telegram_renderer_adds_personal_dashboard_when_context_is_available():
    text = render_telegram(
        {"type": "daily", "period_start": date(2026, 8, 12), "period_end": date(2026, 8, 12)},
        {"summary": "ok", "claims": [], "recommendations": [], "experiments": [], "confidence": "medium"},
        {
            "personal_state": {
                "readiness": {"score": 57, "status": "обычное", "components_used": 4},
                "current": {"sleep_minutes": 480, "steps": 5000, "energy": 6},
                "baseline_28d": {"sleep_minutes": 450, "energy": 5},
            }
        },
    )

    assert "<b>Личные показатели</b>" in text
    assert "57 / 100" in text
    assert "<b>Сон</b>: 480 мин" in text
    assert "личная норма 450 мин" in text


def test_renderer_hides_internal_context_names_from_model_output():
    text = render_telegram(
        {"type": "daily", "period_start": date(2026, 8, 12), "period_end": date(2026, 8, 12)},
        {
            "summary": "В personal_state baseline_28d есть данные.",
            "claims": [],
            "recommendations": [],
            "experiments": [],
            "confidence": "medium",
        },
    )

    assert "personal_state" not in text
    assert "baseline_28d" not in text
    assert "рассчитанная персональная оценка" in text
    assert "личная норма за 28 дней" in text


def test_report_prompt_requires_russian_and_repeated_evidence_for_associations():
    prompt = build_prompt(ReportContext(
        report_type="daily",
        period=DateRange(date(2026, 8, 12), date(2026, 8, 12)),
        recent_days=[],
        baselines={},
        events=[],
        memories=[],
        corrections=[],
    ))

    assert "Весь текст полей" in prompt
    assert "Никогда не проси пользователя повторно сообщить" in prompt
    assert "Не показывай технические названия полей" in prompt
    assert "health.sleep_timing_history" in prompt
    assert "Временная близость двух событий сама по себе не является ассоциацией" in prompt
    assert "Не превращай каждую метрику" in prompt
    assert "Для дневного отчёта" in prompt


def test_english_report_prompt_and_renderers_are_user_facing_in_english():
    context = ReportContext(
        report_type="daily",
        period=DateRange(date(2026, 8, 12), date(2026, 8, 12)),
        recent_days=[],
        baselines={},
        events=[],
        memories=[],
        corrections=[],
    )
    prompt = build_prompt(context, "en")
    draft = {
        "summary": "Recovery appears stable.",
        "claims": [{
            "statement": "Sleep was close to the personal baseline.",
            "kind": "fact",
            "evidence_count": 3,
            "confidence": "medium",
            "alternatives": [],
            "source_ids": [],
        }],
        "recommendations": ["Keep today's training moderate."],
        "experiments": ["Compare bedtime with next-day energy."],
        "confidence": "medium",
    }
    report = {
        "type": "daily",
        "period_start": date(2026, 8, 12),
        "period_end": date(2026, 8, 12),
    }

    markdown = render_markdown(report, draft, locale="en")
    telegram = render_telegram(report, draft, locale="en")

    assert "Write every textual field" in prompt
    assert "# Daily report" in markdown
    assert "## What to try" in markdown
    assert "<b>Daily report</b>" in telegram
    assert "<b>Main takeaway</b>" in telegram
    assert "📊" not in telegram
    assert "🧭" not in telegram
    assert "Уверенность" not in telegram


def test_rich_report_preserves_full_content_and_embeds_native_components():
    report = {
        "type": "daily",
        "period_start": date(2026, 8, 12),
        "period_end": date(2026, 8, 12),
    }
    draft = {
        "summary": "Восстановление выше личной нормы.",
        "claims": [{
            "statement": "Сон был длиннее обычного.",
            "kind": "fact",
            "evidence_count": 3,
            "confidence": "high",
            "alternatives": [],
            "source_ids": [],
        }],
        "recommendations": ["Сохранить время отхода ко сну."],
        "experiments": ["Сравнить энергию в течение трёх дней."],
        "confidence": "high",
    }
    context = {
        "personal_state": {
            "readiness": {"score": 76, "status": "хорошее"},
            "current": {"sleep_minutes": 652, "resting_heart_rate": 60},
            "baseline_28d": {"sleep_minutes": 558.4, "resting_heart_rate": 64.8},
        }
    }

    rich = render_telegram_rich(report, draft, context, "ru", include_chart=True)

    assert "<table bordered striped compact>" in rich
    assert 'src="tg://photo?id=report_chart"' in rich
    assert "Восстановление выше личной нормы." in rich
    assert "Сон был длиннее обычного." in rich
    assert "Сохранить время отхода ко сну." in rich
    assert "Сравнить энергию в течение трёх дней." in rich
    assert "Вклад факторов в сегодняшнюю оценку состояния" in rich
    assert "📊" not in rich
