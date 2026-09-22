from __future__ import annotations

from collections import defaultdict
from datetime import date
import logging
from pathlib import Path

from fitbit_report.i18n import Locale
from fitbit_report.types import DateRange
from fitbit_report.private_storage import ensure_private_directory, restrict_private_file

logger = logging.getLogger(__name__)

BACKGROUND = "#101416"
PANEL = "#20282b"
FOREGROUND = "#f3f5f5"
MUTED = "#aab5b8"
GRID = "#3d484c"
BASELINE = "#f3f5f5"
ACCENT = "#70d7cd"
NEGATIVE = "#d99a92"
SERIES = (ACCENT, "#8abeb9", "#d4eded", "#5ea9a3")
CONFIDENCE_LABELS = {
    "en": {"usable": "sufficient", "exploratory": "exploratory", "insufficient": "insufficient data"},
    "ru": {"usable": "достаточная", "exploratory": "ориентировочная", "insufficient": "недостаточно данных"},
}


def _copy(locale: Locale) -> dict[str, str]:
    return {
        "en": {
            "date": "date", "baseline": "Personal baseline", "to_baseline": "vs baseline",
            "pp_to_baseline": "pp vs baseline", "no_baseline": "no baseline for comparison",
            "no_record": "no record", "cannot_compare": "comparison unavailable",
            "no_comparison": "No data to compare", "baseline_axis": "% of personal baseline · 100% = your baseline",
            "readiness_title": "Readiness · overall score", "readiness_empty": "Insufficient data to estimate readiness",
            "readiness_points": "readiness points", "unknown": "not determined",
            "components": "Components used: {count}",
            "components_no_checkin": "No subjective check-in · components used: {count}",
            "sleep_snapshot": "Sleep · current value vs baseline", "movement_snapshot": "Movement · current value vs baseline",
            "recovery_snapshot": "Recovery · current values vs baseline", "sleep": "Sleep", "minutes": "minutes",
            "steps": "Steps", "steps_unit": "steps", "resting_hr": "Resting HR", "bpm": "bpm", "hrv": "HRV", "ms": "ms",
            "sleep_series": "Sleep · minutes asleep", "movement_series": "Movement · steps",
            "recovery_series": "Recovery · 100% = personal baseline", "wellbeing_series": "Wellbeing · 1–10 scale",
            "no_sleep": "No sleep data", "no_activity": "No activity data", "no_recovery": "Insufficient data for baseline comparison",
            "no_checkin": "No morning or evening check-in for this period", "percent_baseline": "% of baseline",
            "rating": "rating", "energy": "Energy", "focus": "Focus", "personal_dynamics": "Personal trends",
            "readiness": "readiness", "subtitle": "Dashed line: your 28-day baseline · estimate confidence: {confidence}",
            "daily_title": "Personal baseline as reference",
            "daily_subtitle": "Current values relative to your 28-day personal baseline",
            "daily_note": "White dot: personal baseline. Teal diamond: current value. Lower resting HR is treated as improvement.",
            "contribution_title": "What shaped today's readiness",
            "contribution_subtitle": "Each factor's contribution relative to your personal baseline",
            "contribution_axis": "points added to or removed from the readiness score",
            "contribution_base": "Starting point",
            "contribution_total": "Net contribution",
            "contribution_note": "An exploratory personal estimate, not a medical score.",
            "period": "Period",
        },
        "ru": {
            "date": "дата", "baseline": "Личная норма", "to_baseline": "к норме",
            "pp_to_baseline": "п.п. к норме", "no_baseline": "нет базы для сравнения",
            "no_record": "нет записи", "cannot_compare": "сравнение невозможно",
            "no_comparison": "Нет данных для сравнения", "baseline_axis": "% от личной нормы · 100% = твоя норма",
            "readiness_title": "Готовность · итоговая оценка", "readiness_empty": "Недостаточно данных для оценки готовности",
            "readiness_points": "баллы готовности", "unknown": "не определено",
            "components": "В оценке учтено компонентов: {count}",
            "components_no_checkin": "Субъективная оценка дня отсутствует · учтено компонентов: {count}",
            "sleep_snapshot": "Сон · текущий показатель против нормы", "movement_snapshot": "Движение · текущий показатель против нормы",
            "recovery_snapshot": "Восстановление · текущее против личной нормы", "sleep": "Сон", "minutes": "минут",
            "steps": "Шаги", "steps_unit": "шагов", "resting_hr": "Пульс покоя", "bpm": "уд/мин", "hrv": "ВСР", "ms": "мс",
            "sleep_series": "Сон · минуты сна", "movement_series": "Движение · шаги",
            "recovery_series": "Восстановление · 100% = личная норма", "wellbeing_series": "Самочувствие · шкала 1–10",
            "no_sleep": "Нет данных о сне", "no_activity": "Нет данных об активности", "no_recovery": "Недостаточно данных для сравнения с личной нормой",
            "no_checkin": "Нет утреннего или вечернего чек-ина за этот период", "percent_baseline": "% от нормы",
            "rating": "оценка", "energy": "Энергия", "focus": "Фокус", "personal_dynamics": "Персональная динамика",
            "readiness": "готовность", "subtitle": "Пунктир — твоя 28-дневная норма · уверенность оценки: {confidence}",
            "daily_title": "Личная норма как ориентир",
            "daily_subtitle": "Текущие значения относительно личной нормы за 28 дней",
            "daily_note": "Белая точка — личная норма. Бирюзовый ромб — текущее значение. Для пульса покоя шкала инвертирована.",
            "contribution_title": "Что повлияло на состояние",
            "contribution_subtitle": "Вклад каждого фактора относительно личной нормы",
            "contribution_axis": "пункты к итоговой оценке состояния",
            "contribution_base": "Стартовая точка",
            "contribution_total": "Суммарный вклад",
            "contribution_note": "Ориентировочная персональная оценка, не медицинский показатель.",
            "period": "Период",
        },
    }[locale]


