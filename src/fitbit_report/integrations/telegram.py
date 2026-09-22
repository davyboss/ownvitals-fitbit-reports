from __future__ import annotations

import html
import json
import logging
import re
import shlex
from io import BytesIO
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from fitbit_report.async_utils import run_in_thread
from fitbit_report.reports.archive import list_report_paths, read_report
from fitbit_report.journal.fatsecret import (
    MAX_FATSECRET_PDF_BYTES,
    FatSecretParseError,
)
from fitbit_report.journal.fatsecret_oauth import FatSecretOAuthError
from fitbit_report.i18n import Locale, translate
from fitbit_report.integrations.telegram_rich import RichMessageError, send_rich_report
from fitbit_report.private_storage import (
    ensure_private_directory,
    restrict_private_file,
    write_private_text,
)

logger = logging.getLogger(__name__)

MAIN_MENU_LABELS = translate("main_menu.labels", "ru")


def main_menu_labels(locale: Locale = "ru") -> tuple[str, ...]:
    return translate("main_menu.labels", locale)


class _LimitedBytesBuffer(BytesIO):
    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def write(self, value: bytes) -> int:
        if self.tell() + len(value) > self.limit:
            raise FatSecretParseError(
                "PDF FatSecret слишком большой. Максимальный размер — 10 МБ"
            )
        return super().write(value)


MORNING_CHECKIN_FIELDS = (
    ("energy", "Энергия"),
    ("sleep_quality", "Качество сна"),
    ("mood", "Настроение"),
    ("stress", "Стресс"),
)
EVENING_CHECKIN_FIELDS = (
    ("energy", "Энергия"),
    ("persistence", "Упорство"),
    ("quality", "Качество работы"),
    ("focus", "Фокус"),
    ("mood", "Настроение"),
    ("stress", "Стресс"),
)
CHECKIN_RATING_FIELDS = EVENING_CHECKIN_FIELDS
_FATSECRET_URL_RE = re.compile(r"https?://[^\s)\]>]+", re.IGNORECASE)
_MEAL_TIME_TYPES = {"breakfast", "lunch", "dinner", "snack", "other"}


def split_report_text(markdown: str, max_length: int = 3500) -> list[str]:
    if len(markdown) <= max_length:
        return [markdown]
    chunks: list[str] = []
    current = ""
    for paragraph in markdown.split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_length:
            current = candidate
            continue
        if current:
            chunks.append(current)
            current = ""
        while len(paragraph) > max_length:
            split_at = paragraph.rfind("\n", 0, max_length)
            if split_at < max_length // 2:
                split_at = paragraph.rfind(" ", 0, max_length)
            if split_at < max_length // 2:
                split_at = max_length
            chunks.append(paragraph[:split_at].rstrip())
            paragraph = paragraph[split_at:].lstrip()
        current = paragraph
    if current:
        chunks.append(current)
    return chunks or [""]


def save_question_answer(
    log_dir: Path,
    question: str,
    model: str,
    answer: str,
    locale: Locale = "ru",
) -> Path:
    """Keep the latest Claude answer available even if Telegram rejects delivery."""
    question_dir = Path(log_dir) / "questions"
    ensure_private_directory(question_dir)
    path = question_dir / "last-answer.md"
    labels = (
        ("Claude answer", "Model", "Question", "Answer")
        if locale == "en"
        else ("Ответ Claude", "Модель", "Вопрос", "Ответ")
    )
    write_private_text(
        path,
        f"# {labels[0]}\n\n{labels[1]}: {model}\n\n"
        f"{labels[2]}:\n\n{question}\n\n{labels[3]}:\n\n{answer}\n",
    )
    return path


def _feedback_markup(
    report_id: int | None,
    claim_indices: tuple[int, ...],
    selected: dict[tuple[str, int], str] | None = None,
    locale: Locale = "ru",
) -> InlineKeyboardMarkup | None:
    if report_id is None:
        return None
    selected = selected or {}
    rows = []
    for index in claim_indices:
        report_number = index + 1
        verdict = selected.get(("claim", index))
        yes_label = (
            translate("report.feedback.confirmed", locale, index=report_number)
            if verdict == "confirmed"
            else f"{report_number} · {translate('report.feedback.yes', locale)}"
        )
        no_label = (
            translate("report.feedback.rejected", locale, index=report_number)
            if verdict == "rejected"
            else f"{report_number} · {translate('report.feedback.no', locale)}"
        )
        rows.append([
            InlineKeyboardButton(yes_label, callback_data=f"feedback:claim:{report_id}:{index}:confirmed"),
            InlineKeyboardButton(no_label, callback_data=f"feedback:claim:{report_id}:{index}:rejected"),
        ])
    return InlineKeyboardMarkup(rows) if rows else None


def feedback_claim_indices(claims: object) -> tuple[int, ...]:
    """Ask only about uncertain interpretations, never about measured facts."""
    if not isinstance(claims, list):
        return ()
    indices = []
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        if claim.get("kind") not in {"association", "hypothesis"}:
            continue
        if claim.get("confidence") not in {"insufficient", "low", "medium"}:
            continue
        indices.append(index)
        if len(indices) == 2:
            break
    return tuple(indices)


def _feedback_summary(statement: str, kind: str, locale: Locale) -> str:
    """Keep a feedback prompt identifiable without repeating a full claim."""
    normalized = " ".join(statement.split())
    if kind == "hypothesis":
        marker = "Hypothesis:" if locale == "en" else "Гипотеза:"
        marker_position = normalized.lower().find(marker.lower())
        if marker_position >= 0:
            normalized = normalized[marker_position + len(marker):].strip()
    sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0]
    if len(sentence) <= 240:
        return sentence
    return sentence[:237].rstrip(" ,;:") + "..."


def feedback_claim_summaries(
    claims: object, locale: Locale = "ru"
) -> tuple[tuple[int, str], ...]:
    if not isinstance(claims, list):
        return ()
    summaries = []
    for index in feedback_claim_indices(claims):
        claim = claims[index]
        statement = str(claim.get("statement", "")).strip()
        if statement:
            summaries.append(
                (index, _feedback_summary(statement, str(claim.get("kind", "")), locale))
            )
    return tuple(summaries)


def report_feedback_markup(
    result, locale: Locale = "ru"
) -> InlineKeyboardMarkup | None:
    return _feedback_markup(
        result.report_id,
        getattr(result, "feedback_claim_indices", ()),
        locale=locale,
    )


def report_feedback_text(result, locale: Locale = "ru") -> str:
    lines = [
        f"<b>{translate('report.feedback_title', locale)}</b>",
        translate("report.feedback_prompt", locale),
    ]
    for index, summary in getattr(result, "feedback_claim_summaries", ()):
        lines.extend(["", f"<b>{index + 1}.</b> {html.escape(summary, quote=False)}"])
    return "\n".join(lines)


async def send_report(
    bot, chat_id: int, result, locale: Locale = "ru"
) -> None:
    label = translate(f"report.type.{result.report_type}", locale)

    async def deliver(name: str, operation) -> bool:
        try:
            await operation()
        except Exception:
            logger.exception("telegram report delivery failed part=%s", name)
            return False
        return True

    chart_paths = tuple(getattr(result, "chart_paths", ()))
    rich_html = getattr(result, "telegram_rich_html", None)
    token = getattr(bot, "token", None)
    rich_delivered = False
    if rich_html and token:
        try:
            await send_rich_report(
                token=token,
                chat_id=chat_id,
                rich_html=rich_html,
                chart_path=chart_paths[0] if chart_paths else None,
            )
            rich_delivered = True
        except RichMessageError as exc:
            logger.warning("telegram rich report failed; using fallback: %s", exc)

    async def send_charts() -> None:
        for chart_path in chart_paths:
            chart = Path(chart_path)

            async def send_chart(path=chart):
                with path.open("rb") as image:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=image,
                        caption=translate(
                            "report.chart_caption.daily"
                            if result.report_type == "daily"
                            else "report.chart_caption.period",
                            locale,
                        ),
                    )

            await deliver(f"chart:{chart.name}", send_chart)

    if rich_delivered:
        pass
    elif getattr(result, "telegram_before_chart", None) is not None:
        for index, chunk in enumerate(
            split_report_text(result.telegram_before_chart), start=1
        ):
            await deliver(
                f"intro:{index}",
                lambda chunk=chunk: bot.send_message(
                    chat_id=chat_id, text=chunk, parse_mode="HTML"
                ),
            )
        await send_charts()
        for index, chunk in enumerate(
            split_report_text(result.telegram_after_chart or ""), start=1
        ):
            await deliver(
                f"body:{index}",
                lambda chunk=chunk: bot.send_message(
                    chat_id=chat_id, text=chunk, parse_mode="HTML"
                ),
            )
    else:
        await deliver(
            "header",
            lambda: bot.send_message(
                chat_id=chat_id,
                text=translate(
                    "report.automatic_header",
                    locale,
                    report_type=label,
                    start=result.period.start,
                    end=result.period.end,
                ),
            ),
        )
        await send_charts()
        report_text = result.telegram_text or result.markdown
        for index, chunk in enumerate(split_report_text(report_text), start=1):
            await deliver(
                f"text:{index}",
                lambda chunk=chunk: bot.send_message(
                    chat_id=chat_id, text=chunk, parse_mode="HTML"
                ),
            )

    # Feedback remains a separate interactive message for both delivery paths.
    feedback_markup = report_feedback_markup(result, locale)
    if feedback_markup is not None:
        await deliver(
            "feedback",
            lambda: bot.send_message(
                chat_id=chat_id,
                text=report_feedback_text(result, locale),
                parse_mode="HTML",
                reply_markup=feedback_markup,
            ),
        )


