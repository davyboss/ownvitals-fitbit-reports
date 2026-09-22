from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitbit_report.private_storage import ensure_private_directory, write_private_bytes

MAX_FATSECRET_PDF_BYTES = 10 * 1024 * 1024
MAX_FATSECRET_PDF_PAGES = 50
MAX_FATSECRET_PDF_TEXT_CHARS = 1_000_000


class FatSecretParseError(ValueError):
    pass


@dataclass(frozen=True)
class FatSecretFood:
    meal_type: str
    food_name: str
    serving: str | None
    calories: float | None
    fat_g: float | None
    saturated_fat_g: float | None
    carbohydrates_g: float | None
    fiber_g: float | None
    sugar_g: float | None
    protein_g: float | None
    sodium_mg: float | None
    cholesterol_mg: float | None
    potassium_mg: float | None


@dataclass(frozen=True)
class FatSecretDiary:
    report_date: date
    foods: list[FatSecretFood]
    raw_text: str


def is_fatsecret_pdf_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").casefold()
    return (
        parsed.scheme == "https"
        and (host == "fatsecret.com" or host.endswith(".fatsecret.com"))
        and parsed.path.casefold().endswith(".pdf")
    )


@dataclass(frozen=True)
class FatSecretImportSummary:
    report_date: date
    food_count: int
    meal_count: int
    pdf_path: Path


@dataclass(frozen=True)
class FatSecretApiImportSummary:
    report_date: date
    food_count: int
    meal_count: int


def import_fatsecret_url(
    url: str,
    engine,
    report_dir: Path,
    session_factory,
) -> FatSecretImportSummary:
    """Download, parse and persist one FatSecret daily export."""
    if not is_fatsecret_pdf_url(url):
        raise FatSecretParseError("Нужна прямая ссылка на PDF-отчёт FatSecret")

    import httpx

    chunks: list[bytes] = []
    downloaded = 0
    # A diary URL is an operator-supplied network destination. Do not follow
    # redirects: an otherwise valid FatSecret URL must never turn into a
    # request to localhost, cloud metadata, or another untrusted host.
    with httpx.Client(timeout=45, follow_redirects=False) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = 0
                if declared_size > MAX_FATSECRET_PDF_BYTES:
                    raise FatSecretParseError(
                        "PDF FatSecret слишком большой. Максимальный размер — 10 МБ"
                    )
            for chunk in response.iter_bytes():
                downloaded += len(chunk)
                if downloaded > MAX_FATSECRET_PDF_BYTES:
                    raise FatSecretParseError(
                        "PDF FatSecret слишком большой. Максимальный размер — 10 МБ"
                    )
                chunks.append(chunk)
    return import_fatsecret_pdf_bytes(
        b"".join(chunks),
        url,
        engine,
        report_dir,
        session_factory,
    )


def import_fatsecret_pdf_bytes(
    pdf_bytes: bytes,
    source_url: str,
    engine,
    report_dir: Path,
    session_factory,
) -> FatSecretImportSummary:
    """Parse and persist a FatSecret PDF already downloaded by Telegram."""
    if not pdf_bytes:
        raise FatSecretParseError("Получен пустой PDF-файл FatSecret")
    if len(pdf_bytes) > MAX_FATSECRET_PDF_BYTES:
        raise FatSecretParseError(
            "PDF FatSecret слишком большой. Максимальный размер — 10 МБ"
        )
    if not pdf_bytes.lstrip().startswith(b"%PDF-"):
        raise FatSecretParseError("Файл не похож на PDF-отчёт FatSecret")
    source_url = source_url.strip()
    if not source_url:
        digest = hashlib.sha256(pdf_bytes).hexdigest()[:24]
        source_url = f"telegram://fatsecret/{digest}"

    diary = extract_fatsecret_pdf(pdf_bytes, source_url)
    ensure_private_directory(report_dir)
    digest = hashlib.sha256(pdf_bytes).hexdigest()[:12]
    pdf_path = report_dir / f"{diary.report_date.isoformat()}-{digest}.pdf"
    write_private_bytes(pdf_path, pdf_bytes)

    _persist_diary(
        diary,
        source_url,
        pdf_path.as_posix(),
        engine,
        session_factory,
    )

    return FatSecretImportSummary(
        report_date=diary.report_date,
        food_count=len(diary.foods),
        meal_count=len({food.meal_type for food in diary.foods}),
        pdf_path=pdf_path,
    )


