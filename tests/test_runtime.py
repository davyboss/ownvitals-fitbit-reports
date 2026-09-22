from datetime import date, datetime, timedelta
from types import SimpleNamespace

from fitbit_report.runtime import (
    build_question_prompt,
    should_run_daily,
    should_run_weekly,
    should_run_monthly,
)
from fitbit_report.runtime import InProcessScheduler


def test_daily_job_runs_once_for_local_day():
    assert should_run_daily(datetime(2026, 8, 12, 8, 0), date(2026, 8, 12), None)
    assert not should_run_daily(datetime(2026, 8, 12, 8, 0), date(2026, 8, 12), date(2026, 8, 12))


def test_english_question_prompt_requests_an_english_user_facing_answer():
    prompt = build_question_prompt("Should I train today?", {"steps": 5000}, "en")

    assert "Answer the user's question concisely in English" in prompt
    assert "Should I train today?" in prompt
    assert '"steps": 5000' in prompt
    assert "кратко и по-русски" not in prompt


def test_runtime_sync_runs_blocking_work_in_a_worker_thread():
    import asyncio
    import threading

    from fitbit_report.runtime import RuntimeServices

    services = RuntimeServices.__new__(RuntimeServices)
    services._sync_sync = lambda _day: threading.get_ident()

    worker_thread_id = asyncio.run(services.sync(date(2026, 8, 12)))

    assert worker_thread_id != threading.get_ident()


def test_weekly_job_runs_only_on_configured_weekday():
    monday = datetime(2026, 8, 10, 8, 15)
    assert should_run_weekly(monday, 0, None)
    assert not should_run_weekly(monday, 1, None)


def test_monthly_job_runs_on_first_day_only():
    assert should_run_monthly(datetime(2026, 8, 1, 8, 30), None)
    assert not should_run_monthly(datetime(2026, 8, 2, 8, 30), None)


def test_in_process_scheduler_runs_sync_and_daily_report_once():
    import asyncio
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult, SyncSummary

    sync_days = []
    report_calls = []

    async def sync(day=None):
        sync_days.append(day)
        return SyncSummary("success", day or date(2026, 8, 12))

    async def report(kind, day):
        report_calls.append((kind, day))
        return ReportResult(
            kind,
            DateRange(day, day),
            Path("report.md"),
            "report",
        )

    async def backup():
        pass

    settings = type("Settings", (), {
        "sync_interval_minutes": 240,
        "daily_report_time": "08:00",
        "weekly_report_time": "08:15",
        "monthly_report_time": "08:30",
        "backup_time": "03:00",
        "weekly_report_weekday": 0,
        "scheduler_tick_seconds": 1,
        "timezone": "Europe/Kiev",
    })()
    scheduler = InProcessScheduler(settings, sync, report, backup)

    async def exercise():
        now = datetime(2026, 8, 12, 8, 1)
        await scheduler.tick(now)
        await scheduler.tick(now)

    asyncio.run(exercise())
    assert sync_days == [None, date(2026, 8, 11)]
    assert report_calls == [("daily", date(2026, 8, 11))]


def test_scheduler_runs_fatsecret_import_once_at_configured_time(caplog):
    import asyncio
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult, SyncSummary

    caplog.set_level(20, logger="fitbit_report.runtime")
    calls = []

    async def sync(day=None):
        return SyncSummary("success", day or date(2026, 8, 12))

    async def report(kind, day):
        return ReportResult(kind, DateRange(day, day), Path("report.md"), "report")

    async def backup():
        pass

    async def fatsecret(day):
        calls.append(day)
        return {"status": "private-status-value", "food_count": 987654321}

    settings = type("Settings", (), {
        "sync_interval_minutes": 240,
        "fatsecret_auto_import_time": "23:30",
        "daily_report_time": "23:59",
        "weekly_report_time": "23:59",
        "monthly_report_time": "23:59",
        "backup_time": "23:59",
        "weekly_report_weekday": 0,
        "scheduler_tick_seconds": 1,
        "timezone": "Europe/Kiev",
    })()
    scheduler = InProcessScheduler(
        settings, sync, report, backup, run_fatsecret_sync=fatsecret
    )

    async def exercise():
        await scheduler.tick(datetime(2026, 8, 12, 23, 30))
        await scheduler.tick(datetime(2026, 8, 12, 23, 31))

    asyncio.run(exercise())
    assert calls == [date(2026, 8, 12)]
    assert "scheduled FatSecret import attempt completed date=2026-08-12" in caplog.text
    assert "private-status-value" not in caplog.text
    assert "987654321" not in caplog.text


