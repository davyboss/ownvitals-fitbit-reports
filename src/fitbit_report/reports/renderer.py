from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from fitbit_report.i18n import Locale
from fitbit_report.reports.presentation import (
    format_metric_value,
    personal_metrics,
    readiness,
)

_REPORT_LABELS = {
    "en": {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"},
    "ru": {"daily": "Дневной", "weekly": "Недельный", "monthly": "Месячный"},
}
_KIND_LABELS = {
    "en": {"fact": "Fact", "association": "Association", "hypothesis": "Hypothesis"},
    "ru": {"fact": "Факт", "association": "Ассоциация", "hypothesis": "Гипотеза"},
}
_CONFIDENCE_LABELS = {
    "en": {"insufficient": "insufficient data", "low": "low", "medium": "medium", "high": "high"},
    "ru": {"insufficient": "недостаточно данных", "low": "низкая", "medium": "средняя", "high": "высокая"},
}
_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)

_TECHNICAL_LABELS = {
    "en": {
        "personal_state": "calculated personal readiness",
        "personal_factors": "personal factors",
        "source_ids": "sources",
        "sleep_timing_history": "sleep timing history",
        "start_time": "sleep start time",
        "end_time": "wake time",
        "health_before_day": "state before the day",
        "previous_day_steps": "previous-day steps",
        "previous_day_exercise_minutes": "previous-day exercise",
        "baseline_28d": "28-day personal baseline",
        "baseline_14d": "14-day personal baseline",
        "baseline_7d": "7-day personal baseline",
        "nutrition_summary": "nutrition summary",
        "exercise_sessions": "workouts",
        "data_completeness": "data completeness",
    },
    "ru": {
        "personal_state": "рассчитанная персональная оценка",
        "personal_factors": "личные факторы",
        "source_ids": "источники",
        "sleep_timing_history": "история времени сна",
        "start_time": "время начала сна",
        "end_time": "время окончания сна",
        "health_before_day": "состояние перед днём",
        "previous_day_steps": "шаги за предыдущий день",
        "previous_day_exercise_minutes": "тренировка предыдущего дня",
        "baseline_28d": "личная норма за 28 дней",
        "baseline_14d": "личная норма за 14 дней",
        "baseline_7d": "личная норма за 7 дней",
        "nutrition_summary": "сводка питания",
        "exercise_sessions": "тренировки",
        "data_completeness": "полнота данных",
    },
}

_READINESS_STATUS = {
    "en": {"хорошее": "good", "сниженное": "reduced", "обычное": "typical"},
    "ru": {},
}


def _clean_text(value: object, locale: Locale = "ru") -> str:
    text = str(value)
    for technical, readable in _TECHNICAL_LABELS[locale].items():
        text = text.replace(technical, readable)
    return text.replace("  ", " ").strip()


def _html_text(value: object, locale: Locale = "ru") -> str:
    return escape(_clean_text(value, locale), quote=False)


def _markdown_callout(title: str, body: str, kind: str = "note") -> list[str]:
    return [f"> [!{kind}] {title}", ">", *[f"> {line}" for line in body.splitlines()]]


def _format_period(report: dict, locale: Locale = "ru") -> str:
    start = report["period_start"]
    end = report["period_end"]
    if locale == "en":
        if start == end:
            return f"{start:%B} {start.day}, {start.year}"
        return f"{start:%B} {start.day} – {end:%B} {end.day}, {end.year}"
    if start == end:
        return f"{start.day} {_MONTHS[start.month - 1]} {start.year}"
    return (
        f"{start.day} {_MONTHS[start.month - 1]} — "
        f"{end.day} {_MONTHS[end.month - 1]} {end.year}"
    )


