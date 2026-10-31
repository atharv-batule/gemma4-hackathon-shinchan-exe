"""Context-preserving cell-line by synergy-metric evidence summary.

This module displays source-reported scores only. It never calculates synergy,
applies cutoffs, or treats missing observations as additive/negative results.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

METRICS = ("ZIP", "Bliss", "Loewe", "HSA")
_METRIC_ALIASES = {metric.casefold(): metric for metric in METRICS}
_METRIC_ALIASES.update({"hsa": "HSA", "zip": "ZIP"})
_CONTEXT_FIELDS = (
    "study", "assay", "concentration_a", "concentration_b",
    "concentration_unit", "ratio", "experimental_context", "source_version",
)
_REQUIRED_COMPARISON_FIELDS = ("study", "assay", "concentration_a", "concentration_b", "concentration_unit")


def _metric(record: dict[str, Any]) -> str | None:
    value = record.get("metric") or record.get("synergy_method")
    return _METRIC_ALIASES.get(str(value).strip().casefold()) if value is not None else None


def _context(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "study": record.get("study") or record.get("study_name") or record.get("dataset"),
        "assay": record.get("assay") or record.get("assay_type"),
        "concentration_a": record.get("concentration_a", record.get("conc_row")),
        "concentration_b": record.get("concentration_b", record.get("conc_col")),
        "concentration_unit": record.get("concentration_unit") or record.get("unit"),
        "ratio": record.get("ratio"),
        "experimental_context": record.get("experimental_context") or record.get("context"),
        "source_version": record.get("source_version") or record.get("version"),
    }


def _context_key(context: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(str(context[field]).strip().casefold() if context[field] is not None else None for field in _CONTEXT_FIELDS)


def _interpretation(record: dict[str, Any]) -> str | None:
    value = record.get("reported_interpretation") or record.get("interpretation") or record.get("synergy_label") or record.get("classification")
    return str(value).strip() if value is not None and str(value).strip() else None


def build_synergy_heatmap(
    records: Iterable[dict[str, Any]] | dict[str, Any] | None,
    *,
    source_status: str = "available",
) -> dict[str, Any]:
    """Build a cell-line x metric matrix while preserving each observation.

    A warning is emitted only when source-reported interpretations disagree
    within the same complete assay context, or differ across distinct contexts
    (in which case the result is labelled context-dependent, not pooled).
    Numeric scores alone are never assigned qualitative meaning.
    """
    if isinstance(records, dict):
        envelope = records
        source_status = str(envelope.get("status", source_status))
        rows = envelope.get("evidence", envelope.get("records", []))
    else:
        rows = records or []
    if not isinstance(rows, (list, tuple)):
        rows = []

    grouped: dict[tuple[str | None, str], list[dict[str, Any]]] = defaultdict(list)
    cell_lines: set[str | None] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        metric = _metric(raw)
        if metric is None:
            continue
        cell_line_value = raw.get("cell_line") or raw.get("cellline") or raw.get("cell_name")
        cell_line = str(cell_line_value).strip() if cell_line_value is not None and str(cell_line_value).strip() else None
        cell_lines.add(cell_line)
        grouped[(cell_line, metric)].append(raw)

    matrix: list[dict[str, Any]] = []
    for cell_line in sorted(cell_lines, key=lambda value: (value is None, (value or "").casefold())):
        for metric in METRICS:
            observations = grouped.get((cell_line, metric), [])
            if not observations:
                matrix.append({
                    "cell_line": cell_line,
                    "metric": metric,
                    "state": "NO_DATA",
                    "observation_count": 0,
                    "scores": [],
                    "contexts": [],
                    "context_dependent": False,
                    "warning": None,
                })
                continue

            context_groups: dict[tuple[Any, ...], dict[str, Any]] = {}
            all_labels: set[str] = set()
            observation_items = []
            for row in observations:
                context = _context(row)
                key = _context_key(context)
                bucket = context_groups.setdefault(key, {"context": context, "records": [], "interpretations": set()})
                label = _interpretation(row)
                if label:
                    bucket["interpretations"].add(label)
                    all_labels.add(label)
                bucket["records"].append(row)
                observation_items.append({
                    "score": row.get("score"),
                    "source": row.get("source"),
                    "source_id": row.get("source_id") or row.get("id"),
                    "url": row.get("url"),
                    "reported_interpretation": label,
                    "context": context,
                })

            comparable_conflict = False
            context_complete_flags = []
            for bucket in context_groups.values():
                context = bucket["context"]
                complete = all(context[field] is not None for field in _REQUIRED_COMPARISON_FIELDS)
                context_complete_flags.append(complete)
                if complete and len(bucket["interpretations"]) > 1:
                    comparable_conflict = True
            across_contexts = len(context_groups) > 1 and len(all_labels) > 1
            context_dependent = comparable_conflict or across_contexts
            if comparable_conflict:
                warning = "Conflicting source-reported interpretations exist for the same cell line, metric, and complete experimental context; review the source records."
            elif across_contexts:
                warning = "Source-reported interpretations differ across distinct experimental contexts; these observations are context-dependent and are not directly compared."
            elif not all(context_complete_flags):
                warning = "Experimental context is incomplete; contradiction/comparability cannot be assessed for all observations."
            else:
                warning = None
            matrix.append({
                "cell_line": cell_line,
                "metric": metric,
                "state": "OBSERVED",
                "observation_count": len(observations),
                "scores": observation_items,
                "contexts": [
                    {"context": bucket["context"], "record_count": len(bucket["records"]),
                     "reported_interpretations": sorted(bucket["interpretations"])}
                    for bucket in context_groups.values()
                ],
                "context_metadata_complete": all(context_complete_flags),
                "context_dependent": context_dependent,
                "warning": warning,
            })

    unavailable = source_status not in {"available", "ok", "success", "evidence_found", "partial"}
    has_observations = any(cell["state"] == "OBSERVED" for cell in matrix)
    status = "unavailable" if unavailable and not has_observations else ("available" if has_observations else "empty")
    return {
        "status": status,
        "metrics": list(METRICS),
        "cell_lines": [value for value in sorted(cell_lines, key=lambda item: (item is None, (item or "").casefold()))],
        "cells": matrix,
        "legend": {
            "NO_DATA": "No observation returned for this cell-line/metric pair; this does not mean additive, ineffective, or unsafe.",
            "OBSERVED": "One or more source-reported observations; scores are listed individually and never pooled.",
        },
        "interpretation": "Only explicit source interpretations are shown. Numerical scores are not assigned thresholds. Distinct studies, assays, concentrations, units, ratios, or contexts are not treated as directly comparable.",
    }
