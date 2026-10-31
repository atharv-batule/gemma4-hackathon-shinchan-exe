"""Deterministically verify structured explanation claims against source records.

This module checks identity and structured fields only. It does not judge
whether free-text prose is scientifically entailed by a citation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Any, Iterable


VERIFIED = "VERIFIED"
ID_ONLY = "ID_ONLY"
MISMATCH = "MISMATCH"
UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class NumericTolerance:
    """Absolute/relative tolerance for like-unit reported numeric values."""

    absolute: float = 1e-6
    relative: float = 1e-3

    def __post_init__(self) -> None:
        if self.absolute < 0 or self.relative < 0:
            raise ValueError("Numeric tolerances must be non-negative")


# Claim detail keys map to source record fields. Units and experimental context
# are compared as reported; no unit conversion or inferred equivalence occurs.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "drug_names": ("drug_names", "drug_name", "drug_a", "drug_b", "drug_row", "drug_col"),
    "drug_ids": ("drug_ids", "drug_id", "drug_a_id", "drug_b_id", "chembl_id", "cid"),
    "metric": ("metric", "synergy_method", "method"),
    "cell_line": ("cell_line", "cellline", "cell_name", "assay_cell_type"),
    "units": ("units", "unit", "concentration_unit", "standard_units"),
    "experimental_context": ("experimental_context", "context", "assay", "assay_type", "study", "study_name"),
}


def _normal(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split())


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _source_payload(record: dict[str, Any]) -> dict[str, Any]:
    """Combine ledger metadata and source payload without mutating either."""
    result = dict(record)
    normalized = record.get("normalized_record")
    if isinstance(normalized, dict):
        result.update(normalized)
    raw = record.get("raw_json")
    if isinstance(raw, dict):
        # Source fields take precedence over ledger metadata on name collision.
        result.update(raw)
    elif isinstance(raw, list):
        # Some providers return collection payloads. No flattening into an
        # invented single record; only explicit mapping fields are inspectable.
        result["raw_json"] = raw
    return result


def _lookup(payload: dict[str, Any], aliases: Iterable[str]) -> tuple[bool, Any]:
    normalized = {str(key).casefold(): value for key, value in payload.items()}
    aliases = tuple(aliases)
    if "drug_names" in aliases:
        pair_values = [normalized[key] for key in ("drug_a", "drug_row", "drug_b", "drug_col") if normalized.get(key) is not None]
        if pair_values:
            return True, pair_values
    if "drug_ids" in aliases:
        pair_values = [normalized[key] for key in ("drug_a_id", "drug_b_id", "drug_id", "chembl_id", "cid") if normalized.get(key) is not None]
        if pair_values:
            return True, pair_values
    for key in aliases:
        if key.casefold() in normalized and normalized[key.casefold()] is not None:
            return True, normalized[key.casefold()]
    return False, None


def _numeric_equal(expected: Any, actual: Any, tolerance: NumericTolerance) -> bool:
    try:
        left, right = float(expected), float(actual)
    except (TypeError, ValueError, OverflowError):
        return _normal(expected) == _normal(actual)
    return isclose(left, right, rel_tol=tolerance.relative, abs_tol=tolerance.absolute)


def _compare_detail(key: str, expected: Any, payload: dict[str, Any], tolerance: NumericTolerance) -> tuple[str, dict[str, Any]]:
    """Return matched/missing/mismatch for one declared structured detail."""
    if key == "values":
        if not isinstance(expected, dict):
            return "mismatch", {"field": key, "reason": "values must be a field-to-value object"}
        any_missing = False
        for field, value in expected.items():
            present, source_value = _lookup(payload, (str(field),))
            if not present:
                any_missing = True
            elif not _numeric_equal(value, source_value, tolerance):
                return "mismatch", {"field": field, "expected": value, "source_value": source_value}
        return ("missing" if any_missing else "matched"), {"field": key, "checked": list(expected)}

    aliases = FIELD_ALIASES.get(key, (key,))
    present, source_value = _lookup(payload, aliases)
    if not present:
        return "missing", {"field": key, "reason": "field absent from cited source record"}
    expected_values = _as_list(expected)
    source_values = _as_list(source_value)
    if key in {"drug_names", "drug_ids"}:
        # Each claimed identity must occur in the cited record, while the
        # record may contain an additional combination partner.
        source_set = {_normal(item) for item in source_values}
        okay = all(_normal(item) in source_set for item in expected_values)
    elif key in {"metric", "cell_line", "units", "experimental_context"}:
        okay = len(expected_values) == 1 and any(_normal(expected_values[0]) == _normal(item) for item in source_values)
    else:
        okay = _numeric_equal(expected, source_value, tolerance)
    if not okay:
        return "mismatch", {"field": key, "expected": expected, "source_value": source_value}
    return "matched", {"field": key, "checked": True}


def verify_claims(
    claims: Iterable[dict[str, Any]],
    ledger: Iterable[dict[str, Any]],
    *,
    tolerance: NumericTolerance | None = None,
) -> dict[str, Any]:
    """Verify claim citations and declared details against this run's ledger.

    Expected claim shape::

        {"claim_text": "...", "citation": {"source": "PubMed", "record_id": "r1"},
         "claim_tag": "sourced", "details": {"metric": "ZIP", "values": {"score": 4.2}}}

    A ledger entry's `record_id` is preferred; its upstream `source_id` is also
    accepted for compatibility when paired with the exact source name. This
    function never considers an uncited free-text claim verified.
    """
    tolerance = tolerance or NumericTolerance()
    ledger_rows = [row for row in ledger if isinstance(row, dict)]
    output: list[dict[str, Any]] = []

    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            output.append({"claim_index": index, "claim_text": "", "claim_tag": "unknown", "status": UNVERIFIABLE,
                           "uncited_claim": False, "checks": [], "reason_code": "invalid_claim",
                           "reason": "Claim was not a structured object."})
            continue
        tag = str(claim.get("claim_tag", "sourced")).casefold()
        citation = claim.get("citation") if isinstance(claim.get("citation"), dict) else {}
        claim_text = str(claim.get("claim_text") or "")
        base = {"claim_index": index, "claim_text": claim_text, "claim_tag": tag,
                "citation_source": citation.get("source"), "citation_record_id": citation.get("record_id"),
                "checks": [], "uncited_claim": False}

        if tag in {"inferred", "unknown"}:
            output.append({**base, "status": UNVERIFIABLE, "reason_code": "explicitly_not_sourced",
                           "reason": "Claim is explicitly tagged inferred/unknown; source verification is not asserted."})
            continue
        if tag != "sourced":
            output.append({**base, "status": UNVERIFIABLE, "reason_code": "invalid_claim_tag",
                           "reason": "Unrecognized claim tag; use sourced, inferred, or unknown."})
            continue
        record_id = citation.get("record_id")
        source = citation.get("source")
        if not record_id or not source:
            output.append({**base, "status": UNVERIFIABLE, "uncited_claim": True,
                           "reason_code": "citation_missing", "reason": "Sourced claim is missing citation source or record ID."})
            continue

        matches = [row for row in ledger_rows if str(row.get("record_id")) == str(record_id)
                   or (row.get("record_id") is None and str(row.get("source_id")) == str(record_id))]
        if not matches:
            output.append({**base, "status": UNVERIFIABLE, "uncited_claim": False,
                           "reason_code": "record_id_not_in_ledger", "reason": "Citation record ID is absent from this run's evidence ledger."})
            continue
        source_matches = [row for row in matches if _normal(row.get("source")) == _normal(source)]
        if not source_matches:
            output.append({**base, "status": UNVERIFIABLE, "uncited_claim": False,
                           "reason_code": "citation_source_mismatch", "reason": "Record ID exists, but its ledger source differs from the cited source."})
            continue
        if len(source_matches) > 1:
            output.append({**base, "status": ID_ONLY, "reason_code": "ambiguous_ledger_record",
                           "reason": "Citation maps to multiple ledger records; detail verification is ambiguous."})
            continue

        payload = _source_payload(source_matches[0])
        details = claim.get("details") if isinstance(claim.get("details"), dict) else {}
        checks = []
        has_mismatch = False
        has_unavailable_detail = False
        for key, expected in details.items():
            result, check = _compare_detail(str(key), expected, payload, tolerance)
            checks.append({"status": result, **check})
            has_mismatch |= result == "mismatch"
            has_unavailable_detail |= result == "missing"
        if has_mismatch:
            status = MISMATCH
            reason_code = "structured_field_mismatch"
            reason = "At least one declared structured detail conflicts with the cited record."
        elif not checks or has_unavailable_detail:
            status = ID_ONLY
            reason_code = "details_unavailable"
            reason = "Citation ID/source matched, but structured details were absent or could not all be checked."
        else:
            status = VERIFIED
            reason_code = "structured_details_match"
            reason = "Citation ID/source and all declared structured details match this ledger record. Free-text entailment is not assessed."
        output.append({**base, "status": status, "ledger_record_id": source_matches[0].get("record_id"),
                       "reason_code": reason_code, "checks": checks, "reason": reason})

    return {"status": "complete", "results": output,
            "summary": {state: sum(1 for row in output if row.get("status") == state)
                        for state in (VERIFIED, ID_ONLY, MISMATCH, UNVERIFIABLE)},
            "limitations": ["Deterministic structured-field comparisons do not establish scientific entailment of free-text claims.",
                            "No unit conversion is performed; units and experimental context are compared as reported."]}