def render_markdown(
    report: dict,
    draft: dict,
    timezone_name: str = "Europe/Kiev",
    locale: Locale = "ru",
) -> str:
    copy = {
        "en": {
            "fallback_report": "Analytical",
            "main": "Main takeaway",
            "observations": "Observations",
            "try": "What to try",
            "experiment": "Personal experiment",
            "reliability": "Reliability",
            "confidence": "Confidence",
            "evidence": "observations",
            "missing": "not specified",
        },
        "ru": {
            "fallback_report": "Аналитический",
            "main": "Главный вывод",
            "observations": "Наблюдения",
            "try": "Что попробовать",
            "experiment": "Личный эксперимент",
            "reliability": "Надёжность вывода",
            "confidence": "Уверенность",
            "evidence": "наблюдений",
            "missing": "не указана",
        },
    }[locale]
    period = _format_period(report, locale)
    lines = [
        "---",
        f"type: {report['type']}",
        f"period: {period}",
        f"generated_at: {datetime.now(ZoneInfo(timezone_name)).isoformat()}",
        "---",
        "",
        f"# {_REPORT_LABELS[locale].get(report['type'], copy['fallback_report'])} "
        + ("report" if locale == "en" else "отчёт"),
        f"_{period}_",
        "",
        *_markdown_callout(copy["main"], _clean_text(draft["summary"], locale), "summary"),
        "",
        f"## {copy['observations']}",
    ]
    for claim in draft.get("claims", []):
        kind = _KIND_LABELS[locale].get(claim["kind"], claim["kind"])
        confidence = _CONFIDENCE_LABELS[locale].get(claim["confidence"], claim["confidence"])
        lines.append(
            f"- **{kind}**: {_clean_text(claim['statement'], locale)} "
            f"({copy['confidence'].lower()}: {confidence}, "
            f"{copy['evidence']}: {claim['evidence_count']})"
        )
    lines += ["", f"## {copy['try']}"]
    lines.extend(f"- {_clean_text(item, locale)}" for item in draft.get("recommendations", []))
    lines += ["", f"## {copy['experiment']}"]
    lines.extend(f"- {_clean_text(item, locale)}" for item in draft.get("experiments", []))
    lines += ["", f"## {copy['reliability']}"]
    confidence = _CONFIDENCE_LABELS[locale].get(
        draft.get("confidence"), draft.get("confidence", copy["missing"])
    )
    lines.append(f"{copy['confidence']}: {confidence}.")
    return "\n".join(lines) + "\n"


def _telegram_copy(locale: Locale) -> dict[str, str]:
    return {
        "en": {
            "fallback_report": "Analytical",
            "report": "report",
            "metrics": "Personal metrics",
            "metric": "Metric",
            "current": "Current",
            "baseline": "Personal baseline",
            "change": "Change",
            "readiness": "Readiness",
            "better": "better",
            "unavailable": "unavailable",
            "main": "Main takeaway",
            "chart_caption_daily": "How each factor contributed to today's readiness",
            "chart_caption_period": "Personal trends over the report period",
            "observations": "Observations",
            "confidence": "Confidence",
            "evidence": "Observations",
            "no_observations": "No observations for this period.",
            "recommendations": "Recommendations",
            "no_recommendations": "No recommendations.",
            "experiment": "Personal experiment",
            "no_experiments": "No suggested experiments.",
            "reliability": "Reliability",
            "missing": "not specified",
            "lower_note": "For resting heart rate, a lower value is treated as an improvement.",
        },
        "ru": {
            "fallback_report": "Аналитический",
            "report": "отчёт",
            "metrics": "Личные показатели",
            "metric": "Показатель",
            "current": "Сейчас",
            "baseline": "Личная норма",
            "change": "Изменение",
            "readiness": "Состояние",
            "better": "лучше",
            "unavailable": "нет сравнения",
            "main": "Главный вывод",
            "chart_caption_daily": "Вклад факторов в сегодняшнюю оценку состояния",
            "chart_caption_period": "Персональная динамика за период отчёта",
            "observations": "Наблюдения",
            "confidence": "Уверенность",
            "evidence": "Наблюдений",
            "no_observations": "Нет наблюдений за этот период.",
            "recommendations": "Рекомендации",
            "no_recommendations": "Нет рекомендаций.",
            "experiment": "Личный эксперимент",
            "no_experiments": "Нет предложенных экспериментов.",
            "reliability": "Надёжность",
            "missing": "не указана",
            "lower_note": "Для пульса покоя более низкое значение считается улучшением.",
        },
    }[locale]


