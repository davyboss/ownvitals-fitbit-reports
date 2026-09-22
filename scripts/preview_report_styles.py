from __future__ import annotations

import asyncio
import argparse
import html
import re
from dataclasses import dataclass
from pathlib import Path

from telegram import Bot

from fitbit_report.config import load_settings


MAX_MESSAGE_LENGTH = 3900


@dataclass(frozen=True)
class Claim:
    kind: str
    text: str
    meta: str


@dataclass(frozen=True)
class Report:
    title: str
    date: str
    dashboard: str
    summary: str
    claims: tuple[Claim, ...]
    recommendations: tuple[str, ...]
    experiments: tuple[str, ...]
    reliability: str


def _section(text: str, start: str, end: str | None = None) -> str:
    value = text.split(start, 1)[1]
    if end is not None:
        value = value.split(end, 1)[0]
    return value.strip()


def _bullet_items(text: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in re.split(r"(?m)^\s*•\s*", text)
        if item.strip()
    )


def _markdown_bullet_items(text: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in re.split(r"(?m)^\s*-\s+", text)
        if item.strip()
    )


def _parse_telegram_report(raw: str) -> Report:
    text = re.sub(r"(?m)^\[[^\n]+\] FitBit Reports:\s*", "", raw).strip()
    text = text.split("🧠 Если хочешь,", 1)[0].strip()

    title = re.search(r"📊\s*([^\n]+)", text).group(1).strip()
    date = re.search(r"📅\s*([^\n]+)", text).group(1).strip()
    dashboard = _section(text, "🧠 Персональная панель", "🧭 Главный вывод")
    summary = _section(text, "🧭 Главный вывод", "🔎 Наблюдения")
    observations = _section(text, "🔎 Наблюдения", "💡 Рекомендации")
    recommendations = _bullet_items(
        _section(text, "💡 Рекомендации", "🧪 Личный эксперимент")
    )
    experiments = _bullet_items(
        _section(text, "🧪 Личный эксперимент", "📌 Надёжность:")
    )
    reliability = _section(text, "📌 Надёжность:").strip()

    matches = list(
        re.finditer(r"(?m)^(?:✅\s*)?(Факт)|^(?:📈\s*)?(Ассоциация)|^(?:⚠️\s*)?(Гипотеза)", observations)
    )
    claims: list[Claim] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(observations)
        chunk = observations[match.start():end].strip()
        kind = next(group for group in match.groups() if group)
        chunk = re.sub(r"^(?:✅|📈|⚠️)\s*", "", chunk)
        chunk = re.sub(rf"^{kind}:\s*", "", chunk)
        body, meta = chunk.rsplit("\nУверенность:", 1)
        claims.append(Claim(kind, body.strip(), "Уверенность:" + meta.strip()))

    return Report(
        title=title,
        date=date,
        dashboard=dashboard,
        summary=summary,
        claims=tuple(claims),
        recommendations=recommendations,
        experiments=experiments,
        reliability=reliability,
    )


def _parse_markdown_report(raw: str) -> Report:
    text = re.sub(r"\A---\n.*?\n---\n", "", raw, flags=re.DOTALL).strip()
    title_match = re.search(r"(?m)^#\s+(.+)$", text)
    date_match = re.search(r"(?m)^_([^\n]+)_$", text)
    if title_match is None or date_match is None:
        raise ValueError("Markdown report must contain a title and period")

    summary_section = _section(text, "> [!summary] Главный вывод", "## Наблюдения")
    summary = "\n".join(
        line.removeprefix(">").strip()
        for line in summary_section.splitlines()
        if line.removeprefix(">").strip()
    )
    observations = _section(text, "## Наблюдения", "## Что попробовать")
    claim_matches = list(
        re.finditer(
            r"(?ms)^- \*\*(Факт|Ассоциация|Гипотеза)\*\*:\s*(.*?)(?=^- \*\*|\Z)",
            observations,
        )
    )
    claims: list[Claim] = []
    for match in claim_matches:
        kind, body = match.groups()
        meta_match = re.search(
            r"\s*\(уверенность:\s*([^,]+),\s*наблюдений:\s*(\d+)\)\s*$",
            body,
        )
        if meta_match is None:
            raise ValueError(f"Observation metadata is missing for {kind}")
        statement = body[:meta_match.start()].strip()
        confidence, count = meta_match.groups()
        claims.append(
            Claim(
                kind,
                statement,
                f"Уверенность: {confidence.strip()} · Наблюдений: {count}",
            )
        )

    recommendations = _markdown_bullet_items(
        _section(text, "## Что попробовать", "## Личный эксперимент")
    )
    experiments = _markdown_bullet_items(
        _section(text, "## Личный эксперимент", "## Надёжность вывода")
    )
    reliability_section = _section(text, "## Надёжность вывода")
    reliability = reliability_section.split("## ", 1)[0].strip()
    reliability = re.sub(r"^Уверенность:\s*", "", reliability).rstrip(".")

    return Report(
        title=title_match.group(1).strip(),
        date=date_match.group(1).strip(),
        dashboard="",
        summary=summary,
        claims=tuple(claims),
        recommendations=recommendations,
        experiments=experiments,
        reliability=reliability,
    )


