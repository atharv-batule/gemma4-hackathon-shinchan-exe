"""Compare reported assay concentrations without translating them into doses."""
from __future__ import annotations
from collections import defaultdict
from math import isfinite
from typing import Any, Iterable


def compare_experimental_ratios(records: Iterable[dict[str, Any]] | None) -> dict[str, Any]:
    rows = list(records or [])
    observed = []
    context_counts: dict[tuple[Any, ...], int] = defaultdict(int)
    for r in rows:
        conc_a = r.get("concentration_a", r.get("conc_row"))
        conc_b = r.get("concentration_b", r.get("conc_col"))
        unit = r.get("concentration_unit") or r.get("unit")
        metric = r.get("metric") or r.get("synergy_method")
        ratio = r.get("ratio")
        derived = None
        try:
            a, b = float(conc_a), float(conc_b)
            if isfinite(a) and isfinite(b) and a > 0 and b > 0 and unit:
                derived = {"a_to_b": a / b, "basis": "calculated from reported experimental concentrations", "unit": unit}
        except (TypeError, ValueError):
            pass
        if ratio is not None or conc_a is not None or conc_b is not None:
            observed.append({
                "drug_a": r.get("drug_a", r.get("drug_row")),
                "drug_b": r.get("drug_b", r.get("drug_col")),
                "reported_ratio": ratio,
                "derived_ratio": derived,
                "concentration_a": conc_a,
                "concentration_b": conc_b,
                "concentration_unit": unit,
                "cell_line": r.get("cell_line"),
                "metric": metric,
                "study": r.get("study") or r.get("study_name") or r.get("dataset"),
                "assay": r.get("assay") or r.get("assay_type"),
                "experimental_context": r.get("experimental_context") or r.get("context"),
                "source_version": r.get("source_version") or r.get("version"),
                "source": r.get("source", "DrugComb"),
                "source_id": r.get("source_id") or r.get("id") or r.get("block_id"),
                "citation": r.get("citation"),
                "doi": r.get("doi"),
                "pmid": r.get("pmid"),
                "url": r.get("url"),
            })
        # Concentrations and ratios are part of the experimental context. Keep
        # distinct dose rows separate even when cell line and study match.
        context_counts[(
            r.get("drug_a") or r.get("drug_row"), r.get("drug_b") or r.get("drug_col"),
            r.get("cell_line"), metric, unit,
            r.get("concentration_a", r.get("conc_row")),
            r.get("concentration_b", r.get("conc_col")), ratio,
            r.get("study") or r.get("study_name") or r.get("dataset"),
            r.get("assay") or r.get("assay_type"),
            r.get("experimental_context") or r.get("context"),
            r.get("source_version") or r.get("version"),
        )] += 1
    contexts = list(context_counts)
    required_context_indices = (2, 3, 4, 8, 9)
    context_complete = bool(contexts) and all(
        all(context[index] is not None for index in required_context_indices)
        for context in contexts
    )
    compatible = bool(observed) and len(contexts) == 1 and context_complete
    return {
        "status": "observed" if observed else "unknown",
        "observations": observed,
        "context_count": len(contexts),
        "context_details": [
            {"drug_a": c[0], "drug_b": c[1], "cell_line": c[2], "metric": c[3],
             "concentration_unit": c[4], "concentration_a": c[5], "concentration_b": c[6],
             "reported_ratio": c[7], "study": c[8], "assay": c[9],
             "experimental_context": c[10], "source_version": c[11], "record_count": count}
            for c, count in context_counts.items()
        ],
        "contexts_comparable": compatible,
        "context_metadata_complete": context_complete,
        "comparison_note": "Records are grouped by cell line, metric, unit, concentrations, ratio, study, and assay. Incomplete context metadata prevents a comparability claim; multiple contexts are not pooled.",
        "clinical_dosing_guidance": None,
        "note": "Reported concentrations and ratios describe experiments only; any derived ratio is arithmetic on the reported experimental concentrations, not a clinical dose recommendation.",
    }

