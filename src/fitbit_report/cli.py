import asyncio
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

from fitbit_report.config import load_settings
from fitbit_report.logging_config import configure_logging
from fitbit_report.runtime import RuntimeServices
from fitbit_report.types import ReportType


app = typer.Typer(
    help="OwnVitals for Fitbit and Pixel Watch: self-hosted health reports"
)
logger = logging.getLogger(__name__)


async def _send_test_report(settings, result) -> None:
    from telegram import Bot

    from fitbit_report.integrations.telegram import send_report

    async with Bot(token=settings.telegram_bot_token) as bot:
        await send_report(
            bot,
            settings.telegram_allowed_chat_id,
            result,
            getattr(settings, "app_locale", "ru"),
        )


def _parse_iso_date(value: str, option_name: str = "--date") -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            "Use YYYY-MM-DD, for example 2026-09-15.",
            param_hint=option_name,
        ) from exc


async def _run_test_report(settings, day, *, sync_data: bool = True):
    services = RuntimeServices(settings)
    summary = None
    if sync_data:
        summary = await services.sync(day)
        if summary is None:
            raise RuntimeError("Google Health is not authorized. Run google-health-auth first.")
        if summary.status != "success":
            error_type = f" ({summary.error_type})" if summary.error_type else ""
            raise RuntimeError(f"Google Health sync failed{error_type}.")
    result = await services.generate_report("daily", day)
    await _send_test_report(settings, result)
    return summary, result


@app.command("init-db")
def init_db_command() -> None:
    """Initialize the local SQLite database."""
    from fitbit_report.db.session import create_engine_from_settings, init_db

    settings = load_settings()
    configure_logging(settings)
    init_db(create_engine_from_settings(settings))
    typer.echo("Database initialized")


@app.command("status")
def status_command() -> None:
    """Print configured local paths and runtime settings."""
    settings = load_settings()
    typer.echo(f"google_health_client_secrets={settings.google_health_client_secrets}")
    typer.echo(f"google_health_token_path={settings.google_health_token_path}")
    typer.echo(f"google_health_scopes={settings.google_health_scopes}")
    typer.echo(f"database={settings.database_url}")
    typer.echo(f"raw_data_dir={settings.raw_data_dir}")
    typer.echo(f"obsidian_vault={settings.obsidian_vault}")
    typer.echo(f"timezone={settings.timezone}")
    typer.echo(
        f"claude_report_model={getattr(settings, 'claude_report_model', settings.claude_model)}"
    )
    typer.echo(
        f"claude_question_model={getattr(settings, 'claude_question_model', settings.claude_model)}"
    )


@app.command("sync")
def sync_command(day: str | None = typer.Option(None, "--date")) -> None:
    """Synchronize Google Health data for one date."""
    from datetime import date as date_type

    from fitbit_report.db.session import create_engine_from_settings, init_db, session_scope
    from fitbit_report.google_health.client import GoogleHealthClient
    from fitbit_report.google_health.oauth import GoogleHealthOAuth, GoogleHealthTokenStore
    from fitbit_report.google_health.schemas import GoogleHealthAuthorizationRequired
    from fitbit_report.google_health.sync import GoogleHealthSync
    import httpx

    settings = load_settings()
    engine = create_engine_from_settings(settings)
    init_db(engine)
    target = _parse_iso_date(day) if day else date_type.today()
    token_store = GoogleHealthTokenStore(settings.google_health_token_path)
    credentials = token_store.load()
    if credentials is None:
        raise typer.BadParameter("Run google-health-auth before sync")
    oauth = GoogleHealthOAuth(settings, token_store=token_store)
    try:
        credentials = oauth.refresh_if_needed(credentials)
    except GoogleHealthAuthorizationRequired as exc:
        raise typer.BadParameter(str(exc)) from exc
    client = GoogleHealthClient(
        http=httpx.Client(timeout=30),
        credentials=credentials,
        token_store=token_store,
    )
    with session_scope(engine) as session:
        summary = GoogleHealthSync(client, settings.timezone).sync_day(target, session)
    typer.echo(summary.status)
    if summary.status != "success":
        raise typer.Exit(code=1)