def parse_report(raw: str) -> Report:
    if "📊" in raw and "🔎 Наблюдения" in raw:
        return _parse_telegram_report(raw)
    if "## Наблюдения" in raw and "> [!summary] Главный вывод" in raw:
        return _parse_markdown_report(raw)
    raise ValueError("Unsupported report format: use a Telegram export or OwnVitals Markdown report")


def e(value: str) -> str:
    return html.escape(value, quote=False)


def pack_blocks(blocks: list[str]) -> list[str]:
    messages: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Preview block is too long: {len(block)} characters")
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= MAX_MESSAGE_LENGTH:
            current = candidate
        else:
            messages.append(current)
            current = block
    if current:
        messages.append(current)
    return messages


def editorial(report: Report) -> list[str]:
    rule = "────────────"
    blocks = [
        f"<b>ВАРИАНТ 1/5 · РЕДАКЦИОННЫЙ</b>\n\n<b>{e(report.title.upper())}</b>\n<i>{e(report.date)}</i>",
    ]
    if report.dashboard:
        blocks.append(f"<b>ПЕРСОНАЛЬНАЯ ПАНЕЛЬ</b>\n\n{e(report.dashboard)}")
    blocks.extend([
        f"{rule}\n\n<b>ГЛАВНЫЙ ВЫВОД</b>\n\n<blockquote>{e(report.summary)}</blockquote>",
        f"{rule}\n\n<b>НАБЛЮДЕНИЯ</b>",
    ])
    for index, claim in enumerate(report.claims, 1):
        blocks.append(
            f"<b>{index:02d}  {e(claim.kind.upper())}</b>\n\n{e(claim.text)}\n\n<i>{e(claim.meta)}</i>"
        )
    blocks.extend([
        f"{rule}\n\n<b>РЕКОМЕНДАЦИИ</b>\n\n"
        + "\n\n".join(f"{i:02d}  {e(item)}" for i, item in enumerate(report.recommendations, 1)),
        f"{rule}\n\n<b>ЛИЧНЫЙ ЭКСПЕРИМЕНТ</b>\n\n"
        + "\n\n".join(f"{i:02d}  {e(item)}" for i, item in enumerate(report.experiments, 1)),
        f"{rule}\n\n<b>НАДЁЖНОСТЬ</b>\n\n{e(report.reliability)}",
    ])
    return pack_blocks(blocks)


def cards(report: Report) -> list[str]:
    blocks = [
        f"<b>ВАРИАНТ 2/5 · МОНОХРОМНЫЕ БЛОКИ</b>\n\n<b>{e(report.title)}</b>\n<i>{e(report.date)}</i>",
    ]
    if report.dashboard:
        blocks.append(f"<b>Персональная панель</b>\n<blockquote>{e(report.dashboard)}</blockquote>")
    blocks.extend([
        f"<b>Главный вывод</b>\n<blockquote>{e(report.summary)}</blockquote>",
        "<b>Наблюдения</b>",
    ])
    for index, claim in enumerate(report.claims, 1):
        blocks.append(
            f"<b>{e(claim.kind)} {index}</b>\n<blockquote>{e(claim.text)}\n\n<i>{e(claim.meta)}</i></blockquote>"
        )
    blocks.extend([
        "<b>Рекомендации</b>\n<blockquote>"
        + "\n\n".join(f"{i}. {e(item)}" for i, item in enumerate(report.recommendations, 1))
        + "</blockquote>",
        "<b>Личный эксперимент</b>\n<blockquote>"
        + "\n\n".join(f"{i}. {e(item)}" for i, item in enumerate(report.experiments, 1))
        + "</blockquote>",
        f"<b>Надёжность</b>\n<blockquote>{e(report.reliability)}</blockquote>",
    ])
    return pack_blocks(blocks)


