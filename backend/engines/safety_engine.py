"""Conservative computational workflow decisions, not clinical safety advice."""
from __future__ import annotations
from typing import Any, Iterable
from .ddi_engine import screen_interactions


def evaluate_safety(drug_a: str, drug_b: str,
                    ddi_warnings: Iterable[dict[str, Any]] | None = None,
                    *, ddi_status: str = "unavailable",
                    flagged_toxicophores: bool | None = None,
                    toxicity_evidence: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    ddi = screen_interactions(drug_a, drug_b, ddi_warnings, source_status=ddi_status)
    toxicity_evidence = toxicity_evidence or []
    # Workflow decision only. High-severity evidence blocks progression; missing
    # interaction/toxicity coverage always requires human review.
    if ddi["ddi_risk_level"] == "High" or flagged_toxicophores is True:
        decision = "NO-GO"
    elif ddi["ddi_risk_level"] == "UNKNOWN" or flagged_toxicophores is None:
        decision = "REVIEW"
    else:
        decision = "REVIEW"  # available computational evidence never establishes clinical safety
    missing = []
    if not ddi["warnings"]:
        if ddi["status"] == "unavailable":
            missing.append("Drug interaction provider unavailable; interaction evidence is unknown.")
        else:
            missing.append("No interaction warning was returned; this does not establish absence of an interaction.")
    if flagged_toxicophores is None and not toxicity_evidence:
        missing.append("Toxicity evidence was not assessed or returned.")
    return {"decision": decision, "decision_scope": "Computational research screening only",
            "flagged_toxicophores": flagged_toxicophores,
            "ddi_risk_level": ddi["ddi_risk_level"], "ddi_status": ddi["status"],
            "ddi_warnings": ddi["warnings"], "toxicity_evidence": toxicity_evidence,
            "missing_evidence": missing,
            "interpretation": "A computational workflow decision is not a medical safety determination. Experimental concentrations are not clinical dosing recommendations.",
            "clinical_safety_conclusion": None}