@app.command("google-health-backfill")
def google_health_backfill_command(
    days: int = typer.Option(90, "--days", min=1, max=365),
) -> None:
    """Load a bounded history from Google Health for the personal baseline."""
    from datetime import timedelta

    settings = load_settings()
    configure_logging(settings)
    end = datetime.now(ZoneInfo(settings.timezone)).date() - timedelta(days=1)
    start = end - timedelta(days=days - 1)
    try:
        summaries = asyncio.run(RuntimeServices(settings).sync_range(start, end))
    except Exception as exc:
        logger.exception("Google Health backfill failed")
        typer.echo(f"Google Health backfill failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not summaries or any(summary.status != "success" for summary in summaries):
        typer.echo("Google Health backfill failed", err=True)
        raise typer.Exit(code=1)
    typer.echo(
        f"Backfill complete: {start}..{end}, days={len(summaries)}, "
        f"fetched={sum(summary.fetched for summary in summaries)}, "
        f"inserted_or_updated={sum(summary.inserted for summary in summaries)}"
    )


@app.command("google-health-auth")
def google_health_auth_command() -> None:
    """Authorize the personal Google Health API connection."""
    from sqlalchemy import select

    from fitbit_report.db.models import GoogleHealthIdentity
    from fitbit_report.db.session import create_engine_from_settings, init_db, session_scope
    from fitbit_report.google_health.oauth import GoogleHealthOAuth, GoogleHealthTokenStore

    settings = load_settings()
    token_store = GoogleHealthTokenStore(settings.google_health_token_path)
    oauth = GoogleHealthOAuth(settings, token_store=token_store)
    credentials = oauth.authorize()
    identity = oauth.get_identity(credentials)

    engine = create_engine_from_settings(settings)
    init_db(engine)
    with session_scope(engine) as session:
        record = session.scalar(
            select(GoogleHealthIdentity).where(GoogleHealthIdentity.singleton_key == "me")
        )
        if record is None:
            record = GoogleHealthIdentity(singleton_key="me")
            session.add(record)
        record.health_user_id = identity.health_user_id
        record.legacy_user_id = identity.legacy_user_id

    typer.echo("Google Health authorization completed")
    typer.echo(f"Token saved to {settings.google_health_token_path}")


@app.command("bot")
def bot_command() -> None:
    """Run the Telegram bot."""
    from fitbit_report.integrations.telegram import build_application

    settings = load_settings()
    application = build_application(settings, {})
    application.run_polling()


@app.command("report")
def report_command(
    report_type: ReportType = typer.Option("daily", "--type"),
) -> None:
    """Generate a report for the requested period."""
    from datetime import date as date_type

    from fitbit_report.db.session import session_scope
    from fitbit_report.reports.service import ReportService
    from fitbit_report.runtime import report_period

    settings = load_settings()
    services = RuntimeServices(settings)
    today = date_type.today()
    with session_scope(services.engine) as session:
        report = ReportService(
            services.make_llm_runner(operation="report"),
            timezone_name=settings.timezone,
            locale=getattr(settings, "app_locale", "en"),
        ).generate(session, report_type, report_period(report_type, today))
    typer.echo(report.status)
    if report.status != "success":
        raise typer.Exit(code=1)


@app.command("model-benchmark")
def model_benchmark_command(
    day: str | None = typer.Option(None, "--date", help="Data date in YYYY-MM-DD format."),
    report_type: ReportType = typer.Option("daily", "--type"),
    models: str = typer.Option(
        "claude-opus-5,claude-sonnet-5,claude-haiku-4-5-20251001",
        "--models",
        help="Comma-separated Claude models.",
    ),
    repeats: int = typer.Option(1, "--repeats", min=1, max=5),
    monthly_calls: int = typer.Option(
        30,
        "--monthly-calls",
        min=1,
        help="Monthly call count used for the API-cost projection.",
    ),
    subscription_price_usd: float = typer.Option(
        20.0,
        "--subscription-price-usd",
        min=0,
        help="Subscription price used for break-even calculations; default: USD 20/month.",
    ),
    output_dir: Path = typer.Option(
        Path("data/model-benchmarks"),
        "--output-dir",
        help="Directory for benchmark JSON results.",
    ),
) -> None:
    """Compare Claude CLI models on the same report context."""
    from datetime import date as date_type, timedelta

    from fitbit_report.reports.benchmark import run_benchmark, save_benchmark

    settings = load_settings()
    configure_logging(settings)
    target_day = (
        date_type.fromisoformat(day)
        if day
        else datetime.now(ZoneInfo(settings.timezone)).date() - timedelta(days=1)
    )
    model_list = [item.strip() for item in models.split(",") if item.strip()]
    if not model_list:
        raise typer.BadParameter("Provide at least one model in --models")

    try:
        services = RuntimeServices(settings)
        result = run_benchmark(
            services.engine,
            settings.timezone,
            report_type,
            target_day,
            models=model_list,
            repeats=repeats,
            max_turns=max(1, settings.claude_max_turns),
            subscription_price_usd=subscription_price_usd,
            monthly_calls=monthly_calls,
            usage_recorder=services.record_llm_usage,
            locale=getattr(settings, "app_locale", "ru"),
        )
        path = save_benchmark(result, output_dir)
    except Exception as exc:
        logger.exception("model benchmark failed")
        typer.echo(f"Model benchmark failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Benchmark saved: {path}")
    typer.echo(f"Period: {result['period']}; prompt: {result['prompt_sha256'][:12]}...")
    typer.echo("\nModel comparison:")
    typer.echo(
        "model | quality/100 | API-equivalent/run USD | API-equivalent/month USD | break-even calls"
    )
    for item in result["results"]:
        break_even = item["break_even_calls_vs_subscription"]
        break_even_text = f"{break_even:.2f}" if break_even is not None else "n/a"
        estimated = " (estimated tokens)" if item["usage_is_estimated"] else ""
        typer.echo(
            f"{item['model']} | {item['average_quality_score']:.2f} | "
            f"{item['average_api_cost_usd']:.6f}{estimated} | "
            f"{item['projected_api_cost_usd_per_month']:.4f} | {break_even_text}"
        )
    typer.echo(f"\nBest quality by heuristic: {result['best_quality_model'] or 'n/a'}")
    typer.echo(f"Best quality/cost ratio: {result['best_value_model'] or 'n/a'}")
    typer.echo(
        "Full model answers and scoring details are in the JSON file; review them manually before switching production."
    )


@app.command("test-report")
def test_report_command(
    day: str | None = typer.Option(
        None,
        "--date",
        help="Report date in YYYY-MM-DD format; defaults to today.",
    ),
    sync_data: bool = typer.Option(
        True,
        "--sync/--no-sync",
        help="Synchronize Google Health before generating the report.",
    ),
) -> None:
    """Generate a daily report, print it, and send it to Telegram."""
    settings = load_settings()
    configure_logging(settings)
    target_day = _parse_iso_date(day) if day else datetime.now(ZoneInfo(settings.timezone)).date()
    try:
        summary, result = asyncio.run(_run_test_report(settings, target_day, sync_data=sync_data))
    except Exception as exc:
        logger.exception("test report failed")
        typer.echo(f"Test report failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if summary is None:
        typer.echo("Google Health sync: skipped")
    else:
        typer.echo(
            f"Google Health sync: fetched={summary.fetched}, "
            f"inserted={summary.inserted}, normalized={summary.normalized}"
        )
    typer.echo(f"Report saved: {result.path}")
    typer.echo("Telegram delivery: sent")
    typer.echo("\n" + result.markdown)


@app.command("create-demo-db")
def create_demo_db_command(
    output: Path = typer.Option(
        Path("data/ownvitals-demo.db"),
        "--output",
        help="Destination SQLite file.",
    ),
    day: str = typer.Option(
        "2026-09-15",
        "--date",
        help="Final demo date in YYYY-MM-DD format.",
    ),
    days: int = typer.Option(35, "--days", min=29, max=365),
    seed: int = typer.Option(20260915, "--seed"),
    timezone_name: str = typer.Option(
        "Europe/Kiev",
        "--timezone",
        help="Timezone used for synthetic event times.",
    ),
    force: bool = typer.Option(False, "--force", help="Replace an existing file."),
) -> None:
    """Create a deterministic SQLite database with synthetic screenshot data."""
    from fitbit_report.demo import create_demo_database

    target_day = _parse_iso_date(day)
    try:
        path = create_demo_database(
            output,
            target_day,
            days=days,
            seed=seed,
            timezone_name=timezone_name,
            force=force,
        )
    except (FileExistsError, ValueError) as exc:
        typer.echo(f"Demo database was not created: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    database_url = f"sqlite:///{path.as_posix()}"
    typer.echo(f"Synthetic demo database created: {path}")
    typer.echo(f"Demo report date: {target_day}")
    typer.echo(f"Use DATABASE_URL={database_url}")
    typer.echo(f"Then run: python -m fitbit_report.cli test-report --date {target_day} --no-sync")


@app.command("backup")
def backup_command() -> None:
    """Create a local backup archive."""
    from datetime import datetime, timezone

    from fitbit_report.scheduler import create_backup

    settings = load_settings()
    path = create_backup(settings, datetime.now(timezone.utc))
    typer.echo(str(path))


if __name__ == "__main__":
    app()