def test_scheduler_notifies_only_after_successful_generation():
    import asyncio
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult, SyncSummary

    calls = []

    async def sync(day=None):
        calls.append("sync" if day is None else f"sync:{day}")
        return SyncSummary("success", day or date(2026, 8, 12))

    async def report(kind, day):
        calls.append(f"{kind}:{day}")
        return ReportResult(
            kind,
            DateRange(day, day),
            Path("report.md"),
            "report",
        )

    async def notify(result):
        calls.append(f"notify:{result.report_type}")

    async def backup():
        pass

    settings = type("Settings", (), {
        "sync_interval_minutes": 240,
        "daily_report_time": "08:00",
        "weekly_report_time": "08:15",
        "monthly_report_time": "08:30",
        "backup_time": "03:00",
        "weekly_report_weekday": 0,
        "scheduler_tick_seconds": 1,
        "timezone": "Europe/Kiev",
    })()
    scheduler = InProcessScheduler(settings, sync, report, backup, notify)

    async def exercise():
        await scheduler.tick(datetime(2026, 8, 12, 8, 1))

    asyncio.run(exercise())

    assert calls == ["sync", "sync:2026-08-11", "daily:2026-08-11", "notify:daily"]


def test_scheduler_does_not_notify_already_delivered_report_after_restart():
    import asyncio
    from pathlib import Path
    from datetime import datetime, timezone

    from fitbit_report.types import DateRange, ReportResult, SyncSummary

    calls = []

    async def sync(day=None):
        return SyncSummary("success", day or date(2026, 8, 12))

    async def report(kind, day):
        return ReportResult(
            kind,
            DateRange(day, day),
            Path("report.md"),
            "report",
            report_id=7,
            telegram_sent_at=datetime.now(timezone.utc),
        )

    async def notify(result):
        calls.append("notify")

    async def backup():
        pass

    settings = type("Settings", (), {
        "sync_interval_minutes": 240,
        "daily_report_time": "08:00",
        "weekly_report_time": "23:59",
        "monthly_report_time": "23:59",
        "backup_time": "23:59",
        "weekly_report_weekday": 0,
        "scheduler_tick_seconds": 1,
        "timezone": "Europe/Kiev",
    })()
    scheduler = InProcessScheduler(settings, sync, report, backup, notify)

    asyncio.run(scheduler.tick(datetime(2026, 8, 15, 22, 0)))

    assert calls == []


def test_scheduler_marks_report_delivered_after_telegram_send():
    import asyncio
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult, SyncSummary

    calls = []

    async def sync(day=None):
        return SyncSummary("success", day or date(2026, 8, 12))

    async def report(kind, day):
        return ReportResult(
            kind,
            DateRange(day, day),
            Path("report.md"),
            "report",
            report_id=7,
        )

    async def notify(result):
        calls.append("notify")

    async def mark(report_id):
        calls.append(f"mark:{report_id}")

    async def backup():
        pass

    settings = type("Settings", (), {
        "sync_interval_minutes": 240,
        "daily_report_time": "08:00",
        "weekly_report_time": "23:59",
        "monthly_report_time": "23:59",
        "backup_time": "23:59",
        "weekly_report_weekday": 0,
        "scheduler_tick_seconds": 1,
        "timezone": "Europe/Kiev",
    })()
    scheduler = InProcessScheduler(
        settings,
        sync,
        report,
        backup,
        notify,
        mark_report_notified=mark,
    )

    asyncio.run(scheduler.tick(datetime(2026, 8, 15, 22, 0)))

    assert calls == ["notify", "mark:7"]


def test_scheduler_refreshes_recent_three_days_before_daily_report():
    import asyncio
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult, SyncSummary

    calls = []

    async def sync(day=None):
        calls.append(("sync", day))
        return SyncSummary("success", day or date(2026, 8, 12))

    async def sync_range(start, end):
        calls.append(("range", start, end))
        return [SyncSummary("success", current) for current in _date_range(start, end)]

    async def report(kind, day):
        calls.append((kind, day))
        return ReportResult(kind, DateRange(day, day), Path("report.md"), "report")

    async def backup():
        pass

    settings = type("Settings", (), {
        "sync_interval_minutes": 240,
        "daily_report_time": "08:00",
        "weekly_report_time": "23:59",
        "monthly_report_time": "23:59",
        "backup_time": "23:59",
        "weekly_report_weekday": 0,
        "scheduler_tick_seconds": 1,
        "timezone": "Europe/Kiev",
    })()
    scheduler = InProcessScheduler(settings, sync, report, backup, run_sync_range=sync_range)

    async def exercise():
        await scheduler.tick(datetime(2026, 8, 12, 8, 1))

    asyncio.run(exercise())

    assert calls == [
        ("sync", None),
        ("range", date(2026, 8, 9), date(2026, 8, 11)),
        ("daily", date(2026, 8, 11)),
    ]


