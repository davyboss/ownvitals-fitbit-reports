from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, Field

from fitbit_report.i18n import Locale, translate
from fitbit_report.reports.llm_runner import ClaudeCliRunner


Confidence = Literal["insufficient", "low", "medium", "high"]
class FoodItemEstimate(BaseModel):
    name: str
    portion: str
    calories_min: float | None = Field(default=None, ge=0)
    calories_max: float | None = Field(default=None, ge=0)
    protein_g_min: float | None = Field(default=None, ge=0)
    protein_g_max: float | None = Field(default=None, ge=0)
    carbohydrates_g_min: float | None = Field(default=None, ge=0)
    carbohydrates_g_max: float | None = Field(default=None, ge=0)
    fat_g_min: float | None = Field(default=None, ge=0)
    fat_g_max: float | None = Field(default=None, ge=0)
    confidence: Confidence


class FoodAnalysis(BaseModel):
    summary: str
    items: list[FoodItemEstimate]
    total_calories_min: float | None = Field(default=None, ge=0)
    total_calories_max: float | None = Field(default=None, ge=0)
    total_protein_g_min: float | None = Field(default=None, ge=0)
    total_protein_g_max: float | None = Field(default=None, ge=0)
    total_carbohydrates_g_min: float | None = Field(default=None, ge=0)
    total_carbohydrates_g_max: float | None = Field(default=None, ge=0)
    total_fat_g_min: float | None = Field(default=None, ge=0)
    total_fat_g_max: float | None = Field(default=None, ge=0)
    uncertainty: str
    confidence: Confidence


class FoodPhotoAnalyzer:
    def __init__(
        self,
        runner: ClaudeCliRunner | None = None,
        model: str = "sonnet",
        locale: Locale = "ru",
    ):
        self.runner = runner or ClaudeCliRunner(model, max_turns=2)
        self.locale = locale

    def analyze(
        self,
        image_path: Path,
        meal_type: str,
        correction: str | None = None,
        *,
        description: str | None = None,
        exact_details: str | None = None,
    ) -> FoodAnalysis:
        payload = self.runner.generate_json(
            build_food_prompt(
                meal_type,
                correction,
                self.locale,
                description=description,
                exact_details=exact_details,
            ),
            image_path,
            max_turns=2,
        )
        return apply_exact_nutrition(
            FoodAnalysis.model_validate(payload),
            exact_details,
        )


class FoodTextAnalyzer:
    def __init__(
        self,
        runner: ClaudeCliRunner | None = None,
        model: str = "sonnet",
        locale: Locale = "ru",
    ):
        self.runner = runner or ClaudeCliRunner(model, max_turns=2)
        self.locale = locale

    def analyze(
        self,
        description: str,
        meal_type: str,
        *,
        exact_details: str | None = None,
    ) -> FoodAnalysis:
        payload = self.runner.generate_json(
            build_food_text_prompt(
                meal_type,
                description,
                self.locale,
                exact_details=exact_details,
            ),
            None,
            max_turns=2,
        )
        return apply_exact_nutrition(
            FoodAnalysis.model_validate(payload),
            exact_details,
        )


def apply_exact_nutrition(
    analysis: FoodAnalysis,
    exact_details: str | None,
) -> FoodAnalysis:
    """Make explicitly labelled user values authoritative over model estimates."""
    if not exact_details:
        return analysis

    number = r"(\d+(?:[.,]\d+)?)"
    patterns = {
        "calories": rf"{number}\s*(?:ккал|kcal)\b",
        "protein": rf"(?:^|[;,\s])(?:б|белки?|protein|p)\s*[:=]?\s*{number}\b",
        "fat": rf"(?:^|[;,\s])(?:ж|жиры?|fat|f)\s*[:=]?\s*{number}\b",
        "carbohydrates": (
            rf"(?:^|[;,\s])(?:у|углеводы?|carbs?|carbohydrates|c)"
            rf"\s*[:=]?\s*{number}\b"
        ),
    }
    values: dict[str, float] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, exact_details, flags=re.IGNORECASE)
        if match:
            values[name] = float(match.group(1).replace(",", "."))
    if not values:
        return analysis

    updates = {}
    field_pairs = {
        "calories": ("total_calories_min", "total_calories_max"),
        "protein": ("total_protein_g_min", "total_protein_g_max"),
        "fat": ("total_fat_g_min", "total_fat_g_max"),
        "carbohydrates": (
            "total_carbohydrates_g_min",
            "total_carbohydrates_g_max",
        ),
    }
    for name, value in values.items():
        minimum, maximum = field_pairs[name]
        updates[minimum] = value
        updates[maximum] = value
    return analysis.model_copy(update=updates)