def import_fatsecret_api_entries(
    report_date: date,
    entries: list[object],
    raw_payload: dict[str, object],
    engine,
    session_factory,
) -> FatSecretApiImportSummary:
    """Persist the exact diary entries returned by FatSecret OAuth API."""
    from fitbit_report.journal.fatsecret_oauth import FatSecretDiaryEntry

    foods = []
    for entry in entries:
        if not isinstance(entry, FatSecretDiaryEntry):
            continue
        foods.append(
            FatSecretFood(
                meal_type=entry.meal_type,
                food_name=entry.food_name,
                serving=entry.serving,
                calories=entry.calories,
                fat_g=entry.fat_g,
                saturated_fat_g=entry.saturated_fat_g,
                carbohydrates_g=entry.carbohydrates_g,
                fiber_g=entry.fiber_g,
                sugar_g=entry.sugar_g,
                protein_g=entry.protein_g,
                sodium_mg=entry.sodium_mg,
                cholesterol_mg=entry.cholesterol_mg,
                potassium_mg=entry.potassium_mg,
            )
        )
    source_url = f"fatsecret-api://food-entries/{report_date.isoformat()}"
    diary = FatSecretDiary(
        report_date=report_date,
        foods=foods,
        raw_text=json.dumps(raw_payload, ensure_ascii=False, sort_keys=True),
    )
    _persist_diary(diary, source_url, source_url, engine, session_factory)
    return FatSecretApiImportSummary(
        report_date=report_date,
        food_count=len(foods),
        meal_count=len({food.meal_type for food in foods}),
    )


def _persist_diary(
    diary: FatSecretDiary,
    source_url: str,
    stored_path: str,
    engine,
    session_factory,
) -> None:
    from fitbit_report.db.models import FatSecretFoodEntry, FatSecretImport, MealTimeLog

    with session_factory(engine) as session:
        record = session.scalar(
            select(FatSecretImport).where(FatSecretImport.source_url == source_url)
        )
        if record is None:
            record = FatSecretImport(
                report_date=diary.report_date,
                source_url=source_url,
                pdf_path=stored_path,
                raw_text=diary.raw_text,
                status="success",
            )
            session.add(record)
            session.flush()
        else:
            session.query(FatSecretFoodEntry).filter(
                FatSecretFoodEntry.import_id == record.id
            ).delete(synchronize_session=False)
            record.report_date = diary.report_date
            record.pdf_path = stored_path
            record.raw_text = diary.raw_text
            record.status = "success"
            record.error_message = None
            record.created_at = datetime.now(timezone.utc)

        slots = list(
            session.scalars(
                select(MealTimeLog)
                .where(MealTimeLog.meal_date == diary.report_date)
                .order_by(MealTimeLog.created_at.desc())
            )
        )
        slot_by_type: dict[str, MealTimeLog] = {}
        for slot in slots:
            slot_by_type.setdefault(slot.meal_type, slot)

        for food in diary.foods:
            slot = slot_by_type.get(food.meal_type)
            session.add(
                FatSecretFoodEntry(
                    import_id=record.id,
                    report_date=diary.report_date,
                    meal_type=food.meal_type,
                    meal_time=slot.occurred_at if slot else None,
                    food_name=food.food_name,
                    serving=food.serving,
                    calories=food.calories,
                    fat_g=food.fat_g,
                    saturated_fat_g=food.saturated_fat_g,
                    carbohydrates_g=food.carbohydrates_g,
                    fiber_g=food.fiber_g,
                    sugar_g=food.sugar_g,
                    protein_g=food.protein_g,
                    sodium_mg=food.sodium_mg,
                    cholesterol_mg=food.cholesterol_mg,
                    potassium_mg=food.potassium_mg,
                )
            )