def test_scheduler_refreshes_exact_week_before_weekly_report():
    import asyncio
    from pathlib import Path

    from fitbit_report.types import DateRange, ReportResult, SyncSummary

    calls = []

    async def sync(day=None):
        calls.append(("sync", day))
        return SyncSummary("success", day or date(2026, 8, 12))

    async def sync_range(start, end):
        calls.append(("range", start, end))
        return [SyncSummary("success", current) for current in _date_range(start, end)]

    async def report(kind, day):
        calls.append((kind, day))
        return ReportResult(kind, DateRange(day - timedelta(days=day.weekday()), day), Path("report.md"), "report")

    async def backup():
        pass

    settings = type("Settings", (), {
        "sync_interval_minutes": 240,
        "daily_report_time": "23:59",
        "weekly_report_time": "08:15",
        "monthly_report_time": "23:59",
        "backup_time": "23:59",
        "weekly_report_weekday": 0,
        "scheduler_tick_seconds": 1,
        "timezone": "Europe/Kiev",
    })()
    scheduler = InProcessScheduler(settings, sync, report, backup, run_sync_range=sync_range)

    async def exercise():
        await scheduler.tick(datetime(2026, 8, 10, 8, 16))

    asyncio.run(exercise())

    assert calls == [
        ("sync", None),
        ("range", date(2026, 8, 3), date(2026, 8, 9)),
        ("weekly", date(2026, 8, 9)),
    ]


def test_runtime_sync_uses_google_health_sync(monkeypatch, tmp_path):

    from fitbit_report.google_health import client as client_module
    from fitbit_report.google_health import oauth as oauth_module
    from fitbit_report.google_health import sync as sync_module
    from fitbit_report.types import SyncSummary
    from fitbit_report.runtime import RuntimeServices

    calls = []

    class FakeCredentials:
        token = "access"
        valid = True

    class FakeStore:
        def __init__(self, path):
            self.path = path

        def load(self):
            return FakeCredentials()

    class FakeOAuth:
        def __init__(self, settings, token_store):
            self.settings = settings
            self.token_store = token_store

        def refresh_if_needed(self, credentials):
            return credentials

    class FakeClient:
        def __init__(self, http, credentials, token_store):
            self.http = http
            self.credentials = credentials
            self.token_store = token_store

    class FakeSync:
        def __init__(self, client, timezone_name):
            self.client = client
            self.timezone_name = timezone_name

        def sync_day(self, day, session):
            calls.append(day)
            return SyncSummary("success", day, fetched=1, inserted=1, normalized=1)

    monkeypatch.setattr(oauth_module, "GoogleHealthTokenStore", FakeStore)
    monkeypatch.setattr(oauth_module, "GoogleHealthOAuth", FakeOAuth)
    monkeypatch.setattr(client_module, "GoogleHealthClient", FakeClient)
    monkeypatch.setattr(sync_module, "GoogleHealthSync", FakeSync)
    settings = SimpleNamespace(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        google_health_token_path=tmp_path / "token.json",
        timezone="Europe/Kiev",
    )

    summary = RuntimeServices(settings)._sync_sync(date(2026, 8, 12))

    assert calls == [date(2026, 8, 12)]
    assert summary.status == "success"


def test_runtime_sync_range_uses_google_health_sync(monkeypatch, tmp_path):

    from fitbit_report.google_health import client as client_module
    from fitbit_report.google_health import oauth as oauth_module
    from fitbit_report.google_health import sync as sync_module
    from fitbit_report.types import SyncSummary
    from fitbit_report.runtime import RuntimeServices

    calls = []

    class FakeCredentials:
        token = "access"
        valid = True

    class FakeStore:
        def __init__(self, path):
            self.path = path

        def load(self):
            return FakeCredentials()

    class FakeOAuth:
        def __init__(self, settings, token_store):
            self.settings = settings
            self.token_store = token_store

        def refresh_if_needed(self, credentials):
            return credentials

    class FakeClient:
        def __init__(self, http, credentials, token_store):
            self.http = http
            self.credentials = credentials
            self.token_store = token_store

    class FakeSync:
        def __init__(self, client, timezone_name):
            self.client = client
            self.timezone_name = timezone_name

        def sync_range(self, start, end, session):
            calls.append((start, end))
            return [SyncSummary("success", start), SyncSummary("success", end)]

    monkeypatch.setattr(oauth_module, "GoogleHealthTokenStore", FakeStore)
    monkeypatch.setattr(oauth_module, "GoogleHealthOAuth", FakeOAuth)
    monkeypatch.setattr(client_module, "GoogleHealthClient", FakeClient)
    monkeypatch.setattr(sync_module, "GoogleHealthSync", FakeSync)
    settings = SimpleNamespace(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        google_health_token_path=tmp_path / "token.json",
        timezone="Europe/Kiev",
    )

    summaries = RuntimeServices(settings)._sync_range_sync(
        date(2026, 8, 3), date(2026, 8, 9)
    )

    assert calls == [(date(2026, 8, 3), date(2026, 8, 9))]
    assert len(summaries) == 2