def main_menu_markup(locale: Locale = "ru") -> ReplyKeyboardMarkup:
    labels = main_menu_labels(locale)
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(labels[0]), KeyboardButton(labels[1])],
            [KeyboardButton(labels[2]), KeyboardButton(labels[3])],
            [KeyboardButton(labels[4])],
        ], resize_keyboard=True, is_persistent=True
    )


def more_menu_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.my_entries", locale), callback_data="more:entries")],
        [
            InlineKeyboardButton(translate("button.sync", locale), callback_data="more:sync"),
            InlineKeyboardButton(translate("button.usage", locale), callback_data="more:usage"),
        ],
        [
            InlineKeyboardButton(translate("button.status", locale), callback_data="more:status"),
            InlineKeyboardButton(translate("button.help", locale), callback_data="more:help"),
        ],
    ])


def entries_actions_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.edit_entries", locale), callback_data="more:edit_entries")],
        [InlineKeyboardButton(translate("button.more", locale), callback_data="nav:more")],
    ])


def journal_menu_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.add_food", locale), callback_data="journal:add_food")],
        [InlineKeyboardButton(translate("button.meal_time", locale), callback_data="journal:meal_time"), InlineKeyboardButton(translate("button.caffeine", locale), callback_data="journal:caffeine")],
        [InlineKeyboardButton(translate("button.nicotine", locale), callback_data="journal:nicotine")],
        [InlineKeyboardButton(translate("button.workout", locale), callback_data="journal:training"), InlineKeyboardButton(translate("button.alcohol", locale), callback_data="journal:alcohol")],
        [InlineKeyboardButton(translate("button.mood", locale), callback_data="journal:mood"), InlineKeyboardButton(translate("button.stress", locale), callback_data="journal:stress")],
        [InlineKeyboardButton(translate("button.note", locale), callback_data="journal:note"), InlineKeyboardButton(translate("button.illness", locale), callback_data="journal:illness")],
        [InlineKeyboardButton(translate("button.private_event", locale), callback_data="journal:masturbation")],
        [InlineKeyboardButton(translate("button.main_menu", locale), callback_data="nav:main")],
    ])


def food_step_markup(step: str, locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.skip", locale), callback_data=f"food-draft:skip:{step}")],
        [InlineKeyboardButton(translate("button.cancel", locale), callback_data="food-draft:cancel")],
    ])


def meal_type_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.breakfast", locale), callback_data="journal:meal:breakfast"), InlineKeyboardButton(translate("button.lunch", locale), callback_data="journal:meal:lunch")],
        [InlineKeyboardButton(translate("button.dinner", locale), callback_data="journal:meal:dinner"), InlineKeyboardButton(translate("button.snack", locale), callback_data="journal:meal:snack")],
        [InlineKeyboardButton(translate("button.other", locale), callback_data="journal:meal:other")],
        [InlineKeyboardButton(translate("button.cancel", locale), callback_data="nav:main")],
    ])


def food_meal_type_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.breakfast", locale), callback_data="food:meal:breakfast"), InlineKeyboardButton(translate("button.lunch", locale), callback_data="food:meal:lunch")],
        [InlineKeyboardButton(translate("button.dinner", locale), callback_data="food:meal:dinner"), InlineKeyboardButton(translate("button.snack", locale), callback_data="food:meal:snack")],
        [InlineKeyboardButton(translate("button.other", locale), callback_data="food:meal:other")],
        [InlineKeyboardButton(translate("button.cancel", locale), callback_data="food-time:cancel")],
    ])


def food_time_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.now", locale), callback_data="food-time:now"), InlineKeyboardButton(translate("button.custom_time", locale), callback_data="food-time:custom")],
        [InlineKeyboardButton(translate("button.cancel", locale), callback_data="food-time:cancel")],
    ])


def food_confirmation_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.correct", locale), callback_data="food:confirm")],
        [InlineKeyboardButton(translate("button.edit", locale), callback_data="food:edit"), InlineKeyboardButton(translate("button.cancel", locale), callback_data="food:cancel")],
    ])


def nicotine_menu_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.snus", locale), callback_data="journal:nicotine:snus"), InlineKeyboardButton(translate("button.cigarettes", locale), callback_data="journal:nicotine:cigarette")],
        [InlineKeyboardButton(translate("button.vape", locale), callback_data="journal:nicotine:vape")],
        [InlineKeyboardButton(translate("button.cancel", locale), callback_data="nav:main")],
    ])


def journal_time_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.now", locale), callback_data="journal-time:now"), InlineKeyboardButton(translate("button.custom_time", locale), callback_data="journal-time:custom")],
        [InlineKeyboardButton(translate("button.cancel", locale), callback_data="journal-time:cancel")],
    ])


def archive_menu_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.daily_reports", locale), callback_data="archive:list:daily")],
        [InlineKeyboardButton(translate("button.weekly_reports", locale), callback_data="archive:list:weekly")],
        [InlineKeyboardButton(translate("button.monthly_reports", locale), callback_data="archive:list:monthly")],
        [InlineKeyboardButton(translate("button.main_menu", locale), callback_data="nav:main")],
    ])


def meal_time_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.now", locale), callback_data="meal-time:now"), InlineKeyboardButton(translate("button.custom_time", locale), callback_data="meal-time:custom")],
        [InlineKeyboardButton(translate("button.cancel", locale), callback_data="meal-time:cancel")],
    ])


def fatsecret_markup(connected: bool, locale: Locale = "ru") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            translate("button.import_today", locale) if connected else translate("button.connect_account", locale),
            callback_data="fatsecret:sync" if connected else "fatsecret:connect",
        )]
    ]
    if connected:
        rows.append([InlineKeyboardButton(translate("button.reconnect", locale), callback_data="fatsecret:connect")])
    rows.append([InlineKeyboardButton(translate("button.journal", locale), callback_data="nav:journal")])
    return InlineKeyboardMarkup(rows)


def question_model_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(translate("button.sonnet", locale), callback_data="question:model:sonnet"),
            InlineKeyboardButton(translate("button.opus", locale), callback_data="question:model:opus"),
        ],
        [InlineKeyboardButton(translate("button.cancel", locale), callback_data="nav:main")],
    ])


def edit_entries_markup(events, locale: Locale = "ru") -> InlineKeyboardMarkup:
    rows = []
    for event in events:
        label = f"#{event.id} {event.category} · {event.occurred_at:%d.%m %H:%M}"
        rows.append([
            InlineKeyboardButton(label, callback_data=f"entry:edit:{event.id}"),
            InlineKeyboardButton(translate("button.delete", locale), callback_data=f"entry:delete:{event.id}"),
        ])
    rows.append([InlineKeyboardButton(translate("button.more", locale), callback_data="nav:more")])
    return InlineKeyboardMarkup(rows)


def archive_period_markup(report_type: str, names: list[str], locale: Locale = "ru") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(name, callback_data=f"archive:view:{report_type}:{index}")] for index, name in enumerate(names)]
    rows.append([InlineKeyboardButton(translate("button.archive", locale), callback_data="nav:archive")])
    return InlineKeyboardMarkup(rows)


def checkin_period_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(translate("button.morning", locale), callback_data="checkin:morning"), InlineKeyboardButton(translate("button.evening", locale), callback_data="checkin:evening")],
        [InlineKeyboardButton(translate("button.main_menu", locale), callback_data="nav:main")],
    ])


def rating_markup(field: str, locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(v), callback_data=f"checkin:set:{field}:{v}") for v in range(1, 6)],
        [InlineKeyboardButton(str(v), callback_data=f"checkin:set:{field}:{v}") for v in range(6, 11)],
        [InlineKeyboardButton(translate("button.skip", locale), callback_data=f"checkin:skip:{field}")],
    ])


def skip_markup(field: str, locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(translate("button.skip", locale), callback_data=f"checkin:skip:{field}")]])


def sync_confirm_markup(locale: Locale = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(translate("button.sync_start", locale), callback_data="sync:confirm"),
        InlineKeyboardButton(translate("button.cancel", locale), callback_data="sync:cancel"),
    ]])


def help_text(locale: Locale = "ru") -> str:
    return translate("help", locale)


def start_text(locale: Locale = "ru") -> str:
    return translate("start", locale)


def status_text(settings, locale: Locale = "ru") -> str:
    return translate(
        "status",
        locale,
        database_url=settings.database_url,
        obsidian_vault=settings.obsidian_vault,
        timezone=settings.timezone,
    )


def usage_text(
    summary: dict[str, object],
    start: datetime,
    end: datetime,
    locale: Locale = "ru",
) -> str:
    return translate(
        "usage",
        locale,
        start=f"{start:%Y-%m-%d}",
        end=f"{end:%Y-%m-%d}",
        calls=int(summary.get("calls", 0)),
        input_tokens=int(summary.get("input_tokens", 0)),
        output_tokens=int(summary.get("output_tokens", 0)),
        cache_read_tokens=int(summary.get("cache_read_input_tokens", 0)),
        estimated_cost=float(summary.get("estimated_cost_usd", 0.0)),
        estimated_calls=int(summary.get("estimated_calls", 0)),
    )


