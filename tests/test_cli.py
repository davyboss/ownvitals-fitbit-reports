from datetime import date
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import fitbit_report.cli as cli
from fitbit_report.cli import app
from fitbit_report.types import DateRange, ReportResult


def test_cli_help_lists_reserved_commands():
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "init-db" in result.stdout
    assert "google-health-auth" in result.stdout
    assert "report" in result.stdout
    assert "test-report" in result.stdout
    assert "google-health-backfill" in result.stdout
    assert "create-demo-db" in result.stdout


def test_test_report_syncs_generates_prints_and_sends(monkeypatch):
    calls = []
    settings = SimpleNamespace(
        timezone="Europe/Kiev",
        telegram_bot_token="token",
        telegram_allowed_chat_id=42,
    )
    report = ReportResult(
        "daily",
        DateRange(date(2026, 8, 12), date(2026, 8, 12)),
        Path("obsidian-vault/Health/Daily/2026-08-12.md"),
        "# Daily report\nGood day",
    )

    class FakeServices:
        def __init__(self, received_settings):
            assert received_settings is settings

        async def sync(self, day):
            calls.append(("sync", day))
            return SimpleNamespace(status="success", fetched=13, inserted=4, normalized=4)

        async def generate_report(self, report_type, day):
            calls.append(("generate", report_type, day))
            return report

    async def fake_send(received_settings, received_report):
        calls.append(("send", received_settings, received_report))

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda received_settings: None)
    monkeypatch.setattr(cli, "RuntimeServices", FakeServices)
    monkeypatch.setattr(cli, "_send_test_report", fake_send)

    result = CliRunner().invoke(app, ["test-report"])

    assert result.exit_code == 0, result.output
    assert "# Daily report" in result.stdout
    assert calls[0][0] == "sync"
    assert calls[1][0:2] == ("generate", "daily")
    assert calls[2] == ("send", settings, report)


def test_test_report_can_use_existing_demo_data_without_sync(monkeypatch):
    calls = []
    settings = SimpleNamespace(
        timezone="Europe/Kiev",
        telegram_bot_token="token",
        telegram_allowed_chat_id=42,
    )
    report = ReportResult(
        "daily",
        DateRange(date(2026, 9, 15), date(2026, 9, 15)),
        Path("reports/2026-09-15.md"),
        "# Synthetic daily report",
    )

    class FakeServices:
        def __init__(self, received_settings):
            assert received_settings is settings

        async def sync(self, day):
            raise AssertionError("sync must not run with --no-sync")

        async def generate_report(self, report_type, day):
            calls.append(("generate", report_type, day))
            return report

    async def fake_send(received_settings, received_report):
        calls.append(("send", received_settings, received_report))

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda received_settings: None)
    monkeypatch.setattr(cli, "RuntimeServices", FakeServices)
    monkeypatch.setattr(cli, "_send_test_report", fake_send)

    result = CliRunner().invoke(
        app,
        ["test-report", "--date", "2026-09-15", "--no-sync"],
    )

    assert result.exit_code == 0, result.output
    assert "Google Health sync: skipped" in result.stdout
    assert calls[0] == ("generate", "daily", date(2026, 9, 15))
    assert calls[1] == ("send", settings, report)


def test_test_report_rejects_invalid_date_without_traceback(monkeypatch):
    settings = SimpleNamespace(timezone="Europe/Kiev")
    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda received_settings: None)

    result = CliRunner().invoke(app, ["test-report", "--date", "15-09-2026"])

    assert result.exit_code != 0
    assert "YYYY-MM-DD" in result.output
    assert "Traceback" not in result.output


def test_create_demo_db_command(tmp_path):
    path = tmp_path / "screenshots.db"

    result = CliRunner().invoke(
        app,
        [
            "create-demo-db",
            "--output",
            str(path),
            "--date",
            "2026-09-15",
        ],
    )

    assert result.exit_code == 0, result.output
    assert path.exists()
    assert "Synthetic demo database created" in result.stdout
    assert "--date 2026-09-15 --no-sync" in result.stdout


def test_google_health_backfill_syncs_requested_number_of_days(monkeypatch):
    calls = []
    settings = SimpleNamespace(timezone="Europe/Kiev")

    class FakeServices:
        def __init__(self, received_settings):
            assert received_settings is settings

        async def sync_range(self, start, end):
            calls.append((start, end))
            return [SimpleNamespace(status="success", fetched=13, inserted=4, normalized=4)]

    monkeypatch.setattr(cli, "load_settings", lambda: settings)
    monkeypatch.setattr(cli, "configure_logging", lambda received_settings: None)
    monkeypatch.setattr(cli, "RuntimeServices", FakeServices)

    result = CliRunner().invoke(app, ["google-health-backfill", "--days", "90"])

    assert result.exit_code == 0, result.output
    start, end = calls[0]
    assert (end - start).days == 89
    assert "Backfill complete" in result.stdout
