from datetime import date
from types import SimpleNamespace

from fitbit_report.reports.schemas import ReportDraft
from fitbit_report.types import DateRange


def test_report_service_retries_text_meal_analysis_before_context(db_session, monkeypatch):
    import fitbit_report.reports.service as service_module

    calls = []

    class FakeMealTextAnalysisService:
        def __init__(self, analyzer):
            calls.append(("init", analyzer))

        def analyze_period(self, session, start, end, timezone_name):
            calls.append(("period", start, end, timezone_name))

    class FakeRunner:
        model = "sonnet"

        def generate(self, prompt):
            return ReportDraft(
                summary="ok",
                claims=[],
                recommendations=[],
                experiments=[],
                confidence="insufficient",
            )

    monkeypatch.setattr(
        service_module,
        "MealTextAnalysisService",
        FakeMealTextAnalysisService,
        raising=False,
    )
    monkeypatch.setattr(
        service_module,
        "build_report_context",
        lambda session, report_type, period, timezone_name, locale: SimpleNamespace(
            as_dict=lambda: {}
        ),
    )

    service_module.ReportService(FakeRunner()).generate(
        db_session,
        "daily",
        DateRange(date(2026, 8, 16), date(2026, 8, 16)),
    )

    assert calls[1] == ("period", date(2026, 8, 16), date(2026, 8, 16), "Europe/Kiev")


def test_report_service_passes_configured_locale_to_prompt(db_session, monkeypatch):
    import fitbit_report.reports.service as service_module

    prompt_locales = []
    context_locales = []

    class FakeMealTextAnalysisService:
        def __init__(self, analyzer):
            pass

        def analyze_period(self, session, start, end, timezone_name):
            pass

    class FakeRunner:
        model = "sonnet"

        def generate(self, prompt):
            return ReportDraft(
                summary="ok",
                claims=[],
                recommendations=[],
                experiments=[],
                confidence="insufficient",
            )

    monkeypatch.setattr(service_module, "MealTextAnalysisService", FakeMealTextAnalysisService)
    monkeypatch.setattr(
        service_module,
        "build_report_context",
        lambda *args: context_locales.append(args[-1])
        or SimpleNamespace(as_dict=lambda: {}),
    )
    monkeypatch.setattr(
        service_module,
        "build_prompt",
        lambda context, locale: prompt_locales.append(locale) or "prompt",
    )

    service_module.ReportService(FakeRunner(), locale="en").generate(
        db_session,
        "daily",
        DateRange(date(2026, 8, 17), date(2026, 8, 17)),
    )

    assert context_locales == ["en"]
    assert prompt_locales == ["en"]
