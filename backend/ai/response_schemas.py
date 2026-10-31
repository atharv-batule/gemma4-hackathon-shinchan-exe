from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ClaimCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = None
    record_id: str | None = None


class ExplanationClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_text: str = Field(min_length=1)
    citation: ClaimCitation | None = None
    claim_tag: Literal["sourced", "inferred", "unknown"]
    details: dict[str, Any] = Field(default_factory=dict)

class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, description="Short evidence-grounded summary; no treatment recommendations")
    key_findings: list[str] = Field(default_factory=list, description="Findings directly supported by the supplied records")
    uncertainty: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list, description="Only exact source identifiers included in supplied evidence")
    claims: list[ExplanationClaim] = Field(description="Atomic claims with source ledger citations and tags")
    research_hypothesis: str | None = None
