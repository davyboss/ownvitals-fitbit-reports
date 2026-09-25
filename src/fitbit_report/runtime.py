import asyncio
import json
import logging
import calendar
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from fitbit_report.async_utils import run_in_thread
from fitbit_report.config import Settings
from fitbit_report.db.session import create_engine_from_settings, init_db, session_scope
from fitbit_report.integrations.obsidian import write_report
from fitbit_report.integrations.telegram import (
    build_application,
    feedback_claim_summaries,
    feedback_claim_indices,
    send_report,
)
from fitbit_report.google_health.schemas import GoogleHealthAuthorizationRequired
from fitbit_report.reports.llm_runner import ClaudeCliRunner
from fitbit_report.reports.charts import generate_report_charts
from fitbit_report.reports.renderer import (
    render_markdown,
    render_telegram_parts,
    render_telegram_rich,
)
from fitbit_report.reports.service import ReportService
from fitbit_report.scheduler import create_backup
from fitbit_report.types import DateRange, ReportResult, ReportType, SyncSummary

logger = logging.getLogger(__name__)


class ReportGenerationError(RuntimeError):
    pass


def should_run_daily(now: datetime, today: date, last_run: date | None) -> bool:
    return now.date() == today and now.strftime("%H:%M") >= "08:00" and last_run != today


def should_run_weekly(now: datetime, weekday: int, last_run: date | None) -> bool:
    return now.weekday() == weekday and now.strftime("%H:%M") >= "08:15" and last_run != now.date()


def should_run_monthly(now: datetime, last_run: date | None) -> bool:
    return now.day == 1 and now.strftime("%H:%M") >= "08:30" and last_run != now.date()