def _format_delta(metric, copy: dict[str, str], locale: Locale) -> str:
    delta = metric.raw_delta_percent
    if delta is None:
        return copy["unavailable"]
    rendered = f"{delta:+.1f}%"
    if locale == "ru":
        rendered = rendered.replace(".", ",")
    if metric.lower_is_better and delta < 0:
        rendered += f" ({copy['better']})"
    return rendered


def _metric_rows(context: dict | None, locale: Locale) -> list[tuple[str, str, str, str]]:
    copy = _telegram_copy(locale)
    rows: list[tuple[str, str, str, str]] = []
    score, status = readiness(context)
    if score is not None:
        localized_status = _READINESS_STATUS[locale].get(status, status or copy["missing"])
        rows.append((copy["readiness"], f"{score:g} / 100", "—", str(localized_status)))
    for metric in personal_metrics(context, locale):
        if metric.current is None and metric.baseline is None:
            continue
        rows.append(
            (
                metric.label,
                format_metric_value(metric.current, metric, locale),
                format_metric_value(metric.baseline, metric, locale),
                _format_delta(metric, copy, locale),
            )
        )
    return rows


def _rich_metric_table(context: dict | None, locale: Locale) -> str:
    copy = _telegram_copy(locale)
    rows = _metric_rows(context, locale)
    if not rows:
        return ""
    header = (
        f"<tr><th>{copy['metric']}</th><th>{copy['current']}</th>"
        f"<th>{copy['baseline']}</th><th>{copy['change']}</th></tr>"
    )
    body = "".join(
        f"<tr><td>{_html_text(label, locale)}</td><td>{_html_text(current, locale)}</td>"
        f"<td>{_html_text(baseline, locale)}</td><td>{_html_text(change, locale)}</td></tr>"
        for label, current, baseline, change in rows
    )
    return f"<table bordered striped compact>{header}{body}</table>"


def _fallback_metrics(context: dict | None, locale: Locale) -> list[str]:
    copy = _telegram_copy(locale)
    rows = _metric_rows(context, locale)
    if not rows:
        return []
    lines = [f"<b>{copy['metrics']}</b>"]
    for label, current, baseline, change in rows:
        lines.append(
            f"<b>{_html_text(label, locale)}</b>: {_html_text(current, locale)} · "
            f"{copy['baseline'].lower()} {_html_text(baseline, locale)} · {_html_text(change, locale)}"
        )
    lines.extend([f"<i>{copy['lower_note']}</i>", ""])
    return lines


def render_telegram_parts(
    report: dict,
    draft: dict,
    context: dict | None = None,
    locale: Locale = "ru",
) -> tuple[str, str]:
    copy = _telegram_copy(locale)
    report_label = _REPORT_LABELS[locale].get(report["type"], copy["fallback_report"])
    before = [
        f"<b>{report_label} {copy['report']}</b>",
        f"<i>{_format_period(report, locale)}</i>",
        "",
        *_fallback_metrics(context, locale),
        f"<b>{copy['main']}</b>",
        f"<blockquote>{_html_text(draft['summary'], locale)}</blockquote>",
    ]
    after = [f"<b>{copy['observations']}</b>"]
    claims = draft.get("claims", [])
    if claims:
        for index, claim in enumerate(claims, 1):
            kind = _KIND_LABELS[locale].get(claim["kind"], claim["kind"])
            confidence = _CONFIDENCE_LABELS[locale].get(
                claim["confidence"], claim["confidence"]
            )
            after.extend(
                [
                    f"<b>{index}. {_html_text(kind, locale)}</b>",
                    _html_text(claim["statement"], locale),
                    f"<i>{copy['confidence']}: {confidence} · "
                    f"{copy['evidence']}: {claim['evidence_count']}</i>",
                    "",
                ]
            )
    else:
        after.extend([copy["no_observations"], ""])
    after.append(f"<b>{copy['recommendations']}</b>")
    recommendations = draft.get("recommendations", [])
    after.extend(
        f"{index}. {_html_text(item, locale)}"
        for index, item in enumerate(recommendations, 1)
    ) if recommendations else after.append(copy["no_recommendations"])
    after.extend(["", f"<b>{copy['experiment']}</b>"])
    experiments = draft.get("experiments", [])
    after.extend(
        f"{index}. {_html_text(item, locale)}"
        for index, item in enumerate(experiments, 1)
    ) if experiments else after.append(copy["no_experiments"])
    confidence = _CONFIDENCE_LABELS[locale].get(
        draft.get("confidence"), draft.get("confidence", copy["missing"])
    )
    after.extend(["", f"<b>{copy['reliability']}</b>", _html_text(confidence, locale)])
    return "\n".join(before), "\n".join(after)


