from dataclasses import dataclass
from statistics import fmean
from typing import Sequence


@dataclass(frozen=True)
class LaggedDayFeatures:
    target_productivity: float | None
    caffeine_after_15h: int | None = None
    sleep_duration_min: float | None = None
    previous_day_stress: float | None = None


@dataclass(frozen=True)
class Association:
    factor: str
    target: str
    direction: str
    effect_size: float
    sample_size: int
    confidence: str
    group_counts: dict[str, int] | None = None


def find_associations(rows: Sequence[LaggedDayFeatures], target: str) -> list[Association]:
    results = []
    for factor in ("caffeine_after_15h", "sleep_duration_min", "previous_day_stress"):
        pairs = [
            (getattr(row, factor), getattr(row, target))
            for row in rows
            if getattr(row, factor) is not None and getattr(row, target) is not None
        ]
        if len(pairs) < 5:
            continue
        values = [float(value) for value, _ in pairs]
        outcomes = [float(outcome) for _, outcome in pairs]
        if factor == "caffeine_after_15h":
            groups: dict[str, list[float]] = {"0": [], "1": []}
            for value, outcome in pairs:
                groups[str(int(value))].append(outcome)
            effect = fmean(groups["1"]) - fmean(groups["0"])
            counts = {key: len(value) for key, value in groups.items()}
        else:
            effect = _rank_corr(values, outcomes)
            counts = {}
        results.append(
            Association(
                factor=factor,
                target=target,
                direction="positive" if effect > 0 else "negative" if effect < 0 else "neutral",
                effect_size=effect,
                sample_size=len(pairs),
                confidence="low" if len(pairs) < 10 else "medium",
                group_counts=counts,
            )
        )
    return results


def _rank_corr(values: list[float], outcomes: list[float]) -> float:
    ranks_x = _ranks(values)
    ranks_y = _ranks(outcomes)
    mean_x = fmean(ranks_x)
    mean_y = fmean(ranks_y)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(ranks_x, ranks_y))
    denominator_x = sum((x - mean_x) ** 2 for x in ranks_x) ** 0.5
    denominator_y = sum((y - mean_y) ** 2 for y in ranks_y) ** 0.5
    return numerator / (denominator_x * denominator_y) if denominator_x and denominator_y else 0.0


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    for rank, index in enumerate(order, start=1):
        result[index] = float(rank)
    return result
