"""Drug-drug interaction evidence handling; absence of data stays unknown."""
from __future__ import annotations
from typing import Any, Iterable


def screen_interactions(drug_a: str, drug_b: str, warnings: Iterable[dict[str, Any]] | None = None,
                        *, source_status: str = "unavailable") -> dict[str, Any]:
    items = [dict(x) for x in (warnings or []) if isinstance(x, dict)]
    severities = {str(x.get("severity", "")).strip().casefold() for x in items}
    if severities & {"high", "contraindicated", "major", "severe"}:
        level, status = "High", "warnings_found"
    elif severities & {"moderate", "medium"}:
        level, status = "Moderate", "warnings_found"
    elif items:
        # A warning without a recognized source severity requires review, but
        # does not justify assigning an invented severity tier.
        level, status = "UNKNOWN", "warnings_found_severity_unknown"
    else:
        level = "UNKNOWN"
        status = "no_warning_returned" if source_status in {"available", "ok", "success"} else "unavailable"
    return {"drug_a": drug_a, "drug_b": drug_b, "status": status, "ddi_risk_level": level,
            "warnings": items, "decision": "REVIEW", "decision_scope": "Computational research screening only",
            "interpretation": "Reported warning severities are source labels, not a medical safety determination. No warning returned is not evidence that a combination is safe."}

