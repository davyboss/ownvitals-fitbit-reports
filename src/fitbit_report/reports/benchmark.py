"""Comparable Claude model benchmark for the personal health report prompt."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from statistics import fmean
from typing import Any, Callable

from sqlalchemy.engine import Engine

from fitbit_report.db.session import session_scope
from fitbit_report.i18n import Locale
from fitbit_report.private_storage import ensure_private_directory, write_private_text
from fitbit_report.reports.context import ReportContext, build_report_context
from fitbit_report.reports.llm_runner import ClaudeCliRunner
from fitbit_report.reports.prompts import build_prompt
from fitbit_report.reports.schemas import ReportDraft
from fitbit_report.runtime import report_period
from fitbit_report.types import ReportType


DEFAULT_BENCHMARK_MODELS = (
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
)

# Current benchmark defaults in USD per one million tokens. The command keeps
# them in code so the report is reproducible; update them when Anthropic changes
# prices or introduces temporary pricing.
MODEL_PRICING_USD: dict[str, dict[str, float]] = {
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
}

MODEL_ALIASES = {
    "opus5": "claude-opus-5",
    "opus-5": "claude-opus-5",
    "sonnet5": "claude-sonnet-5",
    "sonnet-5": "claude-sonnet-5",
    "haiku45": "claude-haiku-4-5-20251001",
    "haiku-4.5": "claude-haiku-4-5-20251001",
    "haiku-4-5": "claude-haiku-4-5-20251001",
    "haiku-4-5-20251001": "claude-haiku-4-5-20251001",
}


def normalize_model_name(value: str) -> str:
    cleaned = value.strip()
    return MODEL_ALIASES.get(cleaned.casefold(), cleaned)


def pricing_for_model(model: str) -> dict[str, float]:
    normalized = normalize_model_name(model)
    if normalized in MODEL_PRICING_USD:
        return dict(MODEL_PRICING_USD[normalized])
    lowered = normalized.casefold()
    if "opus" in lowered:
        return {"input": 5.0, "output": 25.0}
    if "haiku" in lowered:
        return {"input": 1.0, "output": 5.0}
    if "sonnet" in lowered:
        return {"input": 3.0, "output": 15.0}
    return {"input": 0.0, "output": 0.0}


def calculate_api_cost(usage: dict[str, object], pricing: dict[str, float]) -> float:
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    cache_read_tokens = int(usage.get("cache_read_input_tokens", 0) or 0)
    cache_creation_tokens = int(usage.get("cache_creation_input_tokens", 0) or 0)
    return (
        input_tokens * pricing["input"]
        + output_tokens * pricing["output"]
        + cache_read_tokens * pricing["input"] * 0.1
        + cache_creation_tokens * pricing["input"] * 1.25
    ) / 1_000_000


def _draft_text(draft: ReportDraft) -> str:
    return json.dumps(draft.model_dump(mode="json"), ensure_ascii=False).casefold()


def _available_topics(context: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    return {
        "personal_state": ("готов", "состояни", "readiness", "энерг", "самочувств"),
        "baseline": ("baseline", "личн", "норм", "средн", "медиан", "отклон"),
        "sleep": ("сон", "сна", "sleep", "восстанов"),
        "training": ("трен", "нагруз", "зал", "упражн", "вес", "повтор", "rpe"),
        "nutrition": ("питан", "еда", "калор", "белк", "жир", "углев", "нутриент"),
        "personal_factors": ("личн", "фактор", "кофеин", "никотин", "мастурб", "интим"),
        "productivity": ("продуктив", "фокус", "работ", "концентрац"),
    }


def score_draft(draft: ReportDraft, context: ReportContext) -> dict[str, Any]:
    """Return a transparent heuristic score; raw answers remain in the report for review."""
    payload = context.as_dict()
    health = payload.get("health", {})
    productivity = payload.get("productivity_context", {})
    text = _draft_text(draft)
    claims = draft.claims
    claims_with_sources = sum(bool(item.source_ids) for item in claims)
    claims_with_evidence = sum(item.evidence_count > 0 for item in claims)
    recommendations = [item for item in draft.recommendations if len(item.strip()) >= 24]
    experiments = [item for item in draft.experiments if len(item.strip()) >= 24]
    topics = _available_topics(payload)
    topic_presence = {
        "personal_state": bool(payload.get("personal_state")),
        "baseline": bool(payload.get("baselines")),
        "sleep": bool(health.get("sleep")),
        "training": bool(
            health.get("training_logs")
            or health.get("exercise_sessions")
            or health.get("gym_training")
        ),
        "nutrition": bool(health.get("nutrition")),
        "personal_factors": bool(payload.get("personal_factors")),
        "productivity": bool(productivity),
    }
    present_topics = [name for name in topics if topic_presence[name]]
    topic_hits = [name for name in present_topics if any(keyword in text for keyword in topics[name])]

    source_score = 100.0 if not claims else 100.0 * claims_with_sources / len(claims)
    evidence_score = 100.0 if not claims else 100.0 * claims_with_evidence / len(claims)
    available_count = max(1, len(present_topics))
    coverage_score = 100.0 * len(topic_hits) / available_count
    actionability_score = min(
        100.0,
        (50.0 if recommendations else 0.0) + (50.0 if experiments else 0.0),
    )
    components = {
        "schema": 25.0,
        "evidence": round(0.125 * source_score + 0.125 * evidence_score, 2),
        "personal_coverage": round(0.25 * coverage_score, 2),
        "actionability": round(0.25 * actionability_score, 2),
    }
    return {
        "score": round(sum(components.values()), 2),
        "components": components,
        "claims": len(claims),
        "claims_with_sources": claims_with_sources,
        "claims_with_evidence": claims_with_evidence,
        "recommendations": len(draft.recommendations),
        "experiments": len(draft.experiments),
        "available_topics": present_topics,
        "detected_topics": topic_hits,
        "note": "Эвристика проверяет структуру, ссылки на источники, персональные темы и применимость советов; финальный выбор нужно делать по сохранённым ответам.",
    }


def _period_label(report_type: ReportType, target_day: date) -> str:
    period = report_period(report_type, target_day)
    return f"{period.start.isoformat()}..{period.end.isoformat()}"


def run_benchmark(
    engine: Engine,
    timezone_name: str,
    report_type: ReportType,
    target_day: date,
    models: list[str] | tuple[str, ...] = DEFAULT_BENCHMARK_MODELS,
    repeats: int = 1,
    max_turns: int = 1,
    subscription_price_usd: float = 20.0,
    monthly_calls: int = 30,
    usage_recorder: Callable[[str, str, dict[str, object], bool], None] | None = None,
    locale: Locale = "ru",
) -> dict[str, Any]:
    if not models:
        raise ValueError("At least one model is required")
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    if monthly_calls < 1:
        raise ValueError("monthly_calls must be at least 1")

    period = report_period(report_type, target_day)
    with session_scope(engine) as session:
        context = build_report_context(
            session,
            report_type,
            period,
            timezone_name,
            locale,
        )
    prompt = build_prompt(context, locale)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    normalized_models = [normalize_model_name(item) for item in models]
    results: list[dict[str, Any]] = []

    for model in normalized_models:
        pricing = pricing_for_model(model)
        runs: list[dict[str, Any]] = []
        for repeat in range(1, repeats + 1):
            captured_usage: dict[str, object] = {}

            def capture_usage(operation: str, used_model: str, usage: dict[str, object], success: bool) -> None:
                captured_usage.update(usage)
                if usage_recorder is not None:
                    usage_recorder("benchmark", used_model, usage, success)

            runner = ClaudeCliRunner(
                model,
                max_turns=max_turns,
                usage_recorder=capture_usage,
                operation="benchmark",
                input_price_per_million_usd=pricing["input"],
                output_price_per_million_usd=pricing["output"],
                cache_read_price_per_million_usd=pricing["input"] * 0.1,
                cache_creation_price_per_million_usd=pricing["input"] * 1.25,
            )
            run_record: dict[str, Any] = {"repeat": repeat, "model": model}
            try:
                draft = runner.generate(prompt)
            except Exception as exc:
                run_record.update({"status": "error", "error": str(exc)})
            else:
                run_record.update({
                    "status": "success",
                    "quality": score_draft(draft, context),
                    "draft": draft.model_dump(mode="json"),
                })
            run_record["usage"] = {
                "input_tokens": int(captured_usage.get("input_tokens", 0) or 0),
                "output_tokens": int(captured_usage.get("output_tokens", 0) or 0),
                "cache_read_input_tokens": int(captured_usage.get("cache_read_input_tokens", 0) or 0),
                "cache_creation_input_tokens": int(captured_usage.get("cache_creation_input_tokens", 0) or 0),
                "estimated": bool(captured_usage.get("estimated", False)),
            }
            run_record["api_cost_usd"] = round(calculate_api_cost(captured_usage, pricing), 8)
            runs.append(run_record)

        successful = [item for item in runs if item["status"] == "success"]
        average_cost = fmean(item["api_cost_usd"] for item in runs) if runs else 0.0
        average_quality = fmean(item["quality"]["score"] for item in successful) if successful else 0.0
        break_even = (
            subscription_price_usd / average_cost if average_cost > 0 else None
        )
        results.append({
            "model": model,
            "pricing_usd_per_million_tokens": pricing,
            "runs": runs,
            "successful_runs": len(successful),
            "average_quality_score": round(average_quality, 2),
            "average_api_cost_usd": round(average_cost, 8),
            "projected_api_cost_usd_per_month": round(average_cost * monthly_calls, 4),
            "break_even_calls_vs_subscription": round(break_even, 2) if break_even is not None else None,
            "usage_is_estimated": any(item["usage"]["estimated"] for item in runs),
        })

    successful_results = [item for item in results if item["successful_runs"]]
    best_quality = max(successful_results, key=lambda item: item["average_quality_score"], default=None)
    best_value = max(
        successful_results,
        key=lambda item: item["average_quality_score"] / max(item["average_api_cost_usd"], 0.000001),
        default=None,
    )
    return {
        "benchmark": "personal-health-report",
        "period": _period_label(report_type, target_day),
        "report_type": report_type,
        "prompt_sha256": prompt_hash,
        "models": normalized_models,
        "repeats": repeats,
        "subscription_price_usd": subscription_price_usd,
        "monthly_calls_projection": monthly_calls,
        "results": results,
        "best_quality_model": best_quality["model"] if best_quality else None,
        "best_quality_score": best_quality["average_quality_score"] if best_quality else None,
        "best_value_model": best_value["model"] if best_value else None,
        "best_value_score_per_api_dollar": (
            round(best_value["average_quality_score"] / max(best_value["average_api_cost_usd"], 0.000001), 2)
            if best_value else None
        ),
        "api_vs_subscription_note": (
            "API projection uses Anthropic list prices and measured/estimated token usage. "
            "Claude Pro is a separate consumer subscription: its price is not an API credit, "
            "and its usage limits are not equivalent to a fixed token budget."
        ),
    }


def save_benchmark(result: dict[str, Any], output_dir: Path) -> Path:
    ensure_private_directory(output_dir)
    timestamp = result["period"].replace("..", "-")
    path = output_dir / f"benchmark-{timestamp}-{result['prompt_sha256'][:8]}.json"
    write_private_text(
        path,
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
    )
    return path
