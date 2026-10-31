"""Evidence handling and transparent candidate ranking for repurposing research.

Scores are prioritisation aids only. They are not estimates of efficacy.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


def _items(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        value = value.get("records", value.get("results", value.get("data", [])))
    if not isinstance(value, (list, tuple)):
        return []
    return [x for x in value if isinstance(x, dict)]


def build_target_evidence(gene_records: Any, drug_records: Any) -> dict[str, Any]:
    """Normalize disease-gene and drug-target records without inventing links."""
    genes: dict[str, dict[str, Any]] = {}
    for item in _items(gene_records):
        symbol = item.get("gene_symbol") or item.get("symbol") or item.get("target")
        if not symbol:
            continue
        key = str(symbol).upper()
        entry = genes.setdefault(key, {"gene_symbol": str(symbol), "disease_associations": [], "drug_target_records": []})
        association = {k: item.get(k) for k in ("source", "source_id", "score", "evidence", "url", "target_id", "target_name") if item.get(k) is not None}
        if association not in entry["disease_associations"]:
            entry["disease_associations"].append(association)
    for item in _items(drug_records):
        symbol = item.get("gene_symbol") or item.get("target_symbol") or item.get("target")
        if not symbol:
            continue
        key = str(symbol).upper()
        entry = genes.setdefault(key, {"gene_symbol": str(symbol), "disease_associations": [], "drug_target_records": []})
        # Retain source-reported assay context and identifiers so downstream
        # candidate summaries can be traced to the actual ChEMBL record.
        entry["drug_target_records"].append({k: item.get(k) for k in (
            "drug_name", "drug_id", "target_id", "mechanism", "action",
            "activity_type", "activity_value", "units", "pchembl_value",
            "evidence_class", "assay_id", "assay_description", "assay_cell_type",
            "assay_tissue", "assay_organism", "bao_label", "confidence_score",
            "source", "source_id", "url",
        ) if item.get(k) is not None})
    return {"targets": list(genes.values()), "disease_gene_record_count": len(_items(gene_records)), "drug_target_record_count": len(_items(drug_records))}


def rank_candidates(targets: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank distinct drug-target hypotheses using evidence presence and coverage.

    A 0-100 evidence-completeness score measures records available, not drug
    effectiveness. No candidate is created from an unsupported name.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for target in targets:
        gene = target.get("gene_symbol")
        for record in target.get("drug_target_records", []):
            name = record.get("drug_name")
            if not name:
                continue
            ident = str(record.get("drug_id") or name).casefold()
            c = grouped.setdefault(ident, {"drug_name": name, "drug_id": record.get("drug_id"), "targets": [], "disease_associations": [], "evidence": [], "dimensions": {"biological_relevance": None, "drug_target_evidence": None, "experimental_evidence": None, "preclinical_evidence": None, "clinical_evidence": None, "data_completeness": None}})
            if gene and gene not in c["targets"]:
                c["targets"].append(gene)
            disease_associations = target.get("disease_associations", [])
            for association in disease_associations:
                if association not in c["disease_associations"]:
                    c["disease_associations"].append(association)
            evidence = {**record, "gene_symbol": gene, "disease_associations": disease_associations}
            c["evidence"].append(evidence)
    result = []
    for candidate in grouped.values():
        # The score is explicitly a count-based information-coverage score.
        evidence_count = len(candidate["evidence"])
        populated = sum(bool(e.get(k)) for e in candidate["evidence"] for k in ("source", "source_id", "mechanism", "activity_type", "activity_value", "url", "assay_id"))
        score = round(min(100.0, (min(3, len(candidate["targets"])) / 3 * 50) + min(50, populated * 8)), 1)
        candidate["dimensions"].update({
            "biological_relevance": "supported" if candidate["targets"] else "unknown",
            "drug_target_evidence": evidence_count,
            "experimental_evidence": "not separately assessed",
            "preclinical_evidence": "not separately assessed",
            "clinical_evidence": "not separately assessed",
            "data_completeness": score,
        })
        candidate["evidence_completeness_score"] = score
        candidate["score_interpretation"] = "Record completeness and target coverage only; not efficacy or clinical readiness."
        candidate["evidence_level"] = "target association; experimental/preclinical/clinical level not inferred"
        candidate["evidence"] = _deduplicate(candidate["evidence"])
        candidate["disease_associations"] = _deduplicate(candidate["disease_associations"])
        result.append(candidate)
    return sorted(result, key=lambda c: (-c["evidence_completeness_score"], c["drug_name"].casefold()))


def _deduplicate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    out = []
    for record in records:
        key = tuple(sorted((k, str(v)) for k, v in record.items()))
        if key not in seen:
            seen.add(key)
            out.append(record)
    return out