def render_telegram_rich(
    report: dict,
    draft: dict,
    context: dict | None = None,
    locale: Locale = "ru",
    include_chart: bool = True,
) -> str:
    copy = _telegram_copy(locale)
    report_label = _REPORT_LABELS[locale].get(report["type"], copy["fallback_report"])
    parts = [
        f"<h1>{report_label} {copy['report']}</h1>",
        f"<footer>{_format_period(report, locale)}</footer>",
        _rich_metric_table(context, locale),
        f"<h2>{copy['main']}</h2>",
        f"<aside>{_html_text(draft['summary'], locale)}</aside>",
    ]
    if include_chart:
        chart_caption = copy[
            "chart_caption_daily"
            if report["type"] == "daily"
            else "chart_caption_period"
        ]
        parts.append(
            '<figure><img src="tg://photo?id=report_chart"/>'
            f"<figcaption>{chart_caption}</figcaption></figure>"
        )
    parts.extend(["<hr/>", f"<h2>{copy['observations']}</h2>"])
    claims = draft.get("claims", [])
    if claims:
        for index, claim in enumerate(claims, 1):
            kind = _KIND_LABELS[locale].get(claim["kind"], claim["kind"])
            confidence = _CONFIDENCE_LABELS[locale].get(
                claim["confidence"], claim["confidence"]
            )
            parts.extend(
                [
                    f"<h3>{index}. {_html_text(kind, locale)}</h3>",
                    f"<p>{_html_text(claim['statement'], locale)}</p>",
                    f"<footer>{copy['confidence']}: {confidence} · "
                    f"{copy['evidence']}: {claim['evidence_count']}</footer>",
                ]
            )
    else:
        parts.append(f"<p>{copy['no_observations']}</p>")
    parts.extend(["<hr/>", f"<h2>{copy['recommendations']}</h2>"])
    recommendations = draft.get("recommendations", [])
    if recommendations:
        parts.append("<ol>" + "".join(
            f"<li>{_html_text(item, locale)}</li>" for item in recommendations
        ) + "</ol>")
    else:
        parts.append(f"<p>{copy['no_recommendations']}</p>")
    parts.append(f"<h2>{copy['experiment']}</h2>")
    experiments = draft.get("experiments", [])
    if experiments:
        parts.append("<ol>" + "".join(
            f"<li>{_html_text(item, locale)}</li>" for item in experiments
        ) + "</ol>")
    else:
        parts.append(f"<p>{copy['no_experiments']}</p>")
    confidence = _CONFIDENCE_LABELS[locale].get(
        draft.get("confidence"), draft.get("confidence", copy["missing"])
    )
    parts.append(f"<aside>{copy['reliability']}: {_html_text(confidence, locale)}</aside>")
    return "".join(parts)


def render_telegram(
    report: dict,
    draft: dict,
    context: dict | None = None,
    locale: Locale = "ru",
) -> str:
    before, after = render_telegram_parts(report, draft, context, locale)
    return f"{before}\n\n{after}"
