from dataclasses import dataclass, field


@dataclass(frozen=True)
class MemoryItem:
    observation_id: int
    factor: str
    sample_size: int
    confidence: str


@dataclass(frozen=True)
class MemoryContext:
    items: list[MemoryItem]
    correction_ids: list[int]
    facts: list[dict] = field(default_factory=list)
    feedback: list[dict] = field(default_factory=list)