def _parse_clock(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", 1)
    return int(hour), int(minute)


def report_period(report_type: str, day: date) -> DateRange:
    if report_type == "daily":
        return DateRange(day, day)
    if report_type == "weekly":
        start = day - timedelta(days=day.weekday())
        return DateRange(start, start + timedelta(days=6))
    if report_type == "monthly":
        return DateRange(day.replace(day=1), day.replace(day=calendar.monthrange(day.year, day.month)[1]))
    raise ValueError(f"Unsupported report type: {report_type}")


def build_question_prompt(question: str, context: dict, locale: str = "ru") -> str:
    context_json = json.dumps(context, default=str, ensure_ascii=False, sort_keys=True)
    if locale == "en":
        return (
            "You are a personal health and productivity analyst, not a questionnaire. Answer the "
            "user's question concisely in English using only the supplied data. Find the current "
            "and average sleep, sleep and wake times, resting heart rate, HRV, activity, workouts, "
            "and personal baselines yourself. Never ask the user to repeat or confirm a metric that "
            "is already present. Do not invent missing data. Separate facts from hypotheses and "
            "state uncertainty. Keep training advice general and cautious; recommend professional "
            "medical help when symptoms warrant it. Do not diagnose. Start with the calculated "
            "personal readiness state when relevant, then answer the question directly. Do not "
            "repeat raw JSON, expose internal field names such as personal_state or baseline_28d, "
            "or ask follow-up questions about supplied metrics. If data is truly missing, name the "
            "specific missing record. Return only the user-facing answer as plain text, without "
            "JSON, Markdown code fences, or implementation notes.\n\n"
            f"Question: {question}\n\nData from the last 28 days:\n{context_json}"
        )
    return (
        "Ты личный аналитик здоровья и продуктивности, а не анкета. Ответь на вопрос пользователя "
        "по предоставленным данным, кратко и по-русски. Сам найди в контексте текущие и "
        "средние значения сна, время засыпания и пробуждения, пульса покоя, HRV/ВСР, активности, "
        "тренировок и личных норм. "
        "Не проси пользователя повторить или подтвердить показатель, если он уже есть в данных. "
        "Не выдумывай отсутствующие данные, отделяй факты от гипотез, указывай неопределённость. "
        "Советы о тренировках — только общие и осторожные; при симптомах рекомендуй обратиться "
        "к врачу. Не ставь диагноз. Сначала используй рассчитанную персональную оценку состояния "
        "и объясни её, затем ответь на вопрос конкретно; не пересказывай весь сырой JSON, не "
        "раскрывай технические названия полей вроде personal_state или baseline_28d и не задавай "
        "уточняющих вопросов о метриках, которые уже переданы. Если данных действительно нет, "
        "скажи, какой именно записи не хватает. Верни только готовый ответ для пользователя "
        "обычным текстом, без JSON, Markdown-кода и служебных пояснений.\n\n"
        f"Вопрос: {question}\n\nДанные за последние 28 дней:\n{context_json}"
    )


def _refresh_range(report_type: ReportType, target_day: date) -> tuple[date, date]:
    if report_type == "daily":
        return target_day - timedelta(days=2), target_day
    if report_type == "weekly":
        period = report_period("weekly", target_day)
        return period.start, period.end
    return target_day, target_day


class InProcessScheduler:
    def __init__(
        self,
        settings: Settings,
        run_sync: Callable[[date | None], Awaitable[SyncSummary | None]],
        run_report: Callable[[str, date], Awaitable[ReportResult]],
        run_backup: Callable[[], Awaitable[None]],
        notify_report: Callable[[ReportResult], Awaitable[None]] | None = None,
        run_sync_range: Callable[[date, date], Awaitable[list[SyncSummary]]] | None = None,
        mark_report_notified: Callable[[int], Awaitable[None]] | None = None,
        run_fatsecret_sync: Callable[[date], Awaitable[dict[str, object]]] | None = None,
    ):
        self.settings = settings
        self.run_sync = run_sync
        self.run_report = run_report
        self.run_backup = run_backup
        self.notify_report = notify_report
        self.run_sync_range = run_sync_range
        self.mark_report_notified = mark_report_notified
        self.run_fatsecret_sync = run_fatsecret_sync
        self._last_daily: date | None = None
        self._last_weekly: date | None = None
        self._last_monthly: date | None = None
        self._last_backup: date | None = None
        self._last_sync: datetime | None = None
        self._last_fatsecret_sync: date | None = None
        self._report_retry_state: dict[tuple[ReportType, date], tuple[int, datetime]] = {}
        self._lock = asyncio.Lock()

    async def run_forever(self) -> None:
        while True:
            now = datetime.now(ZoneInfo(self.settings.timezone))
            try:
                await self.tick(now)
            except Exception:
                logger.exception("scheduler tick failed; continuing")
            await asyncio.sleep(self.settings.scheduler_tick_seconds)

    async def tick(self, now: datetime) -> None:
        if self._last_sync is None or now - self._last_sync >= timedelta(minutes=self.settings.sync_interval_minutes):
            await self._run_exclusive(self.run_sync)
            self._last_sync = now
        fatsecret_time = getattr(self.settings, "fatsecret_auto_import_time", "23:30")
        fatsecret_hour, fatsecret_minute = _parse_clock(fatsecret_time)
        if (
            self.run_fatsecret_sync is not None
            and self._last_fatsecret_sync != now.date()
            and (now.hour, now.minute) >= (fatsecret_hour, fatsecret_minute)
        ):
            await self._run_fatsecret_sync(now.date())
            self._last_fatsecret_sync = now.date()
        daily_hour, daily_minute = _parse_clock(self.settings.daily_report_time)
        if now.hour > daily_hour or (now.hour == daily_hour and now.minute >= daily_minute):
            target_day = now.date() - timedelta(days=1)
            if (
                self._last_daily != now.date()
                and self._report_retry_due("daily", target_day, now)
                and await self._run_scheduled_report("daily", target_day, now)
            ):
                self._last_daily = now.date()
        weekly_hour, weekly_minute = _parse_clock(self.settings.weekly_report_time)
        if now.weekday() == self.settings.weekly_report_weekday and (now.hour, now.minute) >= (weekly_hour, weekly_minute):
            target_day = now.date() - timedelta(days=1)
            if (
                self._last_weekly != now.date()
                and self._report_retry_due("weekly", target_day, now)
                and await self._run_scheduled_report("weekly", target_day, now)
            ):
                self._last_weekly = now.date()
        monthly_hour, monthly_minute = _parse_clock(self.settings.monthly_report_time)
        if now.day == 1 and (now.hour, now.minute) >= (monthly_hour, monthly_minute):
            target_day = now.date() - timedelta(days=1)
            if (
                self._last_monthly != now.date()
                and self._report_retry_due("monthly", target_day, now)
                and await self._run_scheduled_report("monthly", target_day, now)
            ):
                self._last_monthly = now.date()
        backup_hour, backup_minute = _parse_clock(self.settings.backup_time)
        if (now.hour, now.minute) >= (backup_hour, backup_minute) and self._last_backup != now.date():
            await self._run_exclusive(self.run_backup)
            self._last_backup = now.date()

    async def _run_exclusive(self, operation: Callable[[], Awaitable[None]]) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            try:
                await operation()
            except Exception:
                logger.exception("scheduled operation failed; continuing")

    def _report_retry_due(
        self, report_type: ReportType, target_day: date, now: datetime
    ) -> bool:
        retry_state = self._report_retry_state.get((report_type, target_day))
        return retry_state is None or now >= retry_state[1]

    async def _run_scheduled_report(
        self, report_type: ReportType, target_day: date, now: datetime
    ) -> bool:
        succeeded = False
        if await self._sync_for_report(report_type, target_day):
            succeeded = await self._run_report(report_type, target_day)
        retry_key = (report_type, target_day)
        if succeeded:
            self._report_retry_state.pop(retry_key, None)
            return True

        failures, _ = self._report_retry_state.get(retry_key, (0, now))
        failures += 1
        retry_minutes = min(5 * (2 ** (failures - 1)), 60)
        self._report_retry_state[retry_key] = (
            failures,
            now + timedelta(minutes=retry_minutes),
        )
        logger.warning(
            "scheduled report retry delayed type=%s period_end=%s failures=%s retry_in_minutes=%s",
            report_type,
            target_day,
            failures,
            retry_minutes,
        )
        return False

    async def _run_fatsecret_sync(self, day: date) -> None:
        if self._lock.locked() or self.run_fatsecret_sync is None:
            return
        async with self._lock:
            try:
                await self.run_fatsecret_sync(day)
                logger.info("scheduled FatSecret import attempt completed date=%s", day)
            except Exception:
                logger.exception("scheduled FatSecret import failed; continuing")

    async def _sync_for_report(self, report_type: ReportType, target_day: date) -> bool:
        if self._lock.locked():
            return False
        async with self._lock:
            try:
                if self.run_sync_range is not None:
                    start, end = _refresh_range(report_type, target_day)
                    summaries = await self.run_sync_range(start, end)
                    return bool(summaries) and all(
                        summary.status == "success" for summary in summaries
                    )
                summary = await self.run_sync(target_day)
                return summary is not None and summary.status == "success"
            except Exception:
                logger.exception("scheduled report sync failed; continuing")
                return False

    async def _run_report(self, report_type: ReportType, target_day: date) -> bool:
        if self._lock.locked():
            return False
        async with self._lock:
            try:
                result = await self.run_report(report_type, target_day)
                if self.notify_report is not None and result.telegram_sent_at is None:
                    await self.notify_report(result)
                    if result.report_id is not None and self.mark_report_notified is not None:
                        await self.mark_report_notified(result.report_id)
                elif result.telegram_sent_at is not None:
                    logger.info(
                        "scheduled report notification skipped type=%s period=%s..%s already_sent_at=%s",
                        report_type,
                        result.period.start,
                        result.period.end,
                        result.telegram_sent_at,
                    )
                return True
            except Exception:
                logger.exception("scheduled report failed; continuing")
                return False


class RuntimeServices:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.engine = create_engine_from_settings(settings)
        init_db(self.engine)

    def make_llm_runner(
        self,
        max_turns: int | None = None,
        operation: str = "claude",
        model: str | None = None,
    ) -> ClaudeCliRunner:
        report_model = getattr(
            self.settings, "claude_report_model", getattr(self.settings, "claude_model", "sonnet")
        )
        question_model = getattr(
            self.settings, "claude_question_model", getattr(self.settings, "claude_model", "sonnet")
        )
        is_report = operation == "report"
        selected_model = model or (report_model if is_report else question_model)
        prefix = "claude_report_" if selected_model == report_model else "claude_question_"
        return ClaudeCliRunner(
            selected_model,
            max_turns if max_turns is not None else self.settings.claude_max_turns,
            usage_recorder=self.record_llm_usage,
            operation=operation,
            input_price_per_million_usd=getattr(
                self.settings,
                f"{prefix}input_price_per_million_usd",
                getattr(self.settings, "claude_input_price_per_million_usd", 2.0),
            ),
            output_price_per_million_usd=getattr(
                self.settings,
                f"{prefix}output_price_per_million_usd",
                getattr(self.settings, "claude_output_price_per_million_usd", 10.0),
            ),
            cache_read_price_per_million_usd=getattr(
                self.settings,
                f"{prefix}cache_read_price_per_million_usd",
                getattr(self.settings, "claude_cache_read_price_per_million_usd", 0.20),
            ),
            cache_creation_price_per_million_usd=getattr(
                self.settings,
                f"{prefix}cache_creation_price_per_million_usd",
                getattr(self.settings, "claude_cache_creation_price_per_million_usd", 2.50),
            ),
        )

    def record_llm_usage(
        self, operation: str, model: str, usage: dict[str, object], success: bool
    ) -> None:
        from fitbit_report.db.models import LlmUsage

        with session_scope(self.engine) as session:
            session.add(
                LlmUsage(
                    operation=operation,
                    model=model,
                    input_tokens=int(usage.get("input_tokens", 0) or 0),
                    output_tokens=int(usage.get("output_tokens", 0) or 0),
                    cache_read_input_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
                    cache_creation_input_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
                    estimated_cost_usd=float(usage.get("estimated_cost_usd", 0.0) or 0.0),
                    estimated=bool(usage.get("estimated", False)),
                    status="success" if success else "error",
                    metadata_json=json.dumps(
                        {"estimated": bool(usage.get("estimated", False))},
                        ensure_ascii=False,
                    ),
                )
            )

    async def llm_usage_summary(self, start: datetime, end: datetime) -> dict[str, object]:
        return await run_in_thread(self._llm_usage_summary_sync, start, end)

    def _llm_usage_summary_sync(self, start: datetime, end: datetime) -> dict[str, object]:
        from sqlalchemy import Integer, func
        from fitbit_report.db.models import LlmUsage

        with session_scope(self.engine) as session:
            row = session.query(
                func.count(LlmUsage.id),
                func.coalesce(func.sum(LlmUsage.input_tokens), 0),
                func.coalesce(func.sum(LlmUsage.output_tokens), 0),
                func.coalesce(func.sum(LlmUsage.cache_read_input_tokens), 0),
                func.coalesce(func.sum(LlmUsage.cache_creation_input_tokens), 0),
                func.coalesce(func.sum(LlmUsage.estimated_cost_usd), 0.0),
                func.coalesce(func.sum(LlmUsage.estimated.cast(Integer)), 0),
            ).filter(
                LlmUsage.created_at >= start,
                LlmUsage.created_at < end,
            ).one()
        return {
            "calls": int(row[0] or 0),
            "input_tokens": int(row[1] or 0),
            "output_tokens": int(row[2] or 0),
            "cache_read_input_tokens": int(row[3] or 0),
            "cache_creation_input_tokens": int(row[4] or 0),
            "estimated_cost_usd": float(row[5] or 0.0),
            "estimated_calls": int(row[6] or 0),
        }

    async def sync(self, day: date | None = None) -> SyncSummary | None:
        # Google Health uses synchronous OAuth, HTTP and SQLite clients.  Keep
        # that work out of the Telegram event loop so the bot remains reactive
        # immediately after a restart.
        return await run_in_thread(self._sync_sync, day)

    def _sync_sync(self, day: date | None = None) -> SyncSummary | None:
        import httpx
        from fitbit_report.google_health.client import GoogleHealthClient
        from fitbit_report.google_health.oauth import GoogleHealthOAuth, GoogleHealthTokenStore
        from fitbit_report.google_health.sync import GoogleHealthSync

        token_store = GoogleHealthTokenStore(self.settings.google_health_token_path)
        credentials = token_store.load()
        if credentials is None:
            logger.warning("google health sync skipped: run google-health-auth first")
            return None
        oauth = GoogleHealthOAuth(self.settings, token_store=token_store)
        try:
            credentials = oauth.refresh_if_needed(credentials)
        except GoogleHealthAuthorizationRequired as exc:
            logger.warning("google health sync skipped: %s", exc)
            return None
        with httpx.Client(timeout=30) as http:
            client = GoogleHealthClient(
                http=http,
                credentials=credentials,
                token_store=token_store,
            )
            with session_scope(self.engine) as session:
                summary = GoogleHealthSync(client, self.settings.timezone).sync_day(
                    day or datetime.now(ZoneInfo(self.settings.timezone)).date(), session
                )
        logger.info(
            "google_health sync status=%s fetched=%s inserted=%s",
            summary.status,
            summary.fetched,
            summary.inserted,
        )
        return summary

    async def sync_range(self, start: date, end: date) -> list[SyncSummary]:
        return await run_in_thread(self._sync_range_sync, start, end)

    def _sync_range_sync(self, start: date, end: date) -> list[SyncSummary]:
        import httpx
        from fitbit_report.google_health.client import GoogleHealthClient
        from fitbit_report.google_health.oauth import GoogleHealthOAuth, GoogleHealthTokenStore
        from fitbit_report.google_health.sync import GoogleHealthSync

        if end < start:
            raise ValueError("sync range end must not be before start")
        token_store = GoogleHealthTokenStore(self.settings.google_health_token_path)
        credentials = token_store.load()
        if credentials is None:
            logger.warning("google health range sync skipped: run google-health-auth first")
            return []
        oauth = GoogleHealthOAuth(self.settings, token_store=token_store)
        try:
            credentials = oauth.refresh_if_needed(credentials)
        except GoogleHealthAuthorizationRequired as exc:
            logger.warning("google health range sync skipped: %s", exc)
            return []
        with httpx.Client(timeout=30) as http:
            client = GoogleHealthClient(
                http=http,
                credentials=credentials,
                token_store=token_store,
            )
            with session_scope(self.engine) as session:
                summaries = GoogleHealthSync(client, self.settings.timezone).sync_range(
                    start, end, session
                )
        logger.info(
            "google_health range sync status=%s start=%s end=%s days=%s fetched=%s inserted=%s",
            "success" if summaries and all(item.status == "success" for item in summaries) else "failed",
            start,
            end,
            len(summaries),
            sum(item.fetched for item in summaries),
            sum(item.inserted for item in summaries),
        )
        return summaries

    async def generate_report(self, report_type: ReportType, day: date | None = None) -> ReportResult:
        # Report generation invokes Claude CLI synchronously.  It can take a
        # few minutes, but must never pause polling Telegram updates.
        return await run_in_thread(self._generate_report_sync, report_type, day)

    def _generate_report_sync(self, report_type: ReportType, day: date | None = None) -> ReportResult:
        target_day = day or datetime.now(ZoneInfo(self.settings.timezone)).date()
        period = report_period(report_type, target_day)
        service = ReportService(
            self.make_llm_runner(operation="report")
        )
        if hasattr(service, "timezone_name"):
            service.timezone_name = self.settings.timezone
        if hasattr(service, "locale"):
            service.locale = getattr(self.settings, "app_locale", "ru")
        with session_scope(self.engine) as session:
            report = service.generate(session, report_type, period)
            if report.status != "success" or not report.draft_json:
                error = report.error_message or "Report generation failed"
                logger.error("report failed type=%s error=%s", report_type, error)
                raise ReportGenerationError(error)
            import json
            draft = json.loads(report.draft_json)
            context_payload = json.loads(report.context_json)
            report_meta = {
                "type": report_type,
                "period_start": report.period_start,
                "period_end": report.period_end,
                "model": report.model,
                "context_hash": report.context_hash,
            }
            locale = getattr(self.settings, "app_locale", "ru")
            markdown = render_markdown(
                report_meta, draft, self.settings.timezone, locale
            )
            telegram_before_chart, telegram_after_chart = render_telegram_parts(
                report_meta, draft, context_payload, locale
            )
            telegram_text = f"{telegram_before_chart}\n\n{telegram_after_chart}"
            report_id = getattr(report, "id", None)
            telegram_sent_at = getattr(report, "telegram_sent_at", None)
            claim_count = len(draft.get("claims", []))
            recommendation_count = len(draft.get("recommendations", []))
            feedback_indices = feedback_claim_indices(draft.get("claims", []))
            feedback_summaries = feedback_claim_summaries(
                draft.get("claims", []), locale
            )
        try:
            chart_paths = generate_report_charts(
                context_payload,
                self.settings.obsidian_vault / "assets",
                report_type,
                period,
                locale,
            )
        except Exception:
            logger.exception("report chart generation failed; continuing without charts")
            chart_paths = []
        telegram_rich_html = render_telegram_rich(
            report_meta,
            draft,
            context_payload,
            locale,
            include_chart=bool(chart_paths),
        )
        if chart_paths:
            relative = chart_paths[0].relative_to(self.settings.obsidian_vault).as_posix()
            chart_heading = "Visual overview" if locale == "en" else "Визуальный обзор"
            markdown += f"\n## {chart_heading}\n\n![[{relative.removesuffix('.png')}]]\n"
        path = write_report(self.settings.obsidian_vault, report_type, period, markdown)
        logger.info("report written type=%s path=%s", report_type, path)
        return ReportResult(
            report_type=report_type,
            period=period,
            path=path,
            markdown=markdown,
            telegram_text=telegram_text,
            report_id=report_id,
            telegram_sent_at=telegram_sent_at,
            chart_paths=tuple(chart_paths),
            claim_count=claim_count,
            recommendation_count=recommendation_count,
            feedback_claim_indices=feedback_indices,
            telegram_rich_html=telegram_rich_html,
            telegram_before_chart=telegram_before_chart,
            telegram_after_chart=telegram_after_chart,
            feedback_claim_summaries=feedback_summaries,
        )

    async def analyze_text_meal(self, event_id: int) -> None:
        await run_in_thread(self._analyze_text_meal_sync, event_id)

    async def record_meal_time(self, meal_type: str, occurred_at: datetime) -> int:
        return await run_in_thread(self._record_meal_time_sync, meal_type, occurred_at)

    def _record_meal_time_sync(self, meal_type: str, occurred_at: datetime) -> int:
        from fitbit_report.db.models import MealTimeLog
        from sqlalchemy.exc import OperationalError

        for attempt in range(3):
            try:
                with session_scope(self.engine) as session:
                    record = session.query(MealTimeLog).filter(
                        MealTimeLog.meal_date == occurred_at.date(),
                        MealTimeLog.meal_type == meal_type,
                    ).order_by(MealTimeLog.created_at.desc()).first()
                    if record is None:
                        record = MealTimeLog(
                            meal_date=occurred_at.date(),
                            meal_type=meal_type,
                            occurred_at=occurred_at,
                            source="telegram",
                        )
                        session.add(record)
                        session.flush()
                    else:
                        record.occurred_at = occurred_at
                    return record.id
            except OperationalError as exc:
                is_locked = "database is locked" in str(exc).casefold()
                if not is_locked or attempt == 2:
                    raise
                delay = 0.5 * (attempt + 1)
                logger.warning("meal time save delayed by SQLite lock; retrying in %.1fs", delay)
                time.sleep(delay)
        raise RuntimeError("meal time save retry loop ended unexpectedly")

    async def import_fatsecret_pdf(self, url: str) -> dict[str, object]:
        return await run_in_thread(self._import_fatsecret_pdf_sync, url)

    def _fatsecret_client(self):
        from fitbit_report.journal.fatsecret_oauth import FatSecretOAuthClient, FatSecretOAuthError

        consumer_key = (getattr(self.settings, "fatsecret_consumer_key", None) or "").strip()
        consumer_secret = (getattr(self.settings, "fatsecret_consumer_secret", None) or "").strip()
        if not consumer_key or not consumer_secret:
            raise FatSecretOAuthError(
                "В .env не заданы FATSECRET_CONSUMER_KEY и FATSECRET_CONSUMER_SECRET."
            )
        return FatSecretOAuthClient(consumer_key, consumer_secret)

    async def fatsecret_status(self) -> dict[str, object]:
        return await run_in_thread(self._fatsecret_status_sync)

    def _fatsecret_status_sync(self) -> dict[str, object]:
        from fitbit_report.db.models import FatSecretAuthorization

        configured = bool(
            (getattr(self.settings, "fatsecret_consumer_key", None) or "").strip()
            and (getattr(self.settings, "fatsecret_consumer_secret", None) or "").strip()
        )
        with session_scope(self.engine) as session:
            record = session.query(FatSecretAuthorization).filter(
                FatSecretAuthorization.singleton_key == "me"
            ).one_or_none()
            connected = bool(
                record
                and record.status == "connected"
                and record.access_token
                and record.access_token_secret
            )
        return {"configured": configured, "connected": connected}

    async def start_fatsecret_authorization(self) -> str:
        return await run_in_thread(self._start_fatsecret_authorization_sync)

    def _start_fatsecret_authorization_sync(self) -> str:
        from fitbit_report.db.models import FatSecretAuthorization

        with self._fatsecret_client() as client:
            authorization = client.start_authorization()
        with session_scope(self.engine) as session:
            record = session.query(FatSecretAuthorization).filter(
                FatSecretAuthorization.singleton_key == "me"
            ).one_or_none()
            if record is None:
                record = FatSecretAuthorization(singleton_key="me")
                session.add(record)
            record.status = "pending"
            record.request_token = authorization.request_token
            record.request_token_secret = authorization.request_token_secret
            record.access_token = None
            record.access_token_secret = None
            record.error_message = None
        return authorization.authorization_url

    async def complete_fatsecret_authorization(self, verifier: str) -> dict[str, object]:
        return await run_in_thread(self._complete_fatsecret_authorization_sync, verifier)

    def _complete_fatsecret_authorization_sync(self, verifier: str) -> dict[str, object]:
        from fitbit_report.db.models import FatSecretAuthorization
        from fitbit_report.journal.fatsecret_oauth import FatSecretOAuthError

        verifier = verifier.strip()
        if not verifier:
            raise FatSecretOAuthError("Код подтверждения не должен быть пустым.")
        with session_scope(self.engine) as session:
            record = session.query(FatSecretAuthorization).filter(
                FatSecretAuthorization.singleton_key == "me"
            ).one_or_none()
            if (
                record is None
                or record.status != "pending"
                or not record.request_token
                or not record.request_token_secret
            ):
                raise FatSecretOAuthError("Нет ожидающей привязки. Нажми «Подключить» ещё раз.")
            request_token = record.request_token
            request_token_secret = record.request_token_secret
        with self._fatsecret_client() as client:
            access = client.complete_authorization(
                request_token, request_token_secret, verifier
            )
        with session_scope(self.engine) as session:
            record = session.query(FatSecretAuthorization).filter(
                FatSecretAuthorization.singleton_key == "me"
            ).one()
            record.status = "connected"
            record.request_token = None
            record.request_token_secret = None
            record.access_token = access.token
            record.access_token_secret = access.secret
            record.error_message = None
        return {"status": "connected"}

    async def sync_fatsecret_foods(self, day: date | None = None) -> dict[str, object]:
        return await run_in_thread(self._sync_fatsecret_foods_sync, day)

    def _sync_fatsecret_foods_sync(self, day: date | None = None) -> dict[str, object]:
        from fitbit_report.db.models import FatSecretAuthorization
        from fitbit_report.journal.fatsecret import import_fatsecret_api_entries
        from fitbit_report.journal.fatsecret_oauth import FatSecretOAuthError

        target_day = day or datetime.now(ZoneInfo(self.settings.timezone)).date()
        with session_scope(self.engine) as session:
            record = session.query(FatSecretAuthorization).filter(
                FatSecretAuthorization.singleton_key == "me"
            ).one_or_none()
            if (
                record is None
                or record.status != "connected"
                or not record.access_token
                or not record.access_token_secret
            ):
                return {"status": "not_connected", "report_date": target_day}
            access_token = record.access_token
            access_token_secret = record.access_token_secret
        try:
            with self._fatsecret_client() as client:
                entries, raw_payload = client.fetch_food_diary(
                    target_day, access_token, access_token_secret
                )
        except FatSecretOAuthError:
            with session_scope(self.engine) as session:
                record = session.query(FatSecretAuthorization).filter(
                    FatSecretAuthorization.singleton_key == "me"
                ).one_or_none()
                if record is not None:
                    record.error_message = "Последний запрос к FatSecret не прошёл."
            raise
        summary = import_fatsecret_api_entries(
            target_day,
            entries,
            raw_payload,
            self.engine,
            session_scope,
        )
        return {
            "status": "success",
            "report_date": summary.report_date,
            "food_count": summary.food_count,
            "meal_count": summary.meal_count,
        }

    async def import_fatsecret_pdf_bytes(
        self,
        pdf_bytes: bytes,
        source_url: str = "",
    ) -> dict[str, object]:
        return await run_in_thread(
            self._import_fatsecret_pdf_bytes_sync,
            pdf_bytes,
            source_url,
        )

    def _import_fatsecret_pdf_sync(self, url: str) -> dict[str, object]:
        from fitbit_report.journal.fatsecret import import_fatsecret_url

        summary = import_fatsecret_url(
            url,
            self.engine,
            getattr(self.settings, "fatsecret_report_dir", Path("data/fatsecret-reports")),
            session_scope,
        )
        return {
            "report_date": summary.report_date,
            "food_count": summary.food_count,
            "meal_count": summary.meal_count,
            "pdf_path": summary.pdf_path,
        }

    def _import_fatsecret_pdf_bytes_sync(
        self,
        pdf_bytes: bytes,
        source_url: str,
    ) -> dict[str, object]:
        from fitbit_report.journal.fatsecret import import_fatsecret_pdf_bytes

        summary = import_fatsecret_pdf_bytes(
            pdf_bytes,
            source_url,
            self.engine,
            getattr(self.settings, "fatsecret_report_dir", Path("data/fatsecret-reports")),
            session_scope,
        )
        return {
            "report_date": summary.report_date,
            "food_count": summary.food_count,
            "meal_count": summary.meal_count,
            "pdf_path": summary.pdf_path,
        }

    async def analyze_training(
        self,
        occurred_at: datetime,
        text: str | None = None,
        photo_path: Path | None = None,
    ) -> int:
        return await run_in_thread(
            self._analyze_training_sync, occurred_at, text, photo_path
        )

    def _analyze_training_sync(
        self,
        occurred_at: datetime,
        text: str | None,
        photo_path: Path | None,
    ) -> int:
        from fitbit_report.journal.training import TrainingAnalysisService

        with session_scope(self.engine) as session:
            record = TrainingAnalysisService(
                self.make_llm_runner(
                    max_turns=max(2, self.settings.claude_max_turns), operation="training"
                ),
                locale=getattr(self.settings, "app_locale", "ru"),
            ).analyze(session, occurred_at, text=text, photo_path=photo_path)
            if record.status != "success":
                raise RuntimeError(record.error_message or "Training analysis failed")
            return record.id

    async def answer_question(
        self,
        question: str,
        image_paths: list[Path] | None = None,
        model: str | None = None,
    ) -> str:
        return await run_in_thread(
            self._answer_question_sync, question, image_paths or [], model
        )

    def _answer_question_sync(
        self,
        question: str,
        image_paths: list[Path],
        model: str | None = None,
    ) -> str:
        from fitbit_report.reports.context import build_report_context
        from fitbit_report.reports.llm_runner import ClaudeCliError

        today = datetime.now(ZoneInfo(self.settings.timezone)).date()
        period = DateRange(today - timedelta(days=27), today)
        locale = getattr(self.settings, "app_locale", "ru")
        with session_scope(self.engine) as session:
            context = build_report_context(
                session,
                "daily",
                period,
                self.settings.timezone,
                locale,
            )
            prompt = build_question_prompt(
                question,
                context.as_dict(),
                locale,
            )
        try:
            # Фото читаются Claude CLI как отдельный tool-вызов. При лимите в один
            # ход модель успевает только открыть файл и не может сформировать ответ.
            # Обычные вопросы остаются однопроходными, чтобы не расходовать лишние
            # лимиты подписки.
            base_turns = int(getattr(self.settings, "claude_max_turns", 1))
            question_turns = max(2, base_turns) if image_paths else base_turns
            return self.make_llm_runner(
                max_turns=question_turns,
                operation="question",
                model=model,
            ).generate_text(
                prompt,
                image_paths=image_paths,
            )
        except ClaudeCliError as exc:
            raise RuntimeError(str(exc)) from exc

    def _analyze_text_meal_sync(self, event_id: int) -> None:
        from fitbit_report.db.models import JournalEvent
        from fitbit_report.journal.food import FoodTextAnalyzer
        from fitbit_report.journal.meal_analysis import MealTextAnalysisService

        analyzer = FoodTextAnalyzer(
            self.make_llm_runner(max_turns=2, operation="food_text"),
            model=getattr(
                self.settings,
                "claude_question_model",
                getattr(self.settings, "claude_model", "sonnet"),
            ),
            locale=getattr(self.settings, "app_locale", "ru"),
        )
        with session_scope(self.engine) as session:
            event = session.get(JournalEvent, event_id)
            if event is not None and event.category == "meal":
                MealTextAnalysisService(analyzer).analyze_event(session, event)

    async def mark_report_notified(self, report_id: int) -> None:
        from fitbit_report.db.models import GeneratedReport

        with session_scope(self.engine) as session:
            report = session.get(GeneratedReport, report_id)
            if report is not None:
                report.telegram_sent_at = datetime.now(timezone.utc)

    async def backup(self) -> None:
        path = create_backup(self.settings, datetime.now(timezone.utc))
        logger.info("backup written path=%s", path)


async def run_application(settings: Settings) -> None:
    services = RuntimeServices(settings)
    application = build_application(settings, services)

    async def notify_report(result: ReportResult) -> None:
        await send_report(
            application.bot,
            settings.telegram_allowed_chat_id,
            result,
            getattr(settings, "app_locale", "ru"),
        )

    scheduler = InProcessScheduler(
        settings=settings,
        run_sync=services.sync,
        run_report=services.generate_report,
        run_backup=services.backup,
        notify_report=notify_report,
        run_sync_range=services.sync_range,
        mark_report_notified=services.mark_report_notified,
        run_fatsecret_sync=(
            services.sync_fatsecret_foods
            if (
                getattr(settings, "fatsecret_consumer_key", None)
                and getattr(settings, "fatsecret_consumer_secret", None)
            )
            else None
        ),
    )
    await application.initialize()
    await application.start()
    if application.updater is None:
        raise RuntimeError("Telegram updater is unavailable")
    await application.updater.start_polling()
    logger.info("application started; in-process scheduler is active")
    try:
        await scheduler.run_forever()
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


def main() -> None:
    from fitbit_report.logging_config import configure_logging
    settings = __import__("fitbit_report.config", fromlist=["load_settings"]).load_settings()
    configure_logging(settings)
    try:
        asyncio.run(run_application(settings))
    except KeyboardInterrupt:
        logger.info("application stopped")
