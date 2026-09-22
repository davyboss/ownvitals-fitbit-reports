import re
import shlex
from datetime import datetime, time
from zoneinfo import ZoneInfo

from fitbit_report.journal.schemas import JournalEventInput, ProductivityCheckinInput


AMOUNT_RE = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>[A-Za-zА-Яа-я]+)$")
CHECKIN_FIELDS = {
    "energy",
    "sleep_quality",
    "persistence",
    "quality",
    "focus",
    "mood",
    "stress",
    "deep_work_min",
    "priority",
    "note",
}


def parse_log_command(text: str, now: datetime, timezone: ZoneInfo) -> JournalEventInput:
    tokens = shlex.split(text)
    if len(tokens) < 2 or tokens[0] != "/log":
        raise ValueError("Expected /log <category> ...")
    category = tokens[1]
    if category in {"caffeine", "nicotine"}:
        return _parse_consumable(tokens, now, timezone, text)
    if category == "training":
        values = _parse_key_values(tokens[2:], {"duration", "intensity", "note", "at"})
        return JournalEventInput(
            category=category,
            occurred_at=_occurred_at(values.get("at"), now, timezone),
            duration_min=int(values["duration"]) if "duration" in values else None,
            intensity=float(values["intensity"]) if "intensity" in values else None,
            note=values.get("note"),
            original_text=text,
        )
    if category == "meal":
        return _parse_meal(tokens, now, timezone, text)
    if category in {
        "note",
        "mood",
        "stress",
        "illness",
        "alcohol",
        "masturbation",
        "sexual_activity",
    }:
        return JournalEventInput(
            category=category,
            occurred_at=now.astimezone(timezone),
            note=" ".join(tokens[2:]),
            original_text=text,
        )
    raise ValueError(f"Unsupported journal category: {category}")


def _parse_meal(
    tokens: list[str], now: datetime, timezone: ZoneInfo, original_text: str
) -> JournalEventInput:
    if len(tokens) < 4:
        raise ValueError("Expected /log meal breakfast|lunch|dinner|snack <description>")
    subtype = tokens[2]
    if subtype not in {"breakfast", "lunch", "dinner", "snack", "other"}:
        raise ValueError("Meal type must be breakfast, lunch, dinner, snack, or other")
    description = tokens[3:]
    at_value = None
    if len(description) >= 2 and description[-2] == "at":
        at_value = description[-1]
        description = description[:-2]
    if not description:
        raise ValueError("Meal description is required")
    return JournalEventInput(
        category="meal",
        subtype=subtype,
        occurred_at=_occurred_at(at_value, now, timezone),
        note=" ".join(description),
        original_text=original_text,
    )


def parse_checkin_command(text: str, now: datetime, timezone: ZoneInfo) -> ProductivityCheckinInput:
    tokens = shlex.split(text)
    if len(tokens) < 2 or tokens[0] != "/checkin" or tokens[1] not in {"morning", "evening"}:
        raise ValueError("Expected /checkin morning|evening key=value ...")
    values = _parse_key_values(tokens[2:], CHECKIN_FIELDS)
    converted: dict[str, object] = {
        "local_date": now.astimezone(timezone).date(),
        "period": tokens[1],
        "original_text": text,
    }
    integer_fields = {"energy", "sleep_quality", "persistence", "quality", "focus", "mood", "stress", "deep_work_min"}
    for key, value in values.items():
        if key in integer_fields:
            converted["work_quality" if key == "quality" else key] = int(value)
        else:
            converted[key] = value
    return ProductivityCheckinInput(**converted)


def _parse_consumable(
    tokens: list[str], now: datetime, timezone: ZoneInfo, original_text: str
) -> JournalEventInput:
    category = tokens[1]
    index = 2
    subtype = None
    if category == "nicotine" and index < len(tokens) and "=" not in tokens[index]:
        subtype = tokens[index]
        index += 1
    if index >= len(tokens):
        raise ValueError("A quantity is required")
    match = AMOUNT_RE.fullmatch(tokens[index])
    if not match:
        raise ValueError("Quantity must look like 150mg or 12mg")
    index += 1
    dose = None
    dose_unit = None
    if category == "nicotine" and index < len(tokens) and tokens[index] != "at":
        dose_match = AMOUNT_RE.fullmatch(tokens[index])
        if not dose_match:
            raise ValueError("Dose must look like 50mg")
        dose = float(dose_match.group("value"))
        dose_unit = dose_match.group("unit")
        index += 1
    at_value = None
    if index < len(tokens):
        if index + 1 >= len(tokens) or tokens[index] != "at":
            raise ValueError("Expected at HH:MM after quantity")
        at_value = tokens[index + 1]
    return JournalEventInput(
        category=category,
        subtype=subtype,
        occurred_at=_occurred_at(at_value, now, timezone),
        quantity=float(match.group("value")),
        unit=match.group("unit"),
        dose=dose,
        dose_unit=dose_unit,
        original_text=original_text,
    )


def _parse_key_values(tokens: list[str], allowed: set[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"Expected key=value, got {token}")
        key, value = token.split("=", 1)
        if key not in allowed:
            raise ValueError(f"Unknown field: {key}")
        values[key] = value
    return values


def _occurred_at(value: str | None, now: datetime, timezone: ZoneInfo) -> datetime:
    if value is None:
        return now.astimezone(timezone)
    parsed = time.fromisoformat(value)
    return datetime.combine(now.astimezone(timezone).date(), parsed, tzinfo=timezone)