def build_food_prompt(
    meal_type: str,
    correction: str | None = None,
    locale: Locale = "ru",
    *,
    description: str | None = None,
    exact_details: str | None = None,
) -> str:
    if locale == "en":
        correction_text = (
            f"The user asks you to apply this correction: {correction}\n"
            if correction
            else ""
        )
        description_text = (
            f"User description: {description}\n" if description else ""
        )
        exact_text = (
            "User-provided exact details: "
            f"{exact_details}\nTreat these values as facts. Preserve exact nutrition values "
            "by setting the corresponding minimum and maximum to the same value.\n"
            if exact_details
            else ""
        )
        return (
            "Analyze the meal photo. Return valid JSON only, without markdown. "
            "Write every textual field in English. Do not claim exact values: estimate portions "
            "as ranges and state confidence. If a food or portion size is not visible, mention it "
            "in uncertainty. Do not invent ingredients that are not visible. "
            "Return exactly these fields: summary, items, total_calories_min, total_calories_max, "
            "total_protein_g_min, total_protein_g_max, total_carbohydrates_g_min, "
            "total_carbohydrates_g_max, total_fat_g_min, total_fat_g_max, uncertainty, confidence. "
            "Each item must contain name, portion, calories_min, calories_max, protein_g_min, "
            "protein_g_max, carbohydrates_g_min, carbohydrates_g_max, fat_g_min, fat_g_max, "
            "confidence. confidence must be one of: insufficient, low, medium, high. "
            f"Meal type: {meal_type}.\n{description_text}{exact_text}{correction_text}"
        )
    correction_text = (
        f"Пользователь просит учесть исправление: {correction}\n"
        if correction
        else ""
    )
    description_text = (
        f"Примерное описание пользователя: {description}\n" if description else ""
    )
    exact_text = (
        "Точные данные пользователя: "
        f"{exact_details}\nСчитай эти значения фактами. Для точно указанных нутриентов "
        "установи одинаковые минимальное и максимальное значения.\n"
        if exact_details
        else ""
    )
    return (
        "Проанализируй фотографию приёма пищи. Ответь только валидным JSON, без markdown. "
        "Пиши все текстовые поля на русском языке. Не выдавай точные значения: оцени порции "
        "диапазонами и укажи уверенность. Если продукт или размер порции не виден, укажи это "
        "в uncertainty. Не придумывай ингредиенты, которых не видно. "
        "Верни ровно поля summary, items, total_calories_min, total_calories_max, "
        "total_protein_g_min, total_protein_g_max, total_carbohydrates_g_min, "
        "total_carbohydrates_g_max, total_fat_g_min, total_fat_g_max, uncertainty, confidence. Каждый item должен "
        "содержать name, portion, calories_min, calories_max, protein_g_min, protein_g_max, "
        "carbohydrates_g_min, carbohydrates_g_max, fat_g_min, fat_g_max, confidence. "
        "confidence может быть только insufficient, low, medium или high. "
        f"Тип приёма пищи: {meal_type}.\n{description_text}{exact_text}{correction_text}"
    )


