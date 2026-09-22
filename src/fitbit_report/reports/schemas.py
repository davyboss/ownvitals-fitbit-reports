from typing import Literal

from pydantic import BaseModel, Field


class ReportClaim(BaseModel):
    statement: str
    kind: Literal["fact", "association", "hypothesis"]
    evidence_count: int = Field(ge=0)
    confidence: Literal["insufficient", "low", "medium", "high"]
    alternatives: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ReportDraft(BaseModel):
    summary: str
    claims: list[ReportClaim]
    recommendations: list[str]
    experiments: list[str]
    confidence: Literal["insufficient", "low", "medium", "high"]