def latest_fatsecret_entries(
    session: Session, start: date, end: date
) -> list[object]:
    from fitbit_report.db.models import FatSecretFoodEntry, FatSecretImport

    imports = list(
        session.scalars(
            select(FatSecretImport)
            .where(
                FatSecretImport.report_date >= start,
                FatSecretImport.report_date <= end,
                FatSecretImport.status == "success",
            )
            .order_by(FatSecretImport.created_at.desc())
        )
    )
    latest_by_date = {}
    for item in imports:
        latest_by_date.setdefault(item.report_date, item.id)
    if not latest_by_date:
        return []
    return list(
        session.scalars(
            select(FatSecretFoodEntry)
            .where(
                FatSecretFoodEntry.import_id.in_(list(latest_by_date.values())),
                FatSecretFoodEntry.report_date >= start,
                FatSecretFoodEntry.report_date <= end,
            )
            .order_by(FatSecretFoodEntry.report_date, FatSecretFoodEntry.meal_time, FatSecretFoodEntry.id)
        )
    )


_MEAL_HEADINGS = {
    "breakfast": "breakfast",
    "завтрак": "breakfast",
    "lunch": "lunch",
    "обед": "lunch",
    "dinner": "dinner",
    "ужин": "dinner",
    "snacks/other": "snack",
    "snacks / other": "snack",
    "snacks": "snack",
    "snack": "snack",
    "snacks & other": "snack",
    "snacks and other": "snack",
    "перекусы/другое": "snack",
    "перекусы / другое": "snack",
    "перекусы": "snack",
    "закуски": "snack",
    "перекус": "snack",
    "другое": "other",
}
_NUMBER_LINE_RE = re.compile(
    r"^\s*(?:[-+]?\d+(?:[.,]\d+)?|[-–—])(?:\s+(?:[-+]?\d+(?:[.,]\d+)?|[-–—]))*\s*$"
)
_DATE_IN_FILENAME_RE = re.compile(r"FoodDiary_(\d{6})", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_SKIP_LINES = {
    "food diary report - detailed report",
    "foods.fatsecret.com",
    "cals",
    "fat",
    "sat",
    "carbs",
    "fiber",
    "sugar",
    "prot",
    "sod",
    "chol",
    "potas",
    "food",
    "serving",
    "portion",
    "meal",
    "calories",
    "carbohydrates",
    "protein",
    "total",
}

_EMPTY_NUMBER_TOKENS = {"-"}
_TOTAL_LABELS = {"total", "всего"}


def _normalized_line(line: str) -> str:
    return " ".join(
        line.replace("\u00a0", " ")
        .replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
        .split()
    )


def _number_tokens(line: str) -> list[float]:
    normalized = _normalized_line(line)
    if not _NUMBER_LINE_RE.fullmatch(normalized):
        return []
    values: list[float] = []
    for token in normalized.split():
        if token in _EMPTY_NUMBER_TOKENS:
            values.append(0.0)
        else:
            values.append(float(token.replace(",", ".")))
    return values


def _normalize_lines(text: str) -> list[str]:
    return [
        normalized
        for line in text.replace("\r", "").splitlines()
        if (normalized := _normalized_line(line))
    ]


def _date_from_source(source_url: str, text: str) -> date:
    filename = unquote(Path(urlparse(source_url).path).name)
    match = _DATE_IN_FILENAME_RE.search(filename)
    if match:
        raw = match.group(1)
        return date(2000 + int(raw[:2]), int(raw[2:4]), int(raw[4:6]))

    match = _DATE_RE.search(text)
    if match:
        year, month, day = (int(value) for value in match.groups())
        return date(year, month, day)
    raise FatSecretParseError("Не удалось определить дату в PDF FatSecret")


def _is_technical_line(line: str) -> bool:
    normalized = _normalized_line(line).casefold()
    return (
        normalized in _SKIP_LINES
        or normalized.startswith("page ")
        or normalized.startswith("food diary report")
        or normalized.startswith("period summary")
        or normalized.startswith("daily average")
    )


def _meal_type(line: str) -> str | None:
    normalized = _normalized_line(line).casefold().rstrip(":")
    if normalized in _MEAL_HEADINGS:
        return _MEAL_HEADINGS[normalized]
    return None


def _is_total_row(line: str) -> bool:
    words = _normalized_line(line).casefold().split(maxsplit=1)
    return bool(words) and words[0] in _TOTAL_LABELS


def _consume_numeric_lines(lines: list[str], index: int) -> tuple[list[float], int]:
    values: list[float] = []
    while index < len(lines):
        tokens = _number_tokens(lines[index])
        if not tokens:
            break
        values.extend(tokens)
        index += 1
    return values, index


def _inline_food_row(line: str) -> tuple[str, list[float]] | None:
    """Read a row when pypdf keeps the food and nutrients on one line."""
    if _is_total_row(line):
        return None
    tokens = _normalized_line(line).split()
    if len(tokens) < 3:
        return None
    for candidate in range(1, len(tokens)):
        suffix = _number_tokens(" ".join(tokens[candidate:]))
        if len(suffix) >= 2:
            food_name = " ".join(tokens[:candidate]).strip()
            if not food_name or food_name.casefold() in _TOTAL_LABELS:
                return None
            return food_name, suffix
    return None


def _food_from_values(
    meal_type: str,
    food_name: str,
    values: list[float],
    serving: str | None = None,
) -> FatSecretFood:
    values = values[:10]
    return FatSecretFood(
        meal_type=meal_type,
        food_name=food_name,
        serving=serving,
        calories=values[0],
        fat_g=values[1],
        saturated_fat_g=values[2],
        carbohydrates_g=values[3],
        fiber_g=values[4],
        sugar_g=values[5],
        protein_g=values[6],
        sodium_mg=values[7],
        cholesterol_mg=values[8],
        potassium_mg=values[9],
    )


def _food_from_partial_values(
    meal_type: str,
    food_name: str,
    values: list[float],
    serving: str | None = None,
) -> FatSecretFood:
    """Persist a food when FatSecret omitted trailing nutrient columns.

    Some exports leave blank nutrient cells out of the extracted text entirely.
    The first value remains calories, while assigning the remaining compacted
    values to nutrient columns would be less accurate than leaving them unknown.
    """
    return FatSecretFood(
        meal_type=meal_type,
        food_name=food_name,
        serving=serving,
        calories=values[0],
        fat_g=None,
        saturated_fat_g=None,
        carbohydrates_g=None,
        fiber_g=None,
        sugar_g=None,
        protein_g=None,
        sodium_mg=None,
        cholesterol_mg=None,
        potassium_mg=None,
    )


def parse_fatsecret_text(text: str, source_url: str) -> FatSecretDiary:
    lines = _normalize_lines(text)
    report_date = _date_from_source(source_url, text)
    foods: list[FatSecretFood] = []
    current_meal: str | None = None
    index = 0

    while index < len(lines):
        line = lines[index]
        meal_type = _meal_type(line)
        if meal_type is not None:
            current_meal = meal_type
            index += 1
            continue
        if current_meal is None or _is_technical_line(line) or _number_tokens(line):
            index += 1
            continue
        if _is_total_row(line):
            _, index = _consume_numeric_lines(lines, index + 1)
            continue

        inline_row = _inline_food_row(line)
        if inline_row is not None:
            food_name, values = inline_row
            if len(values) >= 10:
                foods.append(_food_from_values(current_meal, food_name, values))
            else:
                foods.append(_food_from_partial_values(current_meal, food_name, values))
            index += 1
            continue

        food_name = line
        values, value_end = _consume_numeric_lines(lines, index + 1)
        serving = None
        if len(values) < 10 and index + 1 < len(lines):
            # Depending on the PDF generator, FatSecret may place the serving
            # directly before the nutrient columns instead of after them.
            candidate = lines[index + 1]
            if (
                _meal_type(candidate) is None
                and not _is_technical_line(candidate)
                and not _number_tokens(candidate)
                and not _is_total_row(candidate)
            ):
                candidate_values, candidate_end = _consume_numeric_lines(
                    lines, index + 2
                )
                if len(candidate_values) >= 10:
                    serving = candidate
                    values, value_end = candidate_values, candidate_end
        if len(values) < 10:
            index += 1
            continue

        if serving is None and value_end < len(lines):
            candidate = lines[value_end]
            if (
                _meal_type(candidate) is None
                and not _is_technical_line(candidate)
                and not _number_tokens(candidate)
                and not _is_total_row(candidate)
            ):
                serving = candidate
                value_end += 1

        foods.append(_food_from_values(current_meal, food_name, values, serving))
        index = value_end

    if not foods:
        raise FatSecretParseError("В PDF FatSecret не найдены продукты")
    return FatSecretDiary(report_date=report_date, foods=foods, raw_text=text)


def extract_fatsecret_pdf(pdf_bytes: bytes, source_url: str) -> FatSecretDiary:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise FatSecretParseError(
            "Не установлен pypdf. Выполни: pip install -e ."
        ) from exc

    reader = PdfReader(BytesIO(pdf_bytes))
    if reader.is_encrypted:
        raise FatSecretParseError("Зашифрованные PDF FatSecret не поддерживаются")
    if len(reader.pages) > MAX_FATSECRET_PDF_PAGES:
        raise FatSecretParseError(
            f"В PDF FatSecret слишком много страниц. Максимум — {MAX_FATSECRET_PDF_PAGES}"
        )
    extracted_any_text = False
    for extraction_mode in (None, "layout"):
        pages: list[str] = []
        extracted_chars = 0
        for page in reader.pages:
            if extraction_mode is None:
                chars_before_page = extracted_chars

                def count_text(
                    text: str,
                    _current_transform,
                    _text_matrix,
                    _font_dictionary,
                    _font_size,
                ) -> None:
                    nonlocal extracted_chars
                    extracted_chars += len(text)
                    if extracted_chars > MAX_FATSECRET_PDF_TEXT_CHARS:
                        raise FatSecretParseError(
                            "В PDF FatSecret слишком много текста для безопасной обработки"
                        )

                page_text = page.extract_text(visitor_text=count_text) or ""
                extracted_chars = max(
                    extracted_chars,
                    chars_before_page + len(page_text),
                )
            else:
                page_text = page.extract_text(extraction_mode=extraction_mode) or ""
                extracted_chars += len(page_text)
            if extracted_chars > MAX_FATSECRET_PDF_TEXT_CHARS:
                raise FatSecretParseError(
                    "В PDF FatSecret слишком много текста для безопасной обработки"
                )
            pages.append(page_text)
        text = "\n".join(pages)
        if not text.strip():
            continue
        extracted_any_text = True
        try:
            return parse_fatsecret_text(text, source_url)
        except FatSecretParseError:
            continue
    if not extracted_any_text:
        raise FatSecretParseError("PDF FatSecret не содержит извлекаемого текста")
    raise FatSecretParseError(
        "В PDF FatSecret не найдены продукты. Попробуй отправить сам PDF-файл из приложения, а не скриншот."
    )