def is_allowed_chat(chat_id: int | None, allowed_chat_id: int) -> bool:
    return chat_id is not None and chat_id == allowed_chat_id


def _clear_flow(context) -> None:
    for key in (
        "flow",
        "journal",
        "checkin",
        "food",
        "meal_time_type",
        "ask_question",
        "ask_image_paths",
        "ask_photo_path",
        "fatsecret_verifier",
    ):
        context.user_data.pop(key, None)


def _extract_fatsecret_url(text: str) -> str | None:
    for candidate in _FATSECRET_URL_RE.findall(text):
        if (
            "fatsecret.com/export/" in candidate.casefold()
            and candidate.casefold().split("?", 1)[0].endswith(".pdf")
        ):
            return candidate.rstrip(".,")
    return None


def _set_checkin_flow(context, flow: str) -> None:
    context.user_data["flow"] = flow


def _journal_command_from_amount(journal: dict, amount: str) -> str:
    if journal["category"] == "nicotine":
        return f"/log nicotine {journal['subtype']} {amount}"
    return f"/log {journal['category']} {amount}"


def _meal_command(meal_type: str, description: str) -> str:
    return f"/log meal {meal_type} {description}"


def _checkin_command(checkin: dict) -> str:
    values = checkin["values"]
    pairs = []
    for key, value in values.items():
        if value is None:
            continue
        rendered = shlex.quote(str(value)) if isinstance(value, str) else str(value)
        pairs.append(f"{key}={rendered}")
    return f"/checkin {checkin['period']} {' '.join(pairs)}".strip()


def checkin_rating_fields(period: str) -> tuple[tuple[str, str], ...]:
    return MORNING_CHECKIN_FIELDS if period == "morning" else EVENING_CHECKIN_FIELDS


def _next_rating_field(values: dict, period: str = "evening") -> tuple[str, str] | None:
    for key, label in checkin_rating_fields(period):
        if key not in values:
            return key, label
    return None


def _record_journal(command: str, settings, services):
    from fitbit_report.db.session import session_scope
    from fitbit_report.journal.parser import parse_log_command
    from fitbit_report.journal.service import JournalService

    zone = ZoneInfo(settings.timezone)
    event = parse_log_command(command, datetime.now(zone), zone)
    with session_scope(services.engine) as session:
        saved_event = JournalService().record(event, session)
        session.flush()
        session.expunge(saved_event)
        return saved_event


def _record_checkin(command: str, settings, services) -> None:
    from fitbit_report.db.session import session_scope
    from fitbit_report.journal.parser import parse_checkin_command
    from fitbit_report.productivity.service import ProductivityService

    zone = ZoneInfo(settings.timezone)
    checkin = parse_checkin_command(command, datetime.now(zone), zone)
    with session_scope(services.engine) as session:
            ProductivityService().record(checkin, session)


def _format_journal_event(event, zone: ZoneInfo, locale: Locale = "ru") -> str:
    details = event.note or ""
    if event.quantity is not None:
        details = f"{event.quantity:g}{event.unit or ''} " + details
    if event.duration_min is not None:
        unit = "min" if locale == "en" else "мин"
        details = f"{event.duration_min} {unit} " + details
    return f"#{event.id} {event.occurred_at.astimezone(zone):%d.%m %H:%M} · {event.category}/{event.subtype or ''} {details}".strip()


def _persist_food_analysis(state: dict, occurred_at: datetime, analysis, services, correction: str | None = None) -> int:
    from fitbit_report.db.models import MealPhotoAnalysis
    from fitbit_report.db.session import session_scope

    with session_scope(services.engine) as session:
        record = None
        if state.get("analysis_id") is not None:
            record = session.get(MealPhotoAnalysis, state["analysis_id"])
        if record is None:
            record = MealPhotoAnalysis(
                occurred_at=occurred_at,
                meal_type=state["meal_type"],
                photo_path=state["photo_path"],
                analysis_json="{}",
            )
            session.add(record)
        record.occurred_at = occurred_at
        record.meal_type = state["meal_type"]
        record.analysis_json = json.dumps(analysis.model_dump(), ensure_ascii=False)
        record.confirmed_json = None
        record.status = "pending"
        record.correction_text = correction
        session.flush()
        return record.id


def _confirm_food_analysis(analysis_id: int, services) -> None:
    from fitbit_report.db.models import MealPhotoAnalysis
    from fitbit_report.db.session import session_scope

    with session_scope(services.engine) as session:
        record = session.get(MealPhotoAnalysis, analysis_id)
        if record is None:
            raise ValueError("Meal photo analysis was not found")
        record.confirmed_json = record.analysis_json
        record.status = "confirmed"


def _cancel_food_analysis(analysis_id: int, services) -> None:
    from fitbit_report.db.models import MealPhotoAnalysis
    from fitbit_report.db.session import session_scope

    with session_scope(services.engine) as session:
        record = session.get(MealPhotoAnalysis, analysis_id)
        if record is not None:
            record.status = "cancelled"


def _persist_text_food_analysis(state: dict, services) -> int:
    from fitbit_report.db.models import JournalEvent, MealTextAnalysis
    from fitbit_report.db.session import session_scope

    occurred_at = datetime.fromisoformat(state["occurred_at"])
    description = state.get("description")
    exact_details = state.get("exact_details")
    note = ". ".join(item for item in (description, exact_details) if item) or "Meal"
    original_text = (
        f"/log meal {state['meal_type']} {note} at {occurred_at:%H:%M}"
    )
    with session_scope(services.engine) as session:
        event = JournalEvent(
            category="meal",
            subtype=state["meal_type"],
            occurred_at=occurred_at,
            quantity=None,
            unit=None,
            dose=None,
            dose_unit=None,
            duration_min=None,
            intensity=None,
            note=note,
            original_text=original_text,
        )
        session.add(event)
        session.flush()
        session.add(MealTextAnalysis(
            journal_event_id=event.id,
            analysis_json=json.dumps(state["analysis"], ensure_ascii=False),
            status="success",
            model="telegram-food-draft",
        ))
        return event.id