def indexed(report: Report) -> list[str]:
    blocks = [
        f"<b>ВАРИАНТ 3/5 · НУМЕРОВАННЫЙ</b>\n\n<b>{e(report.title.upper())}</b>\n<i>{e(report.date)}</i>",
    ]
    if report.dashboard:
        blocks.append(f"<b>01 / ПЕРСОНАЛЬНАЯ ПАНЕЛЬ</b>\n\n{e(report.dashboard)}")
    blocks.extend([
        f"<b>02 / ГЛАВНЫЙ ВЫВОД</b>\n\n{e(report.summary)}",
        "<b>03 / НАБЛЮДЕНИЯ</b>",
    ])
    for index, claim in enumerate(report.claims, 1):
        blocks.append(
            f"<b>{e(claim.kind.upper())} · {index:02d}</b>\n\n{e(claim.text)}\n\n<i>{e(claim.meta)}</i>"
        )
    blocks.extend([
        "<b>04 / РЕКОМЕНДАЦИИ</b>\n\n"
        + "\n\n".join(f"{i:02d} — {e(item)}" for i, item in enumerate(report.recommendations, 1)),
        "<b>05 / ЛИЧНЫЙ ЭКСПЕРИМЕНТ</b>\n\n"
        + "\n\n".join(f"{i:02d} — {e(item)}" for i, item in enumerate(report.experiments, 1)),
        f"<b>06 / НАДЁЖНОСТЬ</b>\n\n{e(report.reliability)}",
    ])
    return pack_blocks(blocks)


def scientific(report: Report) -> list[str]:
    blocks = [
        f"<b>ВАРИАНТ 4/5 · АНАЛИТИЧЕСКИЙ ПРОТОКОЛ</b>\n\n<b>{e(report.title.upper())}</b>\nПериод: {e(report.date)}",
    ]
    if report.dashboard:
        blocks.append(f"<b>СВОДКА СОСТОЯНИЯ</b>\n\n<pre>{e(report.dashboard)}</pre>")
    blocks.extend([
        f"<b>ГЛАВНЫЙ ВЫВОД</b>\n\n{e(report.summary)}",
        "<b>НАБЛЮДЕНИЯ</b>",
    ])
    for index, claim in enumerate(report.claims, 1):
        meta = claim.meta.replace(" · ", "\n")
        blocks.append(
            f"<b>НАБЛЮДЕНИЕ {index:02d}</b>\n\n"
            f"Тип: {e(claim.kind.lower())}\n{e(meta)}\n\n{e(claim.text)}"
        )
    blocks.extend([
        "<b>РЕКОМЕНДАЦИИ</b>\n\n"
        + "\n\n".join(f"[{i}] {e(item)}" for i, item in enumerate(report.recommendations, 1)),
        "<b>ЛИЧНЫЙ ЭКСПЕРИМЕНТ</b>\n\n"
        + "\n\n".join(f"Протокол {i}\n{e(item)}" for i, item in enumerate(report.experiments, 1)),
        f"<b>ОБЩАЯ НАДЁЖНОСТЬ</b>\n\n{e(report.reliability)}",
    ])
    return pack_blocks(blocks)


def quiet(report: Report) -> list[str]:
    blocks = [
        f"<b>ВАРИАНТ 5/5 · СПОКОЙНЫЙ</b>\n\n<b>{e(report.title)}</b>\n<i>{e(report.date)}</i>",
    ]
    if report.dashboard:
        blocks.append(f"<b>Состояние</b>\n\n{e(report.dashboard)}")
    blocks.extend([
        f"<b>Главный вывод</b>\n\n{e(report.summary)}",
        "<b>Наблюдения</b>",
    ])
    for claim in report.claims:
        blocks.append(
            f"<b>{e(claim.kind)}</b>\n\n{e(claim.text)}\n\n<i>{e(claim.meta)}</i>"
        )
    blocks.extend([
        "<b>Рекомендации</b>\n\n" + "\n\n".join(e(item) for item in report.recommendations),
        "<b>Личный эксперимент</b>\n\n" + "\n\n".join(e(item) for item in report.experiments),
        f"<b>Надёжность</b>\n\n<i>{e(report.reliability)}</i>",
    ])
    return pack_blocks(blocks)


async def main(source: Path) -> None:
    settings = load_settings()
    report = parse_report(source.read_text(encoding="utf-8"))
    variants = [editorial(report), cards(report), indexed(report), scientific(report), quiet(report)]

    async with Bot(token=settings.telegram_bot_token) as bot:
        await bot.send_message(
            chat_id=settings.telegram_allowed_chat_id,
            text=(
                "Ниже пять вариантов оформления одного и того же отчёта. "
                "Содержание сохранено полностью; меняется только визуальная подача."
            ),
        )
        await asyncio.sleep(1)
        for variant in variants:
            for message in variant:
                await bot.send_message(
                    chat_id=settings.telegram_allowed_chat_id,
                    text=message,
                    parse_mode="HTML",
                )
                await asyncio.sleep(1)

    print(f"Sent {sum(len(variant) for variant in variants)} preview messages across 5 variants")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Send five visual variants of a pasted OwnVitals report to Telegram."
    )
    parser.add_argument("source", type=Path, help="UTF-8 text file containing the pasted report")
    args = parser.parse_args()
    asyncio.run(main(args.source))