def build_food_text_prompt(
    meal_type: str,
    description: str,
    locale: Locale = "ru",
    *,
    exact_details: str | None = None,
) -> str:
    if locale == "en":
        exact_text = (
            " Exact details supplied by the user: "
            f"{exact_details}. Treat these as facts and preserve exact nutrition values by "
            "setting the corresponding minimum and maximum to the same value."
            if exact_details
            else ""
        )
        return (
            "Analyze the meal description and estimate its composition. Return valid JSON only, "
            "without markdown. Write every textual field in English. Do not claim exact values: "
            "estimate portions and calories as ranges. If the portion size or composition is "
            "unclear, explain it in uncertainty and lower confidence. Do not invent ingredients "
            "that are not in the description. Return exactly these fields: summary, items, "
            "total_calories_min, total_calories_max, total_protein_g_min, total_protein_g_max, "
            "total_carbohydrates_g_min, total_carbohydrates_g_max, total_fat_g_min, "
            "total_fat_g_max, uncertainty, confidence. Each item must contain name, portion, "
            "calories_min, calories_max, protein_g_min, protein_g_max, carbohydrates_g_min, "
            "carbohydrates_g_max, fat_g_min, fat_g_max, confidence. confidence must be one of: "
            f"insufficient, low, medium, high. Meal type: {meal_type}. Description: {description}."
            f"{exact_text}"
        )
    exact_text = (
        " Точные данные пользователя: "
        f"{exact_details}. Считай их фактами; для точно указанных нутриентов установи "
        "одинаковые минимальное и максимальное значения."
        if exact_details
        else ""
    )
    return (
        "Проанализируй текстовое описание приёма пищи и оцени его состав. "
        "Ответь только валидным JSON, без markdown. Пиши все текстовые поля на русском языке. "
        "Не выдавай точные значения: оцени порции и калории диапазонами. "
        "Если размер порции или состав неясен, укажи это в uncertainty и снизь confidence. "
        "Не придумывай ингредиенты, которых нет в описании. "
        "Верни ровно поля summary, items, total_calories_min, total_calories_max, "
        "total_protein_g_min, total_protein_g_max, total_carbohydrates_g_min, "
        "total_carbohydrates_g_max, total_fat_g_min, total_fat_g_max, uncertainty, confidence. "
        "Каждый item должен содержать name, portion, calories_min, calories_max, "
        "protein_g_min, protein_g_max, carbohydrates_g_min, carbohydrates_g_max, "
        "fat_g_min, fat_g_max, confidence. confidence может быть только insufficient, "
        f"low, medium или high. Тип приёма пищи: {meal_type}. Описание: {description}."
        f"{exact_text}"
    )


def format_food_analysis(analysis: FoodAnalysis, locale: Locale = "ru") -> str:
    lines = [
        analysis.summary,
        "",
        translate("food.approximate_composition", locale),
    ]
    for item in analysis.items:
        line = f"• {item.name} — {item.portion}"
        if item.calories_min is not None and item.calories_max is not None:
            line += ", " + translate(
                "food.item_calories",
                locale,
                value=format_range(item.calories_min, item.calories_max),
            )
        lines.append(line)
    if analysis.total_calories_min is not None and analysis.total_calories_max is not None:
        lines.extend([
            "",
            translate(
                "food.total",
                locale,
                value=format_range(analysis.total_calories_min, analysis.total_calories_max),
            ),
        ])
    macro_lines = []
    for label_key, minimum, maximum in (
        ("food.protein", analysis.total_protein_g_min, analysis.total_protein_g_max),
        ("food.carbohydrates", analysis.total_carbohydrates_g_min, analysis.total_carbohydrates_g_max),
        ("food.fat", analysis.total_fat_g_min, analysis.total_fat_g_max),
    ):
        if minimum is not None and maximum is not None:
            macro_lines.append(
                f"{translate(label_key, locale)}: "
                + translate("food.grams", locale, value=format_range(minimum, maximum))
            )
    if macro_lines:
        lines.extend(["", translate("food.macros", locale), *macro_lines])
    lines.extend([
        translate(
            "food.confidence",
            locale,
            value=translate(f"food.confidence.{analysis.confidence}", locale),
        ),
        analysis.uncertainty,
    ])
    return "\n".join(lines)


def format_range(minimum: float, maximum: float) -> str:
    return f"{_format_number(minimum)}–{_format_number(maximum)}"


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"
