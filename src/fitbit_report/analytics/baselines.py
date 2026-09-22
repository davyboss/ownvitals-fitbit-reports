from dataclasses import dataclass
from statistics import fmean, median, stdev
from typing import Sequence


@dataclass(frozen=True)
class Baseline:
    window_days: int
    mean: float | None
    median: float | None
    stddev: float | None
    sample_size: int
    status: str


def compute_baseline(values: Sequence[float | None], window_days: int) -> Baseline:
    clean = [float(value) for value in values if value is not None]
    if not clean:
        return Baseline(window_days, None, None, None, 0, "insufficient")
    return Baseline(
        window_days=window_days,
        mean=fmean(clean),
        median=median(clean),
        stddev=stdev(clean) if len(clean) >= 2 else None,
        sample_size=len(clean),
        status="ready" if len(clean) >= 3 else "insufficient",
    )
