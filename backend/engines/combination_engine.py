"""Evidence-oriented interpretation of experimentally reported combinations.

This module deliberately does not predict synergy. It only summarizes records
provided by a configured evidence service and preserves their context.
"""
from __future__ import annotations

from typing import Any, Iterable
from .ratio_analysis import compare_experimental_ratios

SYNERGY_METRICS = {"ZIP", "Bliss", "Loewe", "HSA"}


def analyze_combination(drug_a: str, drug_b: str,
                        records: Iterable[dict[str, Any]] | None = None,
                        *, source_status: str = "available") -> dict[str, Any]:
    """Filter and summarize source records without pooling incompatible assays."""
    if not drug_a.strip() or not drug_b.strip():
        raise ValueError("Both drug names or identifiers are required")
    # Accept the biomedical service envelope directly as well as a record list.
    if isinstance(records, dict):
        envelope = records
        records = envelope.get("records", [])
        source_status = envelope.get("status", source_status)
    evidence: list[dict[str, Any]] = []
    excluded_mismatched_pair = 0
    requested_pair = {drug_a.strip().casefold(), drug_b.strip().casefold()}
    for raw in records or []:
        if not isinstance(raw, dict):
            continue
        reported_a = raw.get("drug_a") or raw.get("drug_row")
        reported_b = raw.get("drug_b") or raw.get("drug_col")
        if reported_a and reported_b and {str(reported_a).strip().casefold(), str(reported_b).strip().casefold()} != requested_pair:
            excluded_mismatched_pair += 1
            continue
        metric = raw.get("metric") or raw.get("synergy_method")
        metric_norm = next((m for m in SYNERGY_METRICS if str(metric).casefold() == m.casefold()), None)
        evidence.append({
            "source": raw.get("source", "DrugComb"),
            "source_id": raw.get("source_id") or raw.get("id"),
            "drug_a": raw.get("drug_a") or raw.get("drug_row") or drug_a,
            "drug_b": raw.get("drug_b") or raw.get("drug_col") or drug_b,
            "metric": metric_norm or metric,
            "score": raw.get("score"),
            # A numerical score has no universal interpretation across methods;
            # carry a provider's wording only when it actually supplied one.
            "reported_interpretation": raw.get("interpretation") or raw.get("synergy_label") or raw.get("classification"),
            "cell_line": raw.get("cell_line"),
            "concentration_a": raw.get("concentration_a", raw.get("conc_row")),
            "concentration_b": raw.get("concentration_b", raw.get("conc_col")),
            "concentration_unit": raw.get("concentration_unit") or raw.get("unit"),
            "ratio": raw.get("ratio"),
            "experimental_context": raw.get("experimental_context") or raw.get("context"),
            "study": raw.get("study") or raw.get("study_name") or raw.get("dataset"),
            "assay": raw.get("assay") or raw.get("assay_type"),
            "source_version": raw.get("source_version") or raw.get("version"),
            "citation": raw.get("citation") or raw.get("reference"),
            "pmid": raw.get("pmid"),
            "doi": raw.get("doi"),
            "url": raw.get("url"),
            # Keep original provider fields for auditability, including source-specific
            # concentration columns and response values not mapped above.
            "source_record": dict(raw),
        })
    return {
        "drug_a": drug_a, "drug_b": drug_b,
        "status": "evidence_found" if evidence else ("no_records" if source_status in {"available", "ok", "success"} else "unavailable"),
        "evidence_count": len(evidence), "evidence": evidence,
        "ratio_analysis": compare_experimental_ratios(evidence),
        "excluded_mismatched_pair_count": excluded_mismatched_pair,
        "interpretation": "Reported scores and classifications remain source-reported. No threshold is applied and observations from different metrics, cell lines, concentrations, ratios, assays, or studies are not pooled.",
        "synergy_conclusion": None,
        "missing_evidence": [] if evidence else ["No experimental combination record was returned; this does not establish lack of effect."],
    }