def _date_range(start, end):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def test_generate_report_returns_saved_result(monkeypatch, tmp_path):
    import json
    from contextlib import contextmanager

    import fitbit_report.runtime as runtime
    from fitbit_report.runtime import RuntimeServices

    settings = SimpleNamespace(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        obsidian_vault=tmp_path / "vault",
        timezone="Europe/Kiev",
        claude_model="sonnet",
        claude_max_turns=1,
    )
    report_path = tmp_path / "vault" / "Health" / "Daily" / "2026-08-12.md"
    fake_report = SimpleNamespace(
        status="success",
        draft_json=json.dumps({
            "summary": "Good day",
            "claims": [],
            "recommendations": [],
            "experiments": [],
        }),
        period_start=date(2026, 8, 12),
        period_end=date(2026, 8, 12),
        model="sonnet",
        context_hash="hash",
        context_json="{}",
        error_message=None,
        id=None,
        telegram_sent_at=None,
    )

    class FakeReportService:
        def __init__(self, runner):
            self.runner = runner

        def generate(self, session, report_type, period):
            return fake_report

    @contextmanager
    def fake_session_scope(engine):
        yield object()

    monkeypatch.setattr(runtime, "ReportService", FakeReportService)
    monkeypatch.setattr(runtime, "session_scope", fake_session_scope)
    monkeypatch.setattr(runtime, "write_report", lambda *args: report_path)
    monkeypatch.setattr(runtime, "generate_report_charts", lambda *args: [])

    result = RuntimeServices(settings)._generate_report_sync("daily")

    assert result.path == report_path
    assert result.report_type == "daily"
    assert "Good day" in result.markdown


def test_generate_report_reads_persistent_metadata_before_session_closes(monkeypatch, tmp_path):
    import json
    from contextlib import contextmanager

    import fitbit_report.runtime as runtime
    from fitbit_report.db.models import GeneratedReport
    from fitbit_report.runtime import RuntimeServices

    settings = SimpleNamespace(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        obsidian_vault=tmp_path / "vault",
        timezone="Europe/Kiev",
        claude_model="sonnet",
        claude_max_turns=1,
    )
    report_path = tmp_path / "vault" / "Health" / "Daily" / "2026-08-12.md"

    class FakeReportService:
        def __init__(self, runner):
            self.runner = runner

        def generate(self, session, report_type, period):
            report = GeneratedReport(
                report_type=report_type,
                period_start=period.start,
                period_end=period.end,
                status="success",
                model="sonnet",
                prompt_version="test",
                context_hash="hash",
                context_json="{}",
                draft_json=json.dumps({
                    "summary": "Good day",
                    "claims": [],
                    "recommendations": [],
                    "experiments": [],
                }),
            )
            session.add(report)
            session.flush()
            return report

    @contextmanager
    def fake_session_scope(engine):
        from sqlalchemy.orm import Session

        session = Session(engine)
        try:
            yield session
            session.commit()
        finally:
            session.close()

    monkeypatch.setattr(runtime, "ReportService", FakeReportService)
    monkeypatch.setattr(runtime, "session_scope", fake_session_scope)
    monkeypatch.setattr(runtime, "write_report", lambda *args: report_path)
    monkeypatch.setattr(runtime, "generate_report_charts", lambda *args: [])

    result = RuntimeServices(settings)._generate_report_sync("daily")

    assert result.report_id is not None
    assert result.telegram_sent_at is None


def test_generate_report_raises_on_failed_claude_result(monkeypatch, tmp_path):
    from contextlib import contextmanager

    import fitbit_report.runtime as runtime
    from fitbit_report.runtime import ReportGenerationError, RuntimeServices

    settings = SimpleNamespace(
        database_url=f"sqlite:///{tmp_path / 'app.db'}",
        obsidian_vault=tmp_path / "vault",
        timezone="Europe/Kiev",
        claude_model="sonnet",
        claude_max_turns=1,
    )
    fake_report = SimpleNamespace(status="failed", error_message="Claude CLI failed")

    class FakeReportService:
        def __init__(self, runner):
            self.runner = runner

        def generate(self, session, report_type, period):
            return fake_report

    @contextmanager
    def fake_session_scope(engine):
        yield object()

    monkeypatch.setattr(runtime, "ReportService", FakeReportService)
    monkeypatch.setattr(runtime, "session_scope", fake_session_scope)
    monkeypatch.setattr(runtime, "generate_report_charts", lambda *args: [])

    try:
        RuntimeServices(settings)._generate_report_sync("daily")
    except ReportGenerationError as exc:
        assert "Claude CLI failed" in str(exc)
    else:
        raise AssertionError("failed report must raise ReportGenerationError")