def _date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _number(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _format_number(value: float) -> str:
    return f"{value:g}"


def _annotation_text(
    label: str,
    value: float,
    baseline: float | None,
    mode: str,
    unit: str,
    locale: Locale = "ru",
) -> str:
    copy = _copy(locale)
    if mode == "rating":
        main = f"{_format_number(value)}/10"
    elif mode == "percent":
        main = f"{_format_number(value)}%"
    else:
        main = f"{_format_number(value)} {unit}".strip()
    main = f"{label}: {main}"

    if baseline is None:
        return main
    if mode == "rating":
        delta = value - baseline
        delta_text = f"{delta:+.1f} {copy['to_baseline']}"
    elif mode == "percent":
        delta = value - baseline
        delta_text = f"{delta:+.1f} {copy['pp_to_baseline']}"
    elif baseline == 0:
        delta_text = copy["no_baseline"]
    else:
        delta = (value - baseline) / baseline * 100
        delta_text = f"{delta:+.1f}% {copy['to_baseline']}"
    return f"{main}\n{delta_text}"


def _period_label(period: DateRange) -> str:
    if period.start == period.end:
        return f"{period.start:%d.%m.%Y}"
    return f"{period.start:%d.%m.%Y} — {period.end:%d.%m.%Y}"


def _group_daily(rows: list[dict], value_key: str, mode: str = "mean") -> list[tuple[date, float]]:
    grouped: dict[date, list[float]] = defaultdict(list)
    for row in rows:
        value = _number(row.get(value_key))
        if value is None or row.get("record_date") is None:
            continue
        grouped[_date(row["record_date"])].append(value)
    result = []
    for day, values in sorted(grouped.items()):
        value = sum(values) if mode == "sum" else sum(values) / len(values)
        result.append((day, round(value, 1)))
    return result


def _productivity_series(context: dict, field: str) -> list[tuple[date, float]]:
    result = []
    for row in (context.get("productivity_context") or {}).get("days", []):
        value = None
        for checkin in (row.get("evening"), row.get("morning")):
            if checkin and checkin.get(field) is not None:
                value = _number(checkin[field])
                break
        if value is not None:
            result.append((_date(row["date"]), round(value, 1)))
    return result


def _recovery_series(context: dict, value_key: str, field: str, baseline_key: str) -> list[tuple[date, float]]:
    rows = context.get("health", {}).get(value_key, [])
    raw = _group_daily(rows, field)
    state = context.get("personal_state") or {}
    baseline = _number((state.get("baseline_28d") or {}).get(baseline_key))
    if baseline is None or baseline == 0:
        return []
    return [(day, round(value / baseline * 100, 1)) for day, value in raw]


def _style_axis(axis, title: str, ylabel: str, locale: Locale = "ru") -> None:
    axis.set_facecolor(PANEL)
    axis.set_title(title, color=FOREGROUND, loc="left", fontsize=12, pad=10)
    axis.set_ylabel(ylabel, color=MUTED, fontsize=9)
    axis.set_xlabel(_copy(locale)["date"], color=MUTED, fontsize=9)
    axis.tick_params(colors=FOREGROUND, labelsize=8)
    axis.grid(axis="y", color=GRID, linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    for spine in axis.spines.values():
        spine.set_color(GRID)


def _format_x_axis(axis, dates: list[date]) -> None:
    import matplotlib.dates as mdates

    if not dates:
        return
    minimum = min(dates)
    maximum = max(dates)
    minimum_num = mdates.date2num(minimum)
    maximum_num = mdates.date2num(maximum)
    if minimum == maximum:
        axis.set_xlim(minimum_num - 0.75, maximum_num + 0.75)
        axis.set_xticks([minimum])
    else:
        axis.set_xlim(minimum_num - 0.2, maximum_num + 0.2)
        span = (maximum - minimum).days
        axis.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, span // 6)))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    axis.tick_params(axis="x", labelrotation=0)


def _add_baseline(axis, value: float | None, label: str) -> None:
    if value is not None:
        axis.axhline(value, color=BASELINE, linestyle="--", linewidth=1.2, label=label)


def _plot_series_panel(
    axis,
    title: str,
    series: list[tuple[str, list[tuple[date, float]], str]],
    baselines: list[float | None],
    ylabel: str,
    empty_text: str,
    ylim: tuple[float, float] | None = None,
    annotation_modes: list[str] | None = None,
    units: list[str] | None = None,
    locale: Locale = "ru",
) -> None:
    copy = _copy(locale)
    _style_axis(axis, title, ylabel, locale)
    visible_dates: list[date] = []
    plotted = False
    for index, (label, values, color) in enumerate(series):
        if not values:
            continue
        plotted = True
        dates = [item[0] for item in values]
        numbers = [item[1] for item in values]
        visible_dates.extend(dates)
        axis.plot(
            dates,
            numbers,
            color=color,
            marker="o",
            markersize=5,
            linewidth=2,
            label=label,
        )
        baseline = baselines[index] if index < len(baselines) else None
        mode = annotation_modes[index] if annotation_modes and index < len(annotation_modes) else "absolute"
        unit = units[index] if units and index < len(units) else ""
        if baseline is not None:
            axis.fill_between(
                dates,
                numbers,
                baseline,
                color=color,
                alpha=0.08,
                interpolate=True,
            )
        if values:
            annotation = _annotation_text(label, numbers[-1], baseline, mode, unit, locale)
            if len(values) == 1:
                horizontal_offset = -8 if index % 2 == 0 else 8
                horizontal_alignment = "right" if index % 2 == 0 else "left"
            else:
                horizontal_offset = -5 - index * 80
                horizontal_alignment = "right"
            vertical_offset = 10 + index * 24
            if ylim is not None and numbers[-1] > ylim[1] - 12:
                vertical_offset = -12 - index * 24
            axis.annotate(
                annotation,
                (dates[-1], numbers[-1]),
                xytext=(horizontal_offset, vertical_offset),
                textcoords="offset points",
                ha=horizontal_alignment,
                color=FOREGROUND,
                fontsize=8.5,
                linespacing=1.2,
            )
        baseline_label = copy["baseline"] if not any(
            line.get_label().startswith(copy["baseline"]) for line in axis.lines
        ) else "_nolegend_"
        if baseline is not None and baseline_label != "_nolegend_":
            baseline_label = f"{copy['baseline']}: {baseline:g}"
        _add_baseline(
            axis,
            baseline,
            baseline_label,
        )
    if not plotted:
        axis.text(
            0.5,
            0.5,
            empty_text,
            transform=axis.transAxes,
            ha="center",
            va="center",
            color=MUTED,
            fontsize=10,
        )
        axis.set_xticks([])
        axis.set_yticks([])
        return
    if ylim is not None:
        axis.set_ylim(*ylim)
    _format_x_axis(axis, visible_dates)
    handles, labels = axis.get_legend_handles_labels()
    if handles:
        axis.legend(
            handles,
            labels,
            loc="upper left",
            fontsize=8,
            facecolor=PANEL,
            edgecolor=GRID,
            labelcolor=FOREGROUND,
        )


def _snapshot_ratio(current: float | None, baseline: float | None) -> float | None:
    if current is None or baseline in (None, 0):
        return None
    return round(current / baseline * 100, 1)


def _snapshot_value(current: float | None, unit: str, digits: int = 0, locale: Locale = "ru") -> str:
    if current is None:
        return _copy(locale)["no_record"]
    value = f"{current:.{digits}f}"
    return f"{value} {unit}".strip()


def _snapshot_delta(ratio: float | None, locale: Locale = "ru") -> str:
    if ratio is None:
        return _copy(locale)["cannot_compare"]
    return f"{ratio - 100:+.1f}% {_copy(locale)['to_baseline']}"


def _style_snapshot_axis(axis, title: str) -> None:
    axis.set_facecolor(PANEL)
    axis.set_title(title, color=FOREGROUND, loc="left", fontsize=12, pad=10)
    axis.tick_params(colors=FOREGROUND, labelsize=8)
    axis.grid(axis="x", color=GRID, linewidth=0.7, alpha=0.8)
    axis.set_axisbelow(True)
    for spine in axis.spines.values():
        spine.set_color(GRID)


def _plot_snapshot_comparison(
    axis,
    title: str,
    entries: list[tuple[str, float | None, str, str]],
    locale: Locale = "ru",
) -> None:
    """Show a compact current-vs-personal-norm comparison for one day."""
    _style_snapshot_axis(axis, title)
    valid = [entry for entry in entries if entry[1] is not None]
    if not valid:
        axis.text(
            0.5,
            0.5,
            _copy(locale)["no_comparison"],
            transform=axis.transAxes,
            ha="center",
            va="center",
            color=MUTED,
            fontsize=10,
        )
        axis.set_xticks([])
        axis.set_yticks([])
        return

    ratios = [entry[1] for entry in valid]
    minimum = min(80.0, min(ratios) - 5)
    maximum = max(120.0, max(ratios) + 5)
    axis.set_xlim(minimum, maximum)
    positions = list(range(len(valid)))[::-1]
    axis.set_yticks(positions, [entry[0] for entry in valid])
    axis.set_xlabel(_copy(locale)["baseline_axis"], color=MUTED, fontsize=9)
    axis.axvline(100, color=BASELINE, linestyle="--", linewidth=1.3, zorder=1)

    for position, (label, ratio, value_text, color) in zip(positions, valid):
        axis.hlines(position, minimum, maximum, color=GRID, linewidth=6, alpha=0.9, zorder=1)
        axis.hlines(
            position,
            min(100, ratio),
            max(100, ratio),
            color=color,
            linewidth=6,
            alpha=0.85,
            zorder=2,
        )
        axis.scatter([100], [position], color=BASELINE, marker="D", s=34, zorder=3)
        axis.scatter([ratio], [position], color=color, s=62, zorder=4)
        align_right = ratio > maximum - 15
        axis.annotate(
            f"{ratio:.1f}%\n{value_text} · {_snapshot_delta(ratio, locale)}",
            (ratio, position),
            xytext=(-7 if align_right else 7, 0),
            textcoords="offset points",
            ha="right" if align_right else "left",
            va="center",
            color=FOREGROUND,
            fontsize=8.5,
            linespacing=1.2,
        )


def _plot_readiness_snapshot(axis, context: dict, locale: Locale = "ru") -> None:
    copy = _copy(locale)
    _style_snapshot_axis(axis, copy["readiness_title"])
    state = context.get("personal_state") or {}
    readiness = state.get("readiness") or {}
    score = _number(readiness.get("score"))
    if score is None:
        axis.text(
            0.5,
            0.55,
            copy["readiness_empty"],
            transform=axis.transAxes,
            ha="center",
            va="center",
            color=MUTED,
            fontsize=10,
        )
        axis.set_xticks([])
        axis.set_yticks([])
        return

    status = readiness.get("status", copy["unknown"])
    if locale == "en":
        status = {"хорошее": "good", "сниженное": "reduced", "обычное": "typical"}.get(status, status)
    components = readiness.get("components_used", 0)
    current = state.get("current") or {}
    has_checkin = current.get("energy") is not None or current.get("focus") is not None
    axis.set_xlim(0, 100)
    axis.set_ylim(-0.6, 0.75)
    axis.set_yticks([])
    axis.set_xlabel(copy["readiness_points"], color=MUTED, fontsize=9)
    axis.barh(0, 100, height=0.22, color=GRID, alpha=0.75, zorder=1)
    axis.barh(0, score, height=0.22, color=SERIES[2], alpha=0.95, zorder=2)
    axis.scatter(
        [score],
        [0],
        color=FOREGROUND,
        edgecolors=SERIES[2],
        linewidths=2,
        s=78,
        zorder=3,
    )
    axis.text(
        0.5,
        0.72,
        f"{score:.0f}/100 · {status}",
        transform=axis.transAxes,
        ha="center",
        va="top",
        color=FOREGROUND,
        fontsize=15,
    )
    note = (
        copy["components"].format(count=components)
        if has_checkin
        else copy["components_no_checkin"].format(count=components)
    )
    axis.text(
        0.5,
        0.18,
        note,
        transform=axis.transAxes,
        ha="center",
        va="center",
        color=MUTED,
        fontsize=9,
    )


def _plot_single_day_dashboard(context: dict, axes, locale: Locale = "ru") -> None:
    copy = _copy(locale)
    state = context.get("personal_state") or {}
    current = state.get("current") or {}
    baseline = state.get("baseline_28d") or {}
    sleep_current = _number(current.get("sleep_minutes"))
    steps_current = _number(current.get("steps"))
    rhr_current = _number(current.get("resting_heart_rate"))
    hrv_current = _number(current.get("hrv_rmssd"))

    _plot_snapshot_comparison(
        axes[0, 0],
        copy["sleep_snapshot"],
        [
            (
                copy["sleep"],
                _snapshot_ratio(sleep_current, _number(baseline.get("sleep_minutes"))),
                _snapshot_value(sleep_current, copy["minutes"], locale=locale),
                SERIES[1],
            )
        ], locale,
    )
    _plot_snapshot_comparison(
        axes[0, 1],
        copy["movement_snapshot"],
        [
            (
                copy["steps"],
                _snapshot_ratio(steps_current, _number(baseline.get("steps"))),
                _snapshot_value(steps_current, copy["steps_unit"], locale=locale),
                SERIES[0],
            )
        ], locale,
    )
    _plot_snapshot_comparison(
        axes[1, 0],
        copy["recovery_snapshot"],
        [
            (
                copy["resting_hr"],
                _snapshot_ratio(rhr_current, _number(baseline.get("resting_heart_rate"))),
                _snapshot_value(rhr_current, copy["bpm"], locale=locale),
                SERIES[3],
            ),
            (
                copy["hrv"],
                _snapshot_ratio(hrv_current, _number(baseline.get("hrv_rmssd"))),
                _snapshot_value(hrv_current, copy["ms"], digits=1, locale=locale),
                SERIES[2],
            ),
        ], locale,
    )
    _plot_readiness_snapshot(axes[1, 1], context, locale)


def _generate_daily_contribution_chart(
    context: dict,
    target_dir: Path,
    report_type: str,
    period: DateRange,
    locale: Locale,
) -> list[Path]:
    import matplotlib.pyplot as plt

    state = context.get("personal_state") or {}
    readiness = state.get("readiness") or {}
    contributions = [
        item
        for item in readiness.get("contributions", [])
        if _number(item.get("points")) is not None
    ]
    if not contributions:
        logger.info("daily report chart skipped: no readiness contributions available")
        return []

    copy = _copy(locale)
    points = [float(item["points"]) for item in contributions]
    minimum = min(-16.0, min(points) - 2)
    maximum = max(10.0, max(points) + 2)
    positions = list(range(len(contributions)))[::-1]

    figure, axis = plt.subplots(figsize=(12, 7.2), dpi=150)
    figure.patch.set_facecolor(BACKGROUND)
    axis.set_facecolor(BACKGROUND)
    axis.set_position([0.23, 0.22, 0.60, 0.50])
    axis.set_xlim(minimum, maximum)
    axis.set_ylim(-0.7, len(contributions) - 0.3)
    axis.set_yticks(positions, [item.get("label", item.get("key", "")) for item in contributions])
    axis.tick_params(axis="y", colors=FOREGROUND, labelsize=14, length=0, pad=14)
    axis.tick_params(axis="x", colors=MUTED, labelsize=9, length=0, pad=9)
    axis.set_xlabel(copy["contribution_axis"], color=MUTED, fontsize=9.5, labelpad=12)
    axis.grid(axis="x", color=GRID, linewidth=0.7, alpha=0.7)
    axis.axvline(0, color=FOREGROUND, linewidth=1.2, alpha=0.75, zorder=2)
    for spine in axis.spines.values():
        spine.set_visible(False)

    score = _number(readiness.get("score"))
    base_score = _number(readiness.get("base_score")) or 50
    total_contribution = sum(points)
    figure.text(
        0.07,
        0.90,
        copy["contribution_title"],
        color=FOREGROUND,
        fontsize=27,
        fontweight="bold",
    )
    figure.text(
        0.07,
        0.842,
        copy["contribution_subtitle"],
        color=MUTED,
        fontsize=12.5,
    )
    if score is not None:
        figure.text(
            0.93,
            0.905,
            f"{score:g} / 100",
            color=ACCENT,
            fontsize=22,
            fontweight="bold",
            ha="right",
        )
    figure.text(
        0.93,
        0.855,
        _period_label(period),
        color=MUTED,
        fontsize=10.5,
        ha="right",
    )

    for position, item, value in zip(positions, contributions, points, strict=True):
        color = ACCENT if value > 0 else NEGATIVE if value < 0 else MUTED
        if value == 0:
            axis.scatter([0], [position], s=70, color=color, zorder=4)
        else:
            axis.barh(
                position,
                value,
                height=0.42,
                color=color,
                alpha=0.96,
                zorder=3,
            )
        value_text = f"{value:+g}" if value else "0"
        axis.text(
            value + (0.45 if value >= 0 else -0.45),
            position,
            value_text,
            color=FOREGROUND,
            fontsize=13,
            fontweight="bold",
            ha="left" if value >= 0 else "right",
            va="center",
        )

    total_text = f"{total_contribution:+g}" if total_contribution else "0"
    figure.text(
        0.07,
        0.105,
        f"{copy['contribution_base']}: {base_score:g}   ·   "
        f"{copy['contribution_total']}: {total_text}",
        color=FOREGROUND,
        fontsize=11.5,
        fontweight="bold",
    )
    figure.text(0.07, 0.055, copy["contribution_note"], color=MUTED, fontsize=9.5)
    figure.text(0.93, 0.045, "OwnVitals", color=GRID, fontsize=9.5, ha="right", fontweight="bold")

    path = target_dir / f"{report_type}-{period.start}-{period.end}.png"
    figure.savefig(path, facecolor=BACKGROUND)
    restrict_private_file(path)
    plt.close(figure)
    return [path]


def generate_report_charts(
    context: dict,
    target_dir: Path,
    report_type: str,
    period: DateRange,
    locale: Locale = "ru",
) -> list[Path]:
    """Create an annotated personal dashboard with current values and baselines."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning(
            "report charts skipped: matplotlib is not installed; "
            "install project dependencies with pip install -e ."
        )
        return []

    copy = _copy(locale)
    health = context.get("health", {})
    ensure_private_directory(target_dir)
    if period.start == period.end:
        return _generate_daily_contribution_chart(
            context, target_dir, report_type, period, locale
        )

    figure, axes = plt.subplots(2, 2, figsize=(13, 8))
    figure.patch.set_facecolor(BACKGROUND)
    figure.subplots_adjust(
        left=0.09,
        right=0.98,
        bottom=0.08,
        top=0.84,
        wspace=0.16,
        hspace=0.28,
    )

    sleep_series = _group_daily(health.get("sleep", []), "minutes_asleep", mode="sum")
    activity_series = _group_daily(health.get("activity", []), "steps", mode="sum")
    rhr_series = _recovery_series(
        context, "heart_rate", "resting_heart_rate", "resting_heart_rate"
    )
    hrv_series = _recovery_series(context, "hrv", "rmssd", "hrv_rmssd")
    energy_series = _productivity_series(context, "energy")
    focus_series = _productivity_series(context, "focus")

    _plot_series_panel(
        axes[0, 0],
        copy["sleep_series"],
        [(copy["sleep"], sleep_series, SERIES[1])],
        [
            _number(
                ((context.get("personal_state") or {}).get("baseline_28d") or {}).get(
                    "sleep_minutes"
                )
            )
        ],
        copy["minutes"],
        copy["no_sleep"],
        annotation_modes=["relative"],
        units=[copy["minutes"]],
        locale=locale,
    )
    _plot_series_panel(
        axes[0, 1],
        copy["movement_series"],
        [(copy["steps"], activity_series, SERIES[0])],
        [_number(((context.get("personal_state") or {}).get("baseline_28d") or {}).get("steps"))],
        copy["steps_unit"],
        copy["no_activity"],
        annotation_modes=["relative"],
        units=[copy["steps_unit"]],
        locale=locale,
    )
    _plot_series_panel(
        axes[1, 0],
        copy["recovery_series"],
        [
            (copy["resting_hr"], rhr_series, SERIES[3]),
            (copy["hrv"], hrv_series, SERIES[2]),
        ],
        [100.0, 100.0],
        copy["percent_baseline"],
        copy["no_recovery"],
        ylim=(75, 125),
        annotation_modes=["percent", "percent"],
        units=["%", "%"],
        locale=locale,
    )
    _plot_series_panel(
        axes[1, 1],
        copy["wellbeing_series"],
        [
            (copy["energy"], energy_series, SERIES[0]),
            (copy["focus"], focus_series, SERIES[2]),
        ],
        [
            _number(((context.get("personal_state") or {}).get("baseline_28d") or {}).get("energy")),
            _number(((context.get("personal_state") or {}).get("baseline_28d") or {}).get("focus")),
        ],
        copy["rating"],
        copy["no_checkin"],
        ylim=(0, 10.5),
        annotation_modes=["rating", "rating"],
        units=["", ""],
        locale=locale,
    )

    readiness = (context.get("personal_state") or {}).get("readiness") or {}
    score = readiness.get("score")
    status = readiness.get("status", copy["unknown"])
    if locale == "en":
        status = {"хорошее": "good", "сниженное": "reduced", "обычное": "typical"}.get(status, status)
    confidence_raw = readiness.get("confidence") or copy["unknown"]
    confidence = CONFIDENCE_LABELS[locale].get(confidence_raw, confidence_raw)
    title = f"{copy['personal_dynamics']} · {_period_label(period)}"
    if score is not None:
        title += f" · {copy['readiness']} {score}/100 ({status})"
    figure.suptitle(title, color=FOREGROUND, fontsize=17, y=0.97)
    figure.text(
        0.5,
        0.935,
        copy["subtitle"].format(confidence=confidence),
        ha="center",
        va="top",
        color=MUTED,
        fontsize=9,
    )
    path = target_dir / f"{report_type}-{period.start}-{period.end}.png"
    figure.savefig(path, dpi=160, facecolor=figure.get_facecolor())
    restrict_private_file(path)
    plt.close(figure)
    return [path]
