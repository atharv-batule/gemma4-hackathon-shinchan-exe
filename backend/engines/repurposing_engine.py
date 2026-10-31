"""Disease-to-target-to-drug evidence workflow."""
from __future__ import annotations

import inspect
import time
from typing import Any, Callable

from .target_analysis import build_target_evidence, rank_candidates


async def _call(provider: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> Any:
    if provider is None:
        return None
    value = provider(*args, **kwargs)
    return await value if inspect.isawaitable(value) else value


async def analyze_disease(
    disease: str,
    *,
    disease_gene_provider: Callable[..., Any] | None = None,
    drug_target_provider: Callable[..., Any] | None = None,
    publication_provider: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Collect available evidence and return candidates with provenance.

    Providers are injectable to support public API implementations and tests.
    Missing providers or failed sources are reported as unavailable; no local
    demo records or assumed associations are substituted.
    """
    started = time.perf_counter()
    query = disease.strip() if isinstance(disease, str) else ""
    if not query:
        raise ValueError("A non-empty disease query is required.")

    # Default to the configured public adapters. Provider injection remains
    # available for tests and deployments using alternate licensed sources.
    if disease_gene_provider is None:
        from backend.services.opentargets_service import disease_targets
        disease_gene_provider = disease_targets
    if drug_target_provider is None:
        from backend.services.chembl_service import drug_targets_for_genes
        drug_target_provider = drug_targets_for_genes
    if publication_provider is None:
        from backend.services.pubmed_service import search
        publication_provider = search

    sources: dict[str, dict[str, Any]] = {}
    gene_data, gene_error = await _safe_call(disease_gene_provider, query)
    sources["disease_gene"] = _source_status(gene_data, gene_error)

    genes = _records(gene_data)
    symbols = list(dict.fromkeys(str(x.get("gene_symbol") or x.get("symbol") or x.get("target")) for x in genes if x.get("gene_symbol") or x.get("symbol") or x.get("target")))
    if symbols and _provider_succeeded(gene_data, gene_error):
        drug_data, drug_error = await _safe_call(drug_target_provider, symbols, disease=query)
    else:
        # Do not turn an empty/unavailable target lookup into a successful
        # ChEMBL query over an empty list; expose that this stage was skipped.
        drug_data, drug_error = {"status": "not_run", "records": [], "reason": "No resolved disease target symbols were available."}, None
    sources["drug_target"] = _source_status(drug_data, drug_error)

    publication_data, publication_error = await _safe_call(publication_provider, query)
    sources["publications"] = _source_status(publication_data, publication_error)

    target_evidence = build_target_evidence(gene_data, drug_data)
    candidates = rank_candidates(target_evidence["targets"])
    core = (sources["disease_gene"], sources["drug_target"])
    if all(s["status"] == "available" for s in core):
        status = "ok"
    elif all(s["status"] in ("unavailable", "not_run") for s in core):
        status = "unavailable"
    else:
        status = "partial"
    return {
        "status": status,
        "pipeline_latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "data": {
            "query": query,
            "candidates": candidates,
            "targets": target_evidence["targets"],
            "publications": _records(publication_data),
            "sources": sources,
            "limitations": [
                "Target associations generate research hypotheses and do not establish therapeutic efficacy.",
                "Evidence completeness scores describe record coverage only.",
                "Experimental, preclinical, and clinical evidence are not inferred when not explicitly present.",
                "An unavailable source or absent record is not evidence of no biological relationship.",
            ],
        },
    }


async def _safe_call(provider: Callable[..., Any] | None, *args: Any, **kwargs: Any) -> tuple[Any, str | None]:
    if provider is None:
        return None, "provider_not_configured"
    try:
        return await _call(provider, *args, **kwargs), None
    except Exception as exc:  # API errors are data availability, not empty evidence.
        return None, f"{type(exc).__name__}: {exc}"


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        value = value.get("records", value.get("results", value.get("data", [])))
    return [x for x in value if isinstance(x, dict)] if isinstance(value, (list, tuple)) else []


def _source_status(value: Any, error: str | None) -> dict[str, Any]:
    records = _records(value)
    if error:
        return {"status": "unavailable", "record_count": None, "detail": error}
    if isinstance(value, dict) and value.get("status") not in (None, "ok", "available", "success"):
        return {"status": value.get("status", "unavailable"), "record_count": len(records), "detail": value.get("reason") or value.get("error"), **({"matches": value["matches"]} if value.get("matches") is not None else {})}
    return {"status": "available", "record_count": len(records), "detail": None}


def _provider_succeeded(value: Any, error: str | None) -> bool:
    if error or value is None:
        return False
    return not isinstance(value, dict) or value.get("status") in (None, "ok", "available", "success")


# Compatibility alias for callers that use the engine verb as a function name.
repurpose = analyze_disease
