"""DrugComb experimental evidence adapter.

DrugComb's public API host and response resource are known, but this adapter
does not guess a query parameter contract. Configure the parameter names after
checking the current API documentation/version deployed for your environment.
Returned scores are source records; no synergy is calculated here.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from .biomedical_data import HEADERS, TIMEOUT

DEFAULT_BASE = "https://api.drugcomb.org"
DEFAULT_RESPONSE_PATH = "/response/"


def _extract_rows(payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(payload, list):
        return payload if all(isinstance(row, dict) for row in payload) else None
    if isinstance(payload, dict):
        for key in ("records", "results", "data", "response"):
            value = payload.get(key)
            if isinstance(value, list):
                return value if all(isinstance(row, dict) for row in value) else None
    return None


def _normalize(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Map only explicitly returned columns; retain full original row."""
    metric_keys = {
        "ZIP": ("ZIP", "zip", "synergy_zip", "zip_score"),
        "Bliss": ("Bliss", "bliss", "synergy_bliss", "bliss_score"),
        "Loewe": ("Loewe", "loewe", "synergy_loewe", "loewe_score"),
        "HSA": ("HSA", "hsa", "synergy_hsa", "hsa_score"),
    }
    base = {
        "source": "DrugComb",
        "source_id": row.get("source_id") or row.get("id") or row.get("block_id") or row.get("blockid"),
        "drug_a": row.get("drug_a") or row.get("drug_row") or row.get("drug1"),
        "drug_b": row.get("drug_b") or row.get("drug_col") or row.get("drug2"),
        "cell_line": row.get("cell_line") or row.get("cellline") or row.get("cell_name"),
        "concentration_a": row.get("concentration_a", row.get("conc_row", row.get("conc1"))),
        "concentration_b": row.get("concentration_b", row.get("conc_col", row.get("conc2"))),
        "concentration_unit": row.get("concentration_unit") or row.get("unit"),
        "ratio": row.get("ratio"),
        "study": row.get("study") or row.get("study_name") or row.get("dataset") or row.get("source_name"),
        "assay": row.get("assay") or row.get("assay_type"),
        "citation": row.get("citation") or row.get("reference"),
        "pmid": row.get("pmid"),
        "doi": row.get("doi"),
        "url": row.get("url"),
        "source_record": dict(row),
    }
    # The API may return either a one-metric record or a summary row with
    # separate metric columns. Emit only values actually present.
    direct_metric = row.get("metric") or row.get("synergy_method")
    if direct_metric is not None and ("score" in row or "synergy_score" in row):
        return [{**base, "metric": direct_metric, "score": row.get("score", row.get("synergy_score"))}]
    out = []
    for metric, candidates in metric_keys.items():
        for key in candidates:
            if key in row and row[key] is not None:
                out.append({**base, "metric": metric, "score": row[key]})
                break
    return out


async def search_combinations(drug_a: str, drug_b: str, *, cell_line: str | None = None) -> dict[str, Any]:
    if not drug_a.strip() or not drug_b.strip():
        return {"status": "invalid_request", "source": "DrugComb", "records": [], "error": "Both drug identifiers or names are required."}

    # The API host and /response/ endpoint are public, but endpoint query
    # parameter names vary across API releases and are not assumed here.
    drug_a_param = os.getenv("DRUGCOMB_DRUG_A_PARAM", "").strip()
    drug_b_param = os.getenv("DRUGCOMB_DRUG_B_PARAM", "").strip()
    if not drug_a_param or not drug_b_param:
        return {
            "status": "unavailable", "source": "DrugComb", "records": [],
            "endpoint": DEFAULT_BASE + DEFAULT_RESPONSE_PATH,
            "error": "DrugComb API is public, but query parameter names are not configured. Set DRUGCOMB_DRUG_A_PARAM and DRUGCOMB_DRUG_B_PARAM after verifying the deployed API contract.",
        }

    base = os.getenv("DRUGCOMB_API_BASE", DEFAULT_BASE).rstrip("/")
    path = os.getenv("DRUGCOMB_RESPONSE_PATH", DEFAULT_RESPONSE_PATH)
    if not path.startswith("/"):
        path = "/" + path
    params = {drug_a_param: drug_a.strip(), drug_b_param: drug_b.strip()}
    cell_param = os.getenv("DRUGCOMB_CELL_LINE_PARAM", "").strip()
    if cell_line and cell_param:
        params[cell_param] = cell_line.strip()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
            response = await client.get(base + path, params=params)
            response.raise_for_status()
            payload = response.json()
        rows = _extract_rows(payload)
        if rows is None:
            return {"status": "unavailable", "source": "DrugComb", "records": [], "error": "DrugComb response schema was not a recognized list of records; raw payload was not interpreted."}
        records = [record for row in rows for record in _normalize(row)]
        # When the provider returned drug names, retain only rows matching this
        # request. Do not infer aliases or salt equivalence here.
        a, b = drug_a.strip().casefold(), drug_b.strip().casefold()
        records = [r for r in records if not r.get("drug_a") or not r.get("drug_b") or
                   ({str(r["drug_a"]).casefold(), str(r["drug_b"]).casefold()} == {a, b})]
        return {"status": "ok", "source": "DrugComb", "records": records, "record_count": len(records), "endpoint": base + path, "query": {"drug_a": drug_a, "drug_b": drug_b, "cell_line": cell_line}}
    except (httpx.HTTPError, ValueError) as exc:
        return {"status": "unavailable", "source": "DrugComb", "records": [], "endpoint": base + path, "error": f"DrugComb request failed ({type(exc).__name__})."}