def build_application(settings, services):
    from telegram.ext import Application
    from fitbit_report.journal.food import (
        FoodPhotoAnalyzer,
        FoodTextAnalyzer,
        format_food_analysis,
    )

    application = Application.builder().token(settings.telegram_bot_token).build()
    locale: Locale = getattr(settings, "app_locale", "ru")
    menu_labels = main_menu_labels(locale)
    food_runner = (
        services.make_llm_runner(max_turns=2, operation="food_photo")
        if hasattr(services, "make_llm_runner")
        else None
    )
    food_analyzer = FoodPhotoAnalyzer(
        runner=food_runner,
        model=getattr(
            settings,
            "claude_question_model",
            getattr(settings, "claude_model", "sonnet"),
        ),
        locale=locale,
    )
    food_text_runner = (
        services.make_llm_runner(max_turns=2, operation="food_text")
        if hasattr(services, "make_llm_runner")
        else None
    )
    food_text_analyzer = FoodTextAnalyzer(
        runner=food_text_runner,
        model=getattr(
            settings,
            "claude_question_model",
            getattr(settings, "claude_model", "sonnet"),
        ),
        locale=locale,
    )

    async def start(update, context):
        if is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            await update.effective_message.reply_text(
                start_text(locale),
                reply_markup=main_menu_markup(locale),
            )

    async def help_command(update, context):
        if is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            await update.effective_message.reply_text(
                help_text(locale),
                reply_markup=main_menu_markup(locale),
            )

    async def status_command(update, context):
        if is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            await update.effective_message.reply_text(
                status_text(settings, locale),
                reply_markup=main_menu_markup(locale),
            )

    async def usage_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        if not hasattr(services, "llm_usage_summary"):
            await update.effective_message.reply_text(
                translate("usage.unavailable", locale),
                reply_markup=main_menu_markup(locale),
            )
            return
        now = datetime.now(timezone.utc)
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end = start.replace(year=now.year + 1, month=1)
        else:
            end = start.replace(month=now.month + 1)
        summary = await services.llm_usage_summary(start, end)
        await update.effective_message.reply_text(
            usage_text(summary, start, end, locale),
            reply_markup=main_menu_markup(locale),
        )

    async def answer_question_with_photos(
        message,
        question: str,
        image_paths: list[Path],
        model: str,
    ):
        await message.reply_text(translate("question.analyzing_photos", locale))
        try:
            answer = await services.answer_question(
                question,
                image_paths=image_paths,
                model=model,
            )
        except Exception as exc:
            logger.exception("telegram health question with photos failed")
            if "empty response" in str(exc).casefold():
                text = (
                    translate("question.empty_response", locale)
                )
            else:
                text = translate("question.failed", locale)
            await message.reply_text(text)
        else:
            try:
                answer_path = save_question_answer(
                    settings.log_dir,
                    question,
                    model,
                    answer,
                    locale,
                )
                logger.info(
                    "telegram question answer saved path=%s model=%s chars=%s",
                    answer_path,
                    model,
                    len(answer),
                )
            except OSError:
                logger.exception("telegram question answer could not be saved")

            chunks = split_report_text(answer)
            for index, chunk in enumerate(chunks, start=1):
                await message.reply_text(chunk)

    async def ask_model_choice(
        message,
        context,
        question: str,
        image_paths: list[Path] | None = None,
    ):
        context.user_data["ask_question"] = question
        context.user_data["ask_image_paths"] = [str(path) for path in (image_paths or [])]
        context.user_data["flow"] = "ask_model_choice"
        await message.reply_text(
            translate("question.model_prompt", locale),
            reply_markup=question_model_markup(locale),
        )

    async def ask_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        question = " ".join(context.args).strip()
        if not question:
            context.user_data["flow"] = "ask_waiting"
            await update.effective_message.reply_text(
                translate("question.input_prompt", locale)
            )
            return
        await ask_model_choice(update.effective_message, context, question)

    async def training_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        text = " ".join(context.args).strip()
        if not text:
            context.user_data["flow"] = "training_input"
            await update.effective_message.reply_text(
                translate("training.input_prompt", locale)
            )
            return
        await update.effective_message.reply_text(
            translate("training.analyzing", locale)
        )
        try:
            zone = ZoneInfo(settings.timezone)
            await services.analyze_training(datetime.now(zone), text=text)
        except Exception:
            logger.exception("telegram text training analysis failed")
            await update.effective_message.reply_text(
                translate("training.failed", locale)
            )
        else:
            await update.effective_message.reply_text(
                translate("training.saved", locale),
                reply_markup=main_menu_markup(locale),
            )

    async def save_meal_time(message, meal_type: str, time_text: str):
        if (
            meal_type not in _MEAL_TIME_TYPES
            or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_text)
        ):
            await message.reply_text(
                translate("meal_time.command_format", locale)
            )
            return
        zone = ZoneInfo(settings.timezone)
        occurred_at = datetime.combine(
            datetime.now(zone).date(), time.fromisoformat(time_text), tzinfo=zone
        )
        try:
            await services.record_meal_time(meal_type, occurred_at)
        except Exception as exc:
            logger.exception("telegram meal time save failed")
            if "database is locked" in str(exc).casefold():
                text = translate("meal_time.db_busy", locale)
            else:
                text = translate("meal_time.save_failed", locale)
            await message.reply_text(text)
        else:
            await message.reply_text(
                translate(
                    "meal_time.saved",
                    locale,
                    meal_type=meal_type,
                    time=time_text,
                ),
                reply_markup=main_menu_markup(locale),
            )

    async def mealtime_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        if len(context.args) == 2:
            await save_meal_time(
                update.effective_message,
                context.args[0].lower(),
                context.args[1],
            )
            return
        context.user_data["flow"] = "meal_time_command"
        await update.effective_message.reply_text(
            translate("meal_time.input_prompt", locale)
        )

    async def import_fatsecret_message(message, url: str):
        await message.reply_text(translate("fatsecret.loading_pdf", locale))
        try:
            summary = await services.import_fatsecret_pdf(url)
        except FatSecretParseError as exc:
            logger.warning("telegram FatSecret PDF import rejected: %s", exc)
            await message.reply_text(
                translate("fatsecret.parse_failed", locale, error=exc)
            )
        except Exception:
            logger.exception("telegram FatSecret PDF import failed")
            await message.reply_text(translate("fatsecret.url_failed", locale))
        else:
            await message.reply_text(
                translate(
                    "fatsecret.imported",
                    locale,
                    date=summary["report_date"],
                    food_count=summary["food_count"],
                    meal_count=summary["meal_count"],
                ),
                reply_markup=main_menu_markup(locale),
            )

    async def import_fatsecret_document_message(update, context):
        if not is_allowed_chat(
            update.effective_chat.id,
            settings.telegram_allowed_chat_id,
        ):
            return
        message = update.effective_message
        document = message.document
        file_name = (document.file_name or "").casefold()
        mime_type = (document.mime_type or "").casefold()
        if mime_type != "application/pdf" and not file_name.endswith(".pdf"):
            return
        if document.file_size is not None and document.file_size > MAX_FATSECRET_PDF_BYTES:
            await message.reply_text(translate("fatsecret.pdf_too_large", locale))
            return

        await message.reply_text(translate("fatsecret.loading_pdf", locale))
        source_url = _extract_fatsecret_url(message.caption or "")
        if source_url is None:
            source_url = f"telegram://fatsecret/{document.file_unique_id}"
        try:
            telegram_file = await context.bot.get_file(document.file_id)
            pdf_buffer = _LimitedBytesBuffer(MAX_FATSECRET_PDF_BYTES)
            await telegram_file.download_to_memory(pdf_buffer)
            summary = await services.import_fatsecret_pdf_bytes(
                pdf_buffer.getvalue(),
                source_url,
            )
        except FatSecretParseError as exc:
            logger.warning("telegram FatSecret PDF document rejected: %s", exc)
            await message.reply_text(
                translate("fatsecret.parse_failed", locale, error=exc)
            )
        except Exception:
            logger.exception("telegram FatSecret PDF document import failed")
            await message.reply_text(translate("fatsecret.document_failed", locale))
        else:
            await message.reply_text(
                translate(
                    "fatsecret.imported",
                    locale,
                    date=summary["report_date"],
                    food_count=summary["food_count"],
                    meal_count=summary["meal_count"],
                ),
                reply_markup=main_menu_markup(locale),
            )

    async def entries_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        from sqlalchemy import select
        from fitbit_report.db.models import MealPhotoAnalysis
        from fitbit_report.db.session import session_scope
        from fitbit_report.journal.service import JournalService
        zone = ZoneInfo(settings.timezone)
        with session_scope(services.engine) as session:
            events = JournalService().recent(session, 15)
            photo_meals = list(session.scalars(
                select(MealPhotoAnalysis)
                .where(MealPhotoAnalysis.status.in_(["confirmed", "pending"]))
                .order_by(MealPhotoAnalysis.occurred_at.desc())
                .limit(15)
            ))
            records = [
                (event.occurred_at, _format_journal_event(event, zone, locale))
                for event in events
            ]
            for meal in photo_meals:
                try:
                    analysis = json.loads(meal.confirmed_json or meal.analysis_json or "{}")
                except json.JSONDecodeError:
                    analysis = {}
                calories = ""
                minimum = analysis.get("total_calories_min")
                maximum = analysis.get("total_calories_max")
                if minimum is not None or maximum is not None:
                    calorie_unit = "kcal" if locale == "en" else "ккал"
                    calories = f" · {minimum or '?'}–{maximum or '?'} {calorie_unit}"
                summary = analysis.get("summary") or translate("journal.photo_estimate", locale)
                status = (
                    f" · {translate('journal.pending', locale)}"
                    if meal.status == "pending"
                    else ""
                )
                records.append((meal.occurred_at, f"#{meal.id} {meal.occurred_at.astimezone(zone):%d.%m %H:%M} · 📸 {meal.meal_type}: {summary}{calories}{status}"))
            records.sort(key=lambda item: item[0], reverse=True)
            text = "\n".join(item[1] for item in records[:15])
        await update.effective_message.reply_text(
            (
                translate("journal.entries_header", locale, entries=text)
                if text
                else translate("journal.entries_empty", locale)
            )
            + "\n\n"
            + translate("journal.entries_help", locale),
            reply_markup=entries_actions_markup(locale),
        )

    async def edit_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        if not context.args:
            await update.effective_message.reply_text(
                translate("journal.edit_format", locale)
            )
            return
        try:
            event_id = int(context.args[0])
            values = {}
            for token in context.args[1:]:
                key, value = token.split("=", 1)
                if key == "at":
                    zone = ZoneInfo(settings.timezone)
                    value = datetime.combine(datetime.now(zone).date(), time.fromisoformat(value), tzinfo=zone)
                elif key in {"quantity", "dose", "intensity"}:
                    value = float(value)
                elif key in {"duration_min"}:
                    value = int(value)
                values[key] = value
            from fitbit_report.db.session import session_scope
            from fitbit_report.journal.service import JournalService
            with session_scope(services.engine) as session:
                event = JournalService().update(event_id, values, session)
                rendered = _format_journal_event(
                    event, ZoneInfo(settings.timezone), locale
                )
            await update.effective_message.reply_text(
                translate("journal.edited", locale, entry=rendered)
            )
        except Exception:
            logger.exception("telegram journal edit failed")
            await update.effective_message.reply_text(
                translate("journal.edit_failed", locale)
            )

    async def delete_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        try:
            event_id = int(context.args[0])
            from fitbit_report.db.session import session_scope
            from fitbit_report.journal.service import JournalService
            with session_scope(services.engine) as session:
                JournalService().delete(event_id, session)
            await update.effective_message.reply_text(
                translate("journal.deleted", locale, entry_id=event_id)
            )
        except Exception:
            logger.exception("telegram journal delete failed")
            await update.effective_message.reply_text(
                translate("journal.delete_failed", locale)
            )

    async def edit_checkin_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        try:
            from fitbit_report.db.models import ProductivityCheckin
            from fitbit_report.db.session import session_scope
            if len(context.args) < 2:
                raise ValueError
            checkin_id = int(context.args[0])
            with session_scope(services.engine) as session:
                checkin = session.get(ProductivityCheckin, checkin_id)
                if checkin is None:
                    raise ValueError
                for token in context.args[1:]:
                    key, value = token.split("=", 1)
                    if key not in {"energy", "sleep_quality", "persistence", "work_quality", "focus", "mood", "stress", "deep_work_min", "priority", "note"}:
                        raise ValueError
                    setattr(checkin, key, int(value) if key not in {"priority", "note"} else value)
            await update.effective_message.reply_text(
                translate("checkin.edited", locale)
            )
        except Exception:
            logger.exception("telegram checkin edit failed")
            await update.effective_message.reply_text(
                translate("checkin.edit_format", locale)
            )

    async def delete_checkin_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        try:
            from fitbit_report.db.models import ProductivityCheckin
            from fitbit_report.db.session import session_scope
            checkin_id = int(context.args[0])
            with session_scope(services.engine) as session:
                checkin = session.get(ProductivityCheckin, checkin_id)
                if checkin is None:
                    raise ValueError
                session.delete(checkin)
            await update.effective_message.reply_text(
                translate("checkin.deleted", locale, checkin_id=checkin_id)
            )
        except Exception:
            await update.effective_message.reply_text(
                translate("checkin.delete_format", locale)
            )

    async def show_edit_entries(update, context):
        from fitbit_report.db.session import session_scope
        from fitbit_report.journal.service import JournalService
        with session_scope(services.engine) as session:
            events = JournalService().recent(session, 15)
            session.expunge_all()
        await update.effective_message.reply_text(
            translate("journal.choose_entry", locale),
            reply_markup=edit_entries_markup(events, locale),
        )

    async def log_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        try:
            event = _record_journal(update.effective_message.text, settings, services)
            if event.category == "meal" and hasattr(services, "analyze_text_meal"):
                await services.analyze_text_meal(event.id)
            await update.effective_message.reply_text(
                translate("common.saved", locale),
                reply_markup=main_menu_markup(locale),
            )
        except Exception:
            logger.exception("telegram journal command failed")
            await update.effective_message.reply_text(
                translate("journal.command_failed", locale)
            )

    async def checkin_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        try:
            _record_checkin(update.effective_message.text, settings, services)
            await update.effective_message.reply_text(
                translate("checkin.saved", locale),
                reply_markup=main_menu_markup(locale),
            )
        except Exception:
            logger.exception("telegram checkin command failed")
            await update.effective_message.reply_text(
                translate("checkin.command_failed", locale)
            )

    async def sync_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        await update.effective_message.reply_text(translate("sync.loading", locale))
        try:
            await services.sync()
        except Exception:
            logger.exception("telegram sync command failed")
            await update.effective_message.reply_text(translate("sync.failed", locale))
            return
        await update.effective_message.reply_text(
            translate("sync.complete", locale),
            reply_markup=main_menu_markup(locale),
        )

    async def fatsecret_overview(message, edit: bool = False):
        status = await services.fatsecret_status()
        configured = bool(status.get("configured"))
        connected = bool(status.get("connected"))
        if not configured:
            text = translate("fatsecret.not_configured", locale)
        elif connected:
            time_value = getattr(settings, "fatsecret_auto_import_time", "23:30")
            text = translate("fatsecret.connected", locale, time=time_value)
        else:
            text = translate("fatsecret.disconnected", locale)
        if edit:
            await message.edit_message_text(text, reply_markup=fatsecret_markup(connected, locale))
        else:
            await message.reply_text(text, reply_markup=fatsecret_markup(connected, locale))

    async def fatsecret_command(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        try:
            await fatsecret_overview(update.effective_message)
        except Exception:
            logger.exception("telegram FatSecret overview failed")
            await update.effective_message.reply_text(
                translate("fatsecret.settings_failed", locale)
            )

    async def show_checkin_prompt(update, context):
        checkin = context.user_data["checkin"]
        next_field = _next_rating_field(checkin["values"], checkin["period"])
        if next_field is not None:
            field, _label = next_field
            await update.effective_message.reply_text(
                translate(
                    "checkin.rate",
                    locale,
                    label=translate(f"checkin.{field}", locale),
                ),
                reply_markup=rating_markup(field, locale),
            )
            return
        if checkin["period"] == "morning":
            await finish_checkin(update, context)
            return
        _set_checkin_flow(context, "checkin_deep_work")
        await update.effective_message.reply_text(
            translate("checkin.deep_work", locale),
            reply_markup=skip_markup("deep_work_min", locale),
        )

    async def finish_checkin(update, context):
        command = _checkin_command(context.user_data["checkin"])
        try:
            _record_checkin(command, settings, services)
        except Exception:
            logger.exception("guided Telegram checkin failed")
            await update.effective_message.reply_text(
                translate("checkin.save_failed", locale)
            )
        else:
            await update.effective_message.reply_text(
                translate("checkin.saved", locale),
                reply_markup=main_menu_markup(locale),
            )
        _clear_flow(context)

    async def show_archive(update, report_type):
        paths = list_report_paths(settings.obsidian_vault, report_type)
        if not paths:
            await update.effective_message.reply_text(
                translate("archive.empty", locale),
                reply_markup=archive_menu_markup(locale),
            )
            return
        await update.effective_message.reply_text(
            translate("archive.choose", locale),
            reply_markup=archive_period_markup(report_type, [path.name for path in paths], locale),
        )

    async def send_archived_report(message, report_type, index):
        paths = list_report_paths(settings.obsidian_vault, report_type)
        if index < 0 or index >= len(paths):
            await message.reply_text(
                translate("archive.missing", locale),
                reply_markup=archive_menu_markup(locale),
            )
            return
        try:
            markdown = read_report(paths[index])
        except OSError:
            logger.exception("telegram archive read failed path=%s", paths[index])
            await message.reply_text(
                translate("archive.read_failed", locale),
                reply_markup=archive_menu_markup(locale),
            )
            return
        await message.reply_text(
            translate("archive.report_header", locale, name=paths[index].name)
        )
        for chunk in split_report_text(markdown):
            await message.reply_text(chunk)

    async def start_food_analysis(message, context, occurred_at: datetime, correction: str | None = None):
        food = context.user_data.get("food")
        if not food or not any(
            food.get(key) for key in ("photo_path", "description", "exact_details")
        ):
            await message.reply_text(translate("food.photo_missing", locale))
            return
        await message.reply_text(translate("food.analyzing", locale))
        try:
            if food.get("photo_path"):
                analysis = await run_in_thread(
                    food_analyzer.analyze,
                    Path(food["photo_path"]),
                    food["meal_type"],
                    correction,
                    description=food.get("description"),
                    exact_details=food.get("exact_details"),
                )
                analysis_id = await run_in_thread(
                    _persist_food_analysis,
                    food,
                    occurred_at,
                    analysis,
                    services,
                    correction,
                )
                food["analysis_id"] = analysis_id
                food["storage_kind"] = "photo"
            else:
                description = food.get("description") or (
                    "Meal" if locale == "en" else "Приём пищи"
                )
                exact_details = food.get("exact_details")
                if correction:
                    exact_details = (
                        f"{exact_details}. Correction: {correction}"
                        if exact_details
                        else f"Correction: {correction}"
                    )
                analysis = await run_in_thread(
                    food_text_analyzer.analyze,
                    description,
                    food["meal_type"],
                    exact_details=exact_details,
                )
                food["analysis"] = analysis.model_dump()
                food["storage_kind"] = "text"
        except Exception:
            logger.exception("telegram food analysis failed")
            await message.reply_text(translate("food.analysis_failed", locale))
            return
        food["occurred_at"] = occurred_at.isoformat()
        food["correction"] = correction
        context.user_data["flow"] = "food_confirmation"
        await message.reply_text(
            translate(
                "food.review",
                locale,
                meal_type=food["meal_type"],
                time=occurred_at.strftime("%H:%M"),
                analysis=format_food_analysis(analysis, locale),
            ),
            reply_markup=food_confirmation_markup(locale),
        )

    async def handle_photo(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        try:
            photo = update.effective_message.photo[-1]
            photo_dir = Path(settings.food_photo_dir)
            if context.user_data.get("flow") in {
                "ask_waiting", "ask_photo_question", "ask_model_choice", "training_input"
            } or (
                update.effective_message.caption or ""
            ).strip().lower().startswith(("/ask", "/training")):
                photo_dir = photo_dir / (
                    "questions" if context.user_data.get("flow") in {
                        "ask_waiting", "ask_photo_question", "ask_model_choice"
                    } or
                    (update.effective_message.caption or "").strip().lower().startswith("/ask")
                    else "training"
                )
            ensure_private_directory(photo_dir)
            zone = ZoneInfo(settings.timezone)
            received_at = datetime.now(zone)
            path = photo_dir / f"{received_at:%Y%m%d_%H%M%S}_{photo.file_unique_id}.jpg"
            telegram_file = await context.bot.get_file(photo.file_id)
            await telegram_file.download_to_drive(custom_path=path)
            restrict_private_file(path)
        except Exception:
            logger.exception("telegram food photo download failed")
            await update.effective_message.reply_text(
                translate("common.photo_save_failed", locale)
            )
            return
        caption = (update.effective_message.caption or "").strip()
        question_flow = context.user_data.get("flow") in {
            "ask_waiting", "ask_photo_question", "ask_model_choice"
        }
        if question_flow or caption.lower().startswith("/ask"):
            question = (
                caption[4:].strip()
                if caption.lower().startswith("/ask")
                else (caption if question_flow and caption else context.user_data.get("ask_question", ""))
            )
            image_paths = [Path(item) for item in context.user_data.get("ask_image_paths", [])]
            image_paths.append(path)
            if context.user_data.get("flow") == "ask_model_choice":
                context.user_data["ask_image_paths"] = [str(item) for item in image_paths]
                await update.effective_message.reply_text(
                    translate(
                        "question.photo_added_choose", locale, count=len(image_paths)
                    )
                )
                return
            if not question:
                context.user_data["ask_image_paths"] = [str(item) for item in image_paths]
                context.user_data["flow"] = "ask_photo_question"
                await update.effective_message.reply_text(
                    translate(
                        "question.photo_added_more", locale, count=len(image_paths)
                    )
                )
                return
            _clear_flow(context)
            await ask_model_choice(update.effective_message, context, question, image_paths)
            return
        if context.user_data.get("flow") == "training_input" or caption.lower().startswith("/training"):
            text = caption[9:].strip() if caption.lower().startswith("/training") else caption or None
            _clear_flow(context)
            await update.effective_message.reply_text(
                translate("training.analyzing", locale)
            )
            try:
                await services.analyze_training(
                    datetime.now(ZoneInfo(settings.timezone)),
                    text=text,
                    photo_path=path,
                )
            except Exception:
                logger.exception("telegram training photo analysis failed")
                await update.effective_message.reply_text(
                    translate("training.failed", locale)
                )
            else:
                await update.effective_message.reply_text(
                    translate("training.saved", locale),
                    reply_markup=main_menu_markup(locale),
                )
            return
        food_draft_flow = context.user_data.get("flow") in {
            "food_photo_input",
            "food_description_input",
            "food_exact_input",
        }
        previous_flow = context.user_data.get("flow")
        if not food_draft_flow:
            _clear_flow(context)
            context.user_data["food"] = {}
        food = context.user_data.setdefault("food", {})
        food["photo_path"] = str(path)
        if caption:
            previous_description = food.get("description")
            food["description"] = (
                f"{previous_description}. {caption}"
                if previous_description and caption not in previous_description
                else previous_description or caption
            )
        if caption or previous_flow == "food_exact_input":
            context.user_data["flow"] = "food_exact_input"
            await update.effective_message.reply_text(
                translate("food.exact_prompt", locale),
                reply_markup=food_step_markup("exact", locale),
            )
        else:
            context.user_data["flow"] = "food_description_input"
            await update.effective_message.reply_text(
                translate("food.description_prompt", locale),
                reply_markup=food_step_markup("description", locale),
            )

    async def handle_callback(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        query = update.callback_query
        await query.answer()
        data = query.data or ""
        logger.info("telegram callback received action=%s", data)
        message = update.effective_message

        if data.startswith("feedback:"):
            try:
                _, item_type, raw_report_id, raw_index, verdict = data.split(":", 4)
                report_id = int(raw_report_id)
                item_index = int(raw_index)
                from sqlalchemy import select

                from fitbit_report.db.models import GeneratedReport, InsightFeedback
                from fitbit_report.db.session import session_scope
                from fitbit_report.memory.service import record_insight_feedback

                with session_scope(services.engine) as session:
                    report = session.get(GeneratedReport, report_id)
                    if report is None or not report.draft_json:
                        raise ValueError("Report was not found")
                    draft = json.loads(report.draft_json)
                    items = draft.get("claims" if item_type == "claim" else "recommendations", [])
                    if item_index < 0 or item_index >= len(items):
                        raise ValueError("Insight was not found")
                    item = items[item_index]
                    statement = item.get("statement") if isinstance(item, dict) else str(item)
                    record_insight_feedback(
                        session,
                        report_id,
                        item_type,
                        item_index,
                        verdict,
                        note=statement,
                    )
                    selected = {
                        (feedback.item_type, feedback.item_index): feedback.verdict
                        for feedback in session.scalars(
                            select(InsightFeedback).where(
                                InsightFeedback.report_id == report_id
                            )
                        )
                    }
                markup = _feedback_markup(
                    report_id,
                    feedback_claim_indices(draft.get("claims", [])),
                    selected,
                    locale,
                )
                await query.edit_message_reply_markup(reply_markup=markup)
            except Exception:
                logger.exception("telegram insight feedback failed")
                await query.answer(
                    translate("question.feedback_failed", locale), show_alert=True
                )
            return

        if data.startswith("question:model:"):
            choice = data.rsplit(":", 1)[1]
            question = context.user_data.pop("ask_question", "")
            image_paths = [Path(item) for item in context.user_data.pop("ask_image_paths", [])]
            if choice not in {"sonnet", "opus"} or not question:
                _clear_flow(context)
                await query.edit_message_text(translate("question.expired", locale))
                return
            model = (
                getattr(settings, "claude_report_model", "claude-opus-5")
                if choice == "opus"
                else getattr(settings, "claude_question_model", "claude-sonnet-5")
            )
            _clear_flow(context)
            await query.edit_message_text(
                translate(
                    "question.model_selected",
                    locale,
                    model="Opus" if choice == "opus" else "Sonnet",
                )
            )
            await answer_question_with_photos(message, question, image_paths, model)
            return

        if data == "journal:add_food":
            _clear_flow(context)
            context.user_data["food"] = {}
            context.user_data["flow"] = "food_photo_input"
            await query.edit_message_text(
                translate("food.photo_prompt", locale),
                reply_markup=food_step_markup("photo", locale),
            )
            return
        if data == "food-draft:skip:photo":
            context.user_data.setdefault("food", {})
            context.user_data["flow"] = "food_description_input"
            await query.edit_message_text(
                translate("food.description_prompt", locale),
                reply_markup=food_step_markup("description", locale),
            )
            return
        if data == "food-draft:skip:description":
            context.user_data.setdefault("food", {})
            context.user_data["flow"] = "food_exact_input"
            await query.edit_message_text(
                translate("food.exact_prompt", locale),
                reply_markup=food_step_markup("exact", locale),
            )
            return
        if data == "food-draft:skip:exact":
            food = context.user_data.get("food") or {}
            if not any(
                food.get(key)
                for key in ("photo_path", "description", "exact_details")
            ):
                context.user_data["flow"] = "food_photo_input"
                await query.edit_message_text(
                    translate("food.need_details", locale)
                    + "\n\n"
                    + translate("food.photo_prompt", locale),
                    reply_markup=food_step_markup("photo", locale),
                )
                return
            context.user_data["flow"] = "food_meal_type"
            await query.edit_message_text(
                translate("food.meal_type_prompt", locale),
                reply_markup=food_meal_type_markup(locale),
            )
            return
        if data == "food-draft:cancel":
            _clear_flow(context)
            await query.edit_message_text(translate("food.cancelled", locale))
            return
        if data.startswith("food:meal:"):
            food = context.user_data.get("food")
            if not food:
                await message.reply_text(translate("food.photo_missing", locale))
                return
            food["meal_type"] = data.rsplit(":", 1)[1]
            context.user_data["flow"] = "food_time_choice"
            await query.edit_message_text(
                translate("food.time_prompt", locale),
                reply_markup=food_time_markup(locale),
            )
            return
        if data == "food-time:now":
            zone = ZoneInfo(settings.timezone)
            await start_food_analysis(message, context, datetime.now(zone))
            return
        if data == "food-time:custom":
            context.user_data["flow"] = "food_time"
            await query.edit_message_text(translate("common.time_format", locale))
            return
        if data == "food-time:cancel":
            _clear_flow(context)
            await query.edit_message_text(translate("food.cancelled", locale))
            return
        if data == "food:confirm":
            food = context.user_data.get("food")
            if not food or not food.get("storage_kind"):
                await message.reply_text(
                    translate("food.confirm_missing", locale)
                )
                return
            try:
                if food["storage_kind"] == "photo":
                    await run_in_thread(
                        _confirm_food_analysis,
                        food["analysis_id"],
                        services,
                    )
                else:
                    await run_in_thread(_persist_text_food_analysis, food, services)
            except Exception:
                logger.exception("telegram food confirmation failed")
                await message.reply_text(
                    translate("food.confirm_failed", locale)
                )
            else:
                _clear_flow(context)
                await message.reply_text(
                    translate("food.confirmed", locale),
                    reply_markup=main_menu_markup(locale),
                )
            return
        if data == "food:edit":
            context.user_data["flow"] = "food_correction"
            await query.edit_message_text(
                translate("food.correction_prompt", locale)
            )
            return
        if data == "food:cancel":
            food = context.user_data.get("food")
            if food and food.get("storage_kind") == "photo" and food.get("analysis_id") is not None:
                await run_in_thread(_cancel_food_analysis, food["analysis_id"], services)
            _clear_flow(context)
            await message.reply_text(
                translate("food.cancelled", locale),
                reply_markup=main_menu_markup(locale),
            )
            return

        if data == "journal:fatsecret":
            try:
                await fatsecret_overview(query, edit=True)
            except Exception:
                logger.exception("telegram FatSecret overview failed")
                await query.edit_message_text(
                    translate("fatsecret.settings_failed", locale)
                )
            return
        if data == "fatsecret:connect":
            try:
                authorization_url = await services.start_fatsecret_authorization()
            except FatSecretOAuthError as exc:
                await query.edit_message_text(
                    translate("fatsecret.connect_failed", locale, error=exc)
                )
                return
            except Exception:
                logger.exception("telegram FatSecret authorization start failed")
                await query.edit_message_text(
                    translate("fatsecret.connect_failed_generic", locale)
                )
                return
            context.user_data["flow"] = "fatsecret_verifier"
            await query.edit_message_text(
                translate(
                    "fatsecret.connect_steps",
                    locale,
                    url=authorization_url,
                )
            )
            return
        if data == "fatsecret:sync":
            await query.edit_message_text(
                translate("fatsecret.importing_today", locale)
            )
            try:
                summary = await services.sync_fatsecret_foods()
            except FatSecretOAuthError as exc:
                await message.reply_text(
                    translate("fatsecret.api_import_failed", locale, error=exc)
                )
                return
            except Exception:
                logger.exception("telegram FatSecret manual import failed")
                await message.reply_text(
                    translate("fatsecret.api_import_failed_generic", locale)
                )
                return
            if summary.get("status") != "success":
                await message.reply_text(
                    translate("fatsecret.connect_first", locale)
                )
                return
            await message.reply_text(
                translate(
                    "fatsecret.api_imported",
                    locale,
                    date=summary["report_date"],
                    food_count=summary["food_count"],
                    meal_count=summary["meal_count"],
                ),
                reply_markup=main_menu_markup(locale),
            )
            return

        if data == "nav:main":
            _clear_flow(context)
            await query.edit_message_text(
                translate("navigation.main_open", locale)
            )
            await message.reply_text(
                translate("navigation.choose_section", locale),
                reply_markup=main_menu_markup(locale),
            )
            return
        if data == "nav:more":
            _clear_flow(context)
            await query.edit_message_text(
                translate("menu.more_prompt", locale),
                reply_markup=more_menu_markup(locale),
            )
            return
        if data == "more:entries":
            await entries_command(update, context)
            return
        if data == "more:edit_entries":
            await show_edit_entries(update, context)
            return
        if data == "more:sync":
            await query.edit_message_text(
                translate("menu.sync_prompt", locale),
                reply_markup=sync_confirm_markup(locale),
            )
            return
        if data == "more:usage":
            await usage_command(update, context)
            return
        if data == "more:status":
            await status_command(update, context)
            return
        if data == "more:help":
            await help_command(update, context)
            return
        if data == "nav:journal":
            _clear_flow(context)
            await query.edit_message_text(
                translate("navigation.journal_open", locale)
            )
            await message.reply_text(
                translate("menu.journal_prompt", locale),
                reply_markup=journal_menu_markup(locale),
            )
            return
        if data.startswith("entry:delete:"):
            event_id = int(data.rsplit(":", 1)[1])
            context.user_data["delete_entry_id"] = event_id
            await query.edit_message_text(
                translate("journal.delete_confirm", locale, entry_id=event_id),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(translate("button.delete", locale), callback_data=f"entry:delete-confirm:{event_id}"),
                     InlineKeyboardButton(translate("button.cancel", locale), callback_data="entry:back")]
                ]),
            )
            return
        if data.startswith("entry:delete-confirm:"):
            event_id = int(data.rsplit(":", 1)[1])
            from fitbit_report.db.session import session_scope
            from fitbit_report.journal.service import JournalService
            with session_scope(services.engine) as session:
                JournalService().delete(event_id, session)
            await query.edit_message_text(translate("journal.deleted_short", locale))
            return
        if data.startswith("entry:edit:"):
            event_id = int(data.rsplit(":", 1)[1])
            context.user_data["edit_entry_id"] = event_id
            context.user_data["flow"] = "edit_entry"
            await query.edit_message_text(
                translate("journal.edit_instructions", locale)
            )
            return
        if data == "entry:back":
            await show_edit_entries(update, context)
            return
        if data == "journal:nicotine":
            context.user_data["flow"] = "journal_nicotine_type"
            await query.edit_message_text(
                translate("journal.nicotine_prompt", locale),
                reply_markup=nicotine_menu_markup(locale),
            )
            return
        if data in {"journal:meal", "journal:meal_time"}:
            context.user_data["flow"] = "meal_type"
            await query.edit_message_text(
                translate("journal.meal_type_prompt", locale),
                reply_markup=meal_type_markup(locale),
            )
            return
        if data == "journal:training":
            context.user_data["flow"] = "training_input"
            await query.edit_message_text(
                translate("training.input_prompt", locale)
            )
            return
        if data.startswith("journal:meal:"):
            context.user_data["meal_time_type"] = data.rsplit(":", 1)[1]
            context.user_data["flow"] = "meal_time_choice"
            await query.edit_message_text(
                translate("common.time_prompt", locale),
                reply_markup=meal_time_markup(locale),
            )
            return
        if data == "meal-time:now":
            meal_type = context.user_data.get("meal_time_type", "other")
            zone = ZoneInfo(settings.timezone)
            _clear_flow(context)
            await save_meal_time(message, meal_type, datetime.now(zone).strftime("%H:%M"))
            return
        if data == "meal-time:custom":
            context.user_data["flow"] = "meal_time_input"
            await query.edit_message_text(
                translate("common.time_format", locale)
            )
            return
        if data == "meal-time:cancel":
            _clear_flow(context)
            await query.edit_message_text(translate("common.cancelled", locale))
            return
        if data.startswith("journal:nicotine:"):
            context.user_data["flow"] = "journal_amount"
            context.user_data["journal"] = {"category": "nicotine", "subtype": data.rsplit(":", 1)[1]}
            await query.edit_message_text(
                translate("journal.amount_prompt", locale)
            )
            return
        if data == "journal:caffeine":
            context.user_data["flow"] = "journal_amount"
            context.user_data["journal"] = {"category": "caffeine"}
            await query.edit_message_text(
                translate("journal.caffeine_prompt", locale)
            )
            return
        if data.startswith("journal:"):
            category = data.split(":", 1)[1]
            context.user_data["flow"] = "journal_note"
            context.user_data["journal"] = {"category": category}
            prompt = translate(
                "journal.training_prompt" if category == "training" else "journal.note_prompt",
                locale,
            )
            await query.edit_message_text(prompt)
            return
        if data == "journal-time:now":
            try:
                _record_journal(context.user_data["journal"]["command"], settings, services)
            except Exception:
                logger.exception("guided Telegram journal save failed")
                await message.reply_text(translate("common.save_failed", locale))
            else:
                _clear_flow(context)
                await message.reply_text(
                    translate("common.saved", locale),
                    reply_markup=main_menu_markup(locale),
                )
            return
        if data == "journal-time:custom":
            context.user_data["flow"] = "journal_time"
            await query.edit_message_text(translate("common.time_format", locale))
            return
        if data == "journal-time:cancel":
            _clear_flow(context)
            await query.edit_message_text(translate("common.cancelled", locale))
            await message.reply_text(
                translate("navigation.main_open", locale),
                reply_markup=main_menu_markup(locale),
            )
            return
        if data in {"checkin:morning", "checkin:evening"}:
            context.user_data["flow"] = "checkin_rating"
            context.user_data["checkin"] = {"period": data.split(":", 1)[1], "values": {}}
            await query.edit_message_text(translate("checkin.started", locale))
            await show_checkin_prompt(update, context)
            return
        match = re.fullmatch(r"checkin:(set|skip):([a-z_]+)(?::(\d+))?", data)
        if match and "checkin" in context.user_data:
            action, field, raw_value = match.groups()
            checkin = context.user_data["checkin"]
            checkin["values"][field] = int(raw_value) if action == "set" else None
            if field == "deep_work_min":
                _set_checkin_flow(context, "checkin_priority")
                await message.reply_text(
                    translate("checkin.priority", locale),
                    reply_markup=skip_markup("priority", locale),
                )
                return
            if field == "priority":
                _set_checkin_flow(context, "checkin_note")
                await message.reply_text(
                    translate("checkin.note", locale),
                    reply_markup=skip_markup("note", locale),
                )
                return
            if field == "note":
                await finish_checkin(update, context)
                return
            await show_checkin_prompt(update, context)
            return
        if data.startswith("report:") or data.startswith("archive:list:"):
            report_type = data.split(":", 1)[1] if data.startswith("report:") else data.split(":", 2)[2]
            if report_type in {"daily", "weekly", "monthly"}:
                await show_archive(update, report_type)
                return
            return
        if data == "nav:archive":
            await message.reply_text(
                translate("archive.menu", locale),
                reply_markup=archive_menu_markup(locale),
            )
            return
        if data.startswith("archive:view:"):
            _, _, report_type, raw_index = data.split(":", 3)
            await send_archived_report(message, report_type, int(raw_index))
            return
        if data == "sync:cancel":
            await query.edit_message_text(translate("sync.cancelled", locale))
            return
        if data == "sync:confirm":
            await query.edit_message_text(translate("sync.loading", locale))
            try:
                await services.sync()
            except Exception:
                logger.exception("guided Telegram sync failed")
                await message.reply_text(translate("sync.failed", locale))
            else:
                await message.reply_text(
                    translate("sync.complete", locale),
                    reply_markup=main_menu_markup(locale),
                )

    async def handle_text(update, context):
        if not is_allowed_chat(update.effective_chat.id, settings.telegram_allowed_chat_id):
            return
        text = (update.effective_message.text or "").strip()
        logger.info(
            "telegram text received kind=%s",
            "menu" if text in menu_labels else "message",
        )
        flow = context.user_data.get("flow")
        if flow == "fatsecret_verifier":
            try:
                await services.complete_fatsecret_authorization(text)
            except FatSecretOAuthError as exc:
                await update.effective_message.reply_text(
                    translate("fatsecret.verify_failed", locale, error=exc)
                )
                return
            except Exception:
                logger.exception("telegram FatSecret authorization completion failed")
                await update.effective_message.reply_text(
                    translate("fatsecret.verify_failed_generic", locale)
                )
                return
            _clear_flow(context)
            await update.effective_message.reply_text(
                translate("fatsecret.connected_importing", locale)
            )
            try:
                summary = await services.sync_fatsecret_foods()
            except Exception:
                logger.exception("telegram FatSecret first import failed")
                await update.effective_message.reply_text(
                    translate("fatsecret.first_import_failed", locale)
                )
                return
            await update.effective_message.reply_text(
                translate(
                    "fatsecret.auto_import_enabled",
                    locale,
                    time=getattr(settings, "fatsecret_auto_import_time", "23:30"),
                    food_count=summary.get("food_count", 0),
                    meal_count=summary.get("meal_count", 0),
                ),
                reply_markup=main_menu_markup(locale),
            )
            return
        fatsecret_url = _extract_fatsecret_url(text)
        if fatsecret_url:
            _clear_flow(context)
            await import_fatsecret_message(update.effective_message, fatsecret_url)
            return
        if flow == "ask_waiting":
            _clear_flow(context)
            await ask_model_choice(update.effective_message, context, text)
            return
        if flow == "ask_photo_question":
            image_paths = [Path(item) for item in context.user_data.get("ask_image_paths", [])]
            if not image_paths and context.user_data.get("ask_photo_path"):
                # Support a photo that was saved by the previous bot version.
                image_paths = [Path(context.user_data["ask_photo_path"])]
            _clear_flow(context)
            await ask_model_choice(update.effective_message, context, text, image_paths)
            return
        if flow == "training_input":
            _clear_flow(context)
            await update.effective_message.reply_text(
                translate("training.analyzing", locale)
            )
            try:
                await services.analyze_training(datetime.now(ZoneInfo(settings.timezone)), text=text)
            except Exception:
                logger.exception("telegram text training analysis failed")
                await update.effective_message.reply_text(
                    translate("training.failed", locale)
                )
            else:
                await update.effective_message.reply_text(
                    translate("training.saved", locale),
                    reply_markup=main_menu_markup(locale),
                )
            return
        if flow == "food_photo_input":
            await update.effective_message.reply_text(
                translate("food.photo_prompt", locale),
                reply_markup=food_step_markup("photo", locale),
            )
            return
        if flow == "food_description_input":
            context.user_data.setdefault("food", {})["description"] = text
            context.user_data["flow"] = "food_exact_input"
            await update.effective_message.reply_text(
                translate("food.exact_prompt", locale),
                reply_markup=food_step_markup("exact", locale),
            )
            return
        if flow == "food_exact_input":
            context.user_data.setdefault("food", {})["exact_details"] = text
            context.user_data["flow"] = "food_meal_type"
            await update.effective_message.reply_text(
                translate("food.meal_type_prompt", locale),
                reply_markup=food_meal_type_markup(locale),
            )
            return
        if flow == "meal_time_command":
            parts = text.split()
            if len(parts) != 2:
                await update.effective_message.reply_text(
                    translate("meal_time.input_prompt", locale)
                )
                return
            _clear_flow(context)
            await save_meal_time(update.effective_message, parts[0].lower(), parts[1])
            return
        if flow == "meal_time_input":
            meal_type = context.user_data.get("meal_time_type", "other")
            _clear_flow(context)
            await save_meal_time(update.effective_message, meal_type, text)
            return
        if flow == "edit_entry":
            try:
                values = {}
                for token in shlex.split(text):
                    key, value = token.split("=", 1)
                    if key == "at":
                        zone = ZoneInfo(settings.timezone)
                        value = datetime.combine(datetime.now(zone).date(), time.fromisoformat(value), tzinfo=zone)
                    elif key in {"quantity", "dose", "intensity"}:
                        value = float(value)
                    elif key == "duration_min":
                        value = int(value)
                    values[key] = value
                from fitbit_report.db.session import session_scope
                from fitbit_report.journal.service import JournalService
                with session_scope(services.engine) as session:
                    JournalService().update(context.user_data["edit_entry_id"], values, session)
                _clear_flow(context)
                await update.effective_message.reply_text(
                    translate("journal.edited_short", locale),
                    reply_markup=main_menu_markup(locale),
                )
            except Exception:
                await update.effective_message.reply_text(
                    translate("journal.edit_failed_example", locale)
                )
            return
        if flow == "food_time":
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text):
                await update.effective_message.reply_text(
                    translate("common.time_format", locale)
                )
                return
            zone = ZoneInfo(settings.timezone)
            parsed_time = time.fromisoformat(text)
            occurred_at = datetime.combine(
                datetime.now(zone).date(), parsed_time, tzinfo=zone
            )
            await start_food_analysis(update.effective_message, context, occurred_at)
            return
        if flow == "food_correction":
            if not text:
                await update.effective_message.reply_text(
                    translate("food.correction_required", locale)
                )
                return
            food = context.user_data.get("food")
            occurred_at = datetime.fromisoformat(food["occurred_at"])
            await start_food_analysis(update.effective_message, context, occurred_at, text)
            return
        if flow == "journal_amount":
            journal = context.user_data["journal"]
            amount_pattern = r"\d+(?:\.\d+)?[A-Za-zА-Яа-я]+"
            if journal["category"] == "nicotine":
                amount_pattern = rf"{amount_pattern}(?:\s+{amount_pattern})?"
            if not re.fullmatch(amount_pattern, text):
                await update.effective_message.reply_text(
                    translate("journal.amount_format", locale)
                )
                return
            journal["command"] = _journal_command_from_amount(journal, text)
            context.user_data["flow"] = "journal_time_choice"
            await update.effective_message.reply_text(
                translate("common.time_prompt", locale),
                reply_markup=journal_time_markup(locale),
            )
            return
        if flow == "meal_description":
            if not text:
                await update.effective_message.reply_text(
                    translate("journal.empty_meal", locale)
                )
                return
            journal = context.user_data["journal"]
            journal["command"] = _meal_command(journal["subtype"], text)
            context.user_data["flow"] = "journal_time_choice"
            await update.effective_message.reply_text(
                translate("common.time_prompt", locale),
                reply_markup=journal_time_markup(locale),
            )
            return
        if flow == "journal_time":
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text):
                await update.effective_message.reply_text(
                    translate("common.time_format", locale)
                )
                return
            journal = context.user_data["journal"]
            journal["command"] = f"{journal['command']} at {text}"
            try:
                event = _record_journal(journal["command"], settings, services)
                if event.category == "meal" and hasattr(services, "analyze_text_meal"):
                    await services.analyze_text_meal(event.id)
            except Exception:
                logger.exception("guided Telegram journal time save failed")
                await update.effective_message.reply_text(
                    translate("common.save_failed", locale)
                )
            else:
                _clear_flow(context)
                await update.effective_message.reply_text(
                    translate("common.saved", locale),
                    reply_markup=main_menu_markup(locale),
                )
            return
        if flow == "journal_note":
            journal = context.user_data["journal"]
            command = f"/log training {text}" if journal["category"] == "training" else f"/log {journal['category']} {text}"
            try:
                _record_journal(command, settings, services)
            except Exception:
                logger.exception("guided Telegram note save failed")
                await update.effective_message.reply_text(
                    translate("common.save_failed", locale)
                )
            else:
                _clear_flow(context)
                await update.effective_message.reply_text(
                    translate("common.saved", locale),
                    reply_markup=main_menu_markup(locale),
                )
            return
        if flow == "checkin_deep_work":
            if not text.isdigit() or int(text) < 0:
                await update.effective_message.reply_text(
                    translate("checkin.invalid_minutes", locale)
                )
                return
            context.user_data["checkin"]["values"]["deep_work_min"] = int(text)
            _set_checkin_flow(context, "checkin_priority")
            await update.effective_message.reply_text(
                translate("checkin.priority", locale),
                reply_markup=skip_markup("priority", locale),
            )
            return
        if flow == "checkin_priority":
            context.user_data["checkin"]["values"]["priority"] = text
            _set_checkin_flow(context, "checkin_note")
            await update.effective_message.reply_text(
                translate("checkin.note", locale),
                reply_markup=skip_markup("note", locale),
            )
            return
        if flow == "checkin_note":
            context.user_data["checkin"]["values"]["note"] = text
            await finish_checkin(update, context)
            return
        labels = {
            menu_labels[0]: (translate("menu.journal_prompt", locale), journal_menu_markup(locale)),
            menu_labels[1]: (translate("menu.productivity_prompt", locale), checkin_period_markup(locale)),
            menu_labels[2]: (translate("menu.ask_hint", locale), main_menu_markup(locale)),
            menu_labels[3]: (translate("menu.archive_prompt", locale), archive_menu_markup(locale)),
            menu_labels[4]: (translate("menu.more_prompt", locale), more_menu_markup(locale)),
        }
        if text in labels:
            if text == menu_labels[2]:
                context.user_data["flow"] = "ask_waiting"
                await update.effective_message.reply_text(
                    translate("menu.ask_next", locale)
                )
                return
            prompt, markup = labels[text]
            await update.effective_message.reply_text(prompt, reply_markup=markup)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("log", log_command))
    application.add_handler(CommandHandler("checkin", checkin_command))
    application.add_handler(CommandHandler("sync", sync_command))
    application.add_handler(CommandHandler("fatsecret", fatsecret_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("training", training_command))
    application.add_handler(CommandHandler("mealtime", mealtime_command))
    application.add_handler(CommandHandler("entries", entries_command))
    application.add_handler(CommandHandler("edit", edit_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("editcheckin", edit_checkin_command))
    application.add_handler(CommandHandler("deletecheckin", delete_checkin_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, import_fatsecret_document_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return application
