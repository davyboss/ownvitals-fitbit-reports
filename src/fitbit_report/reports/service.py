import hashlib
import json

from sqlalchemy.orm import Session

from fitbit_report.db.models import GeneratedReport
from fitbit_report.i18n import Locale
from fitbit_report.journal.food import FoodTextAnalyzer
from fitbit_report.journal.meal_analysis import MealTextAnalysisService
from fitbit_report.reports.context import build_report_context
from fitbit_report.reports.llm_runner import ClaudeCliRunner
from fitbit_report.reports.prompts import PROMPT_VERSION, build_prompt
from fitbit_report.types import DateRange, ReportType


class ReportService:
    def __init__(
        self,
        runner: ClaudeCliRunner,
        timezone_name: str = "Europe/Kiev",
        locale: Locale = "ru",
    ):
        self.runner = runner
        self.timezone_name = timezone_name
        self.locale = locale

    def generate(self, session: Session, report_type: ReportType, period: DateRange) -> GeneratedReport:
        MealTextAnalysisService(
            FoodTextAnalyzer(self.runner, locale=self.locale)
        ).analyze_period(
            session,
            period.start,
            period.end,
            self.timezone_name,
        )
        # Make any meal-analysis writes visible to the report context, then
        # release SQLite before building the prompt and waiting for Claude.
        session.commit()
        context = build_report_context(
            session,
            report_type,
            period,
            self.timezone_name,
            self.locale,
        )
        context_json = json.dumps(context.as_dict(), default=str, sort_keys=True, ensure_ascii=False)
        context_hash = hashlib.sha256(
            f"{self.locale}\n{context_json}".encode()
        ).hexdigest()
        existing = session.query(GeneratedReport).filter_by(
            report_type=report_type,
            period_start=period.start,
            period_end=period.end,
            context_hash=context_hash,
        ).one_or_none()
        if existing is not None and existing.status == "success" and existing.prompt_version == PROMPT_VERSION:
            return existing
        if existing is not None:
            existing.status = "running"
            existing.error_message = None
            existing.draft_json = None
            existing.prompt_version = PROMPT_VERSION
            existing.model = self.runner.model
            report = existing
        else:
            report = GeneratedReport(
                report_type=report_type,
                period_start=period.start,
                period_end=period.end,
                status="running",
                model=self.runner.model,
                prompt_version=PROMPT_VERSION,
                context_hash=context_hash,
                context_json=context_json,
            )
            session.add(report)
            # Do not flush before the Claude call.  A flush opens a SQLite
            # write transaction and would lock interactive journal writes for
            # the whole duration of a potentially multi-minute report.
        try:
            draft = self.runner.generate(build_prompt(context, self.locale))
            report.status = "success"
            report.draft_json = draft.model_dump_json()
        except Exception as exc:
            report.status = "failed"
            report.error_message = str(exc)
        # Persist the final state only after Claude has returned.  The caller
        # needs the generated id for Telegram feedback, but this write is now
        # short-lived rather than spanning the CLI request.
        session.flush()
        return report
