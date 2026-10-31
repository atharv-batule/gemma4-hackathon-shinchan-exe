from __future__ import annotations
import time
from typing import Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from backend.services.provenance_ledger import (
    annotate_heatmap_provenance, attach_provenance, build_evidence_ledger,
    find_provenance_records, get_provenance_record, make_source_check, source_checks_snapshot,
)

load_dotenv()

app = FastAPI(title="DrugDiscover AI", description="Evidence-grounded biomedical research screening. Not for clinical use.", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
class Query(BaseModel): disease: str = Field(min_length=2, max_length=160)
class Molecule(BaseModel): smiles: str
class Pair(BaseModel): drug_a: str; drug_b: str
class ClaimVerificationRequest(BaseModel):
    claims: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ledger: list[dict[str, Any]] = Field(default_factory=list)

def contract(result: dict[str, Any], started: float) -> dict[str, Any]:
    result.setdefault("status", "ok")
    result.setdefault("pipeline_latency_ms", round((time.perf_counter()-started)*1000, 2))
    result.setdefault("reasoning_trace", [])
    if "data" not in result:
        result["data"] = {k:v for k,v in result.items() if k not in {"status", "pipeline_latency_ms", "reasoning_trace"}}
    return result

@app.get("/health")
def health(): return {"status":"ok", "service":"DrugDiscover AI", "scope":"computational research screening only", "source_checks":source_checks_snapshot()}
@app.get("/api/diseases/search")
async def disease_search(q: str):
    from backend.services.opentargets_service import search_diseases
    t=time.perf_counter(); result=await search_diseases(q)
    attach_provenance(result, {"Open Targets":("Open Targets",result)})
    return contract(result,t)
@app.get("/api/drugs/search")
async def drug_search(q: str):
    from backend.services.pubchem_service import search_drug
    from backend.services.chembl_service import search_drug as chembl_search
    import asyncio
    t=time.perf_counter(); pubchem, chembl = await asyncio.gather(search_drug(q), chembl_search(q))
    result={"status":"ok" if "ok" in (pubchem.get("status"),chembl.get("status")) else "unavailable", "query":q,"sources":{"PubChem":pubchem,"ChEMBL":chembl}}
    attach_provenance(result, {"PubChem":("PubChem",pubchem),"ChEMBL":("ChEMBL",chembl)})
    return contract(result,t)
@app.post("/api/repurposing/analyze")
async def repurpose(q: Query):
    from backend.engines.repurposing_engine import analyze_disease
    t=time.perf_counter(); result=await analyze_disease(q.disease)
    sources=result.get("data",{}).get("sources",{})
    provider_map={"disease_gene":"Open Targets","drug_target":"ChEMBL","publications":"PubMed"}
    attach_provenance(result, {key:(provider_map.get(key,key),value) for key,value in sources.items()})
    return contract(result,t)
@app.post("/api/combinations/analyze")
async def combinations(q: Pair):
    from backend.engines.combination_engine import analyze_combination
    from backend.engines.synergy_heatmap import build_synergy_heatmap
    from backend.services.drugcomb_service import search_combinations
    t=time.perf_counter(); records=await search_combinations(q.drug_a,q.drug_b)
    result=analyze_combination(q.drug_a,q.drug_b,records)
    # Build provenance from the retrieved source records before adding the
    # derived ratio/heatmap views, so summaries do not become duplicate rows.
    attach_provenance(result, {"DrugComb":("DrugComb",records)})
    result["evidence_ledger"] = build_evidence_ledger({"evidence": result.get("evidence", [])})
    result["synergy_heatmap"] = annotate_heatmap_provenance(
        build_synergy_heatmap(
            result.get("evidence", []), source_status=records.get("status", "unavailable")
        ),
        result["evidence_ledger"],
    )
    return contract(result,t)
@app.get("/api/combinations/mock-demo")
def combination_mock_demo():
    """Clearly labelled mock DrugComb fixture demonstrating cell-line x metric synergy heatmap."""
    from backend.engines.combination_engine import analyze_combination
    from backend.engines.synergy_heatmap import build_synergy_heatmap
    t = time.perf_counter()
    drug_a = "Gefitinib"
    drug_b = "Osimertinib"
    mock_records = [
        {"source": "DrugComb (Mock)", "source_id": "mock-block-101", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "A549", "metric": "ZIP", "score": 18.5, "reported_interpretation": "synergistic",
         "study": "DEMO-ALMANAC", "assay": "72h viability", "concentration_a": 1.0, "concentration_b": 2.0,
         "concentration_unit": "uM", "ratio": "1:2", "url": "https://example.invalid/mock-block-101",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-101", "metric": "ZIP", "score": 18.5, "cell": "A549"}},
        {"source": "DrugComb (Mock)", "source_id": "mock-block-102", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "A549", "metric": "Bliss", "score": 8.7, "reported_interpretation": "synergy",
         "study": "DEMO-ALMANAC", "assay": "72h viability", "concentration_a": 1.0, "concentration_b": 2.0,
         "concentration_unit": "uM", "ratio": "1:2", "url": "https://example.invalid/mock-block-102",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-102", "metric": "Bliss", "score": 8.7, "cell": "A549"}},
        {"source": "DrugComb (Mock)", "source_id": "mock-block-103", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "A549", "metric": "Loewe", "score": 0.2, "reported_interpretation": "additive",
         "study": "DEMO-ALMANAC", "assay": "72h viability", "concentration_a": 1.0, "concentration_b": 2.0,
         "concentration_unit": "uM", "ratio": "1:2", "url": "https://example.invalid/mock-block-103",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-103", "metric": "Loewe", "score": 0.2, "cell": "A549"}},
        {"source": "DrugComb (Mock)", "source_id": "mock-block-104", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "A549", "metric": "HSA", "score": -16.4, "reported_interpretation": "antagonistic",
         "study": "DEMO-ALMANAC", "assay": "72h viability", "concentration_a": 1.0, "concentration_b": 2.0,
         "concentration_unit": "uM", "ratio": "1:2", "url": "https://example.invalid/mock-block-104",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-104", "metric": "HSA", "score": -16.4, "cell": "A549"}},
        {"source": "DrugComb (Mock)", "source_id": "mock-block-201", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "MCF7", "metric": "ZIP", "score": 4.6, "reported_interpretation": "positive",
         "study": "DEMO-ONEIL", "assay": "cell titer", "concentration_a": 0.5, "concentration_b": 1.0,
         "concentration_unit": "uM", "ratio": "1:2", "url": "https://example.invalid/mock-block-201",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-201", "metric": "ZIP", "score": 4.6, "cell": "MCF7"}},
        {"source": "DrugComb (Mock)", "source_id": "mock-block-202", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "MCF7", "metric": "Bliss", "score": -8.4, "reported_interpretation": "antagonistic",
         "study": "DEMO-ONEIL", "assay": "cell titer", "concentration_a": 0.5, "concentration_b": 1.0,
         "concentration_unit": "uM", "ratio": "1:2", "url": "https://example.invalid/mock-block-202",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-202", "metric": "Bliss", "score": -8.4, "cell": "MCF7"}},
        {"source": "DrugComb (Mock)", "source_id": "mock-block-203", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "MCF7", "metric": "Loewe", "score": 3.1, "reported_interpretation": "positive",
         "study": "DEMO-ONEIL", "assay": "cell titer", "concentration_a": 0.5, "concentration_b": 1.0,
         "concentration_unit": "uM", "ratio": "1:2", "url": "https://example.invalid/mock-block-203",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-203", "metric": "Loewe", "score": 3.1, "cell": "MCF7"}},
        {"source": "DrugComb (Mock)", "source_id": "mock-block-301", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "H1299", "metric": "ZIP", "score": 9.2, "reported_interpretation": "synergistic",
         "study": "DEMO-CLOUD-1", "assay": "viability", "concentration_a": 2.0, "concentration_b": 4.0,
         "concentration_unit": "uM", "ratio": "1:2", "url": "https://example.invalid/mock-block-301",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-301", "metric": "ZIP", "score": 9.2, "cell": "H1299"}},
        {"source": "DrugComb (Mock)", "source_id": "mock-block-302", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "H1299", "metric": "ZIP", "score": -2.8, "reported_interpretation": "antagonistic",
         "study": "DEMO-CLOUD-2", "assay": "colony formation", "concentration_a": 0.2, "concentration_b": 0.5,
         "concentration_unit": "uM", "ratio": "1:2.5", "url": "https://example.invalid/mock-block-302",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-302", "metric": "ZIP", "score": -2.8, "cell": "H1299"}},
        {"source": "DrugComb (Mock)", "source_id": "mock-block-303", "drug_a": drug_a, "drug_b": drug_b,
         "cell_line": "H1299", "metric": "Bliss", "score": 0.0, "reported_interpretation": "neutral",
         "study": "DEMO-CLOUD-1", "assay": "viability", "concentration_a": 2.0, "concentration_b": 4.0,
         "concentration_unit": "uM", "ratio": "1:2", "url": "https://example.invalid/mock-block-303",
         "raw_display_permitted": True, "source_record": {"block_id": "mock-303", "metric": "Bliss", "score": 0.0, "cell": "H1299"}},
    ]
    result = analyze_combination(drug_a, drug_b, mock_records, source_status="available")
    result["is_mock_fixture"] = True
    result["fixture_notice"] = "Clearly labelled demonstration fixture: Synthetic DrugComb records demonstrating cell-line x metric synergy heatmap, diverging color-blind-safe styling, context warnings, and provenance ledger audit links. Not live biomedical data."
    envelope = {"status": "available", "source": "DrugComb (Mock)", "records": mock_records}
    attach_provenance(result, {"DrugComb": ("DrugComb (Mock)", envelope)})
    result["evidence_ledger"] = build_evidence_ledger({"evidence": result.get("evidence", [])})
    result["synergy_heatmap"] = build_synergy_heatmap(
        result.get("evidence", []), source_status="available"
    )
    result["safety"] = {
        "status": "unavailable", "decision": "REVIEW", "ddi_risk_level": "UNKNOWN",
        "error": "Drug interaction data requires authorized DrugBank credentials; missing DDI evidence remains UNKNOWN/REVIEW."
    }
    return contract(result, t)
@app.post("/api/safety/evaluate")
async def safety(q: Pair):
    from backend.engines.safety_engine import evaluate_safety
    from backend.services.drugbank_service import interaction_lookup
    t=time.perf_counter(); ddi=interaction_lookup(q.drug_a,q.drug_b)
    result=evaluate_safety(q.drug_a,q.drug_b,ddi.get("records",[]),ddi_status=ddi.get("status","unavailable"))
    attach_provenance(result, {"DrugBank":("DrugBank",ddi)})
    result["ddi_source_check"] = result["source_checks"]["DrugBank"]
    return contract(result,t)
@app.post("/api/molecular/validate")
def molecular(q: Molecule):
    from backend.engines.molecular_engine import validate_smiles
    t=time.perf_counter(); return contract(validate_smiles(q.smiles),t)
@app.post("/api/discovery/combined")
async def combined(q: Query):
    from backend.engines.repurposing_engine import analyze_disease
    t=time.perf_counter(); result=await analyze_disease(q.disease)
    result.setdefault("combination_analysis", {"status":"not_run", "reason":"Select identified compounds to investigate experimentally."})
    result.setdefault("safety_evaluation", {"decision":"REVIEW", "decision_scope":"Computational research screening only", "flagged_toxicophores":None, "ddi_risk_level":"UNKNOWN"})
    result.setdefault("research_hypothesis", None); result.setdefault("reconstructed_molecules", [])
    sources=result.get("data",{}).get("sources",{})
    provider_map={"disease_gene":"Open Targets","drug_target":"ChEMBL","publications":"PubMed"}
    attach_provenance(result, {key:(provider_map.get(key,key),value) for key,value in sources.items()})
    return contract(result,t)
@app.post("/api/ai/explain")
def explain(payload: dict[str, Any]):
    from backend.ai.gemma_service import explain_evidence
    t=time.perf_counter(); result=explain_evidence(payload)
    source_check=make_source_check("Gemma",result)
    result["source_checks"]={"Gemma":source_check}
    return contract(result,t)
@app.post("/api/ai/verify-claims")
def verify_claims_route(payload: ClaimVerificationRequest):
    """Deterministic source-ID and structured-field verification; no LLM judge."""
    from backend.ai.citation_verifier import verify_claims
    t=time.perf_counter()
    result=verify_claims(payload.claims, payload.evidence_ledger)
    return contract(result,t)
MAX_PROVENANCE_ID_LENGTH = 512

def _clean_provenance_id(value: Any) -> str | None:
    """Return a normalized identifier or None when it is unusable."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_PROVENANCE_ID_LENGTH:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in cleaned):
        return None
    return cleaned

def _provenance_failure(detail: str) -> JSONResponse:
    return JSONResponse(status_code=503, content={
        "status": "unavailable", "records": [], "record": None,
        "reason": f"Provenance store could not be read: {detail}",
    })

@app.get("/api/provenance/records")
def provenance_records(record_id: str | None = None, source: str | None = None,
                       source_id: str | None = None, experiment_id: str | None = None):
    """Retrieve stored provenance records by exact record/source/experiment ID."""
    filters = {}
    for name, value in (("record_id", record_id), ("source_id", source_id), ("experiment_id", experiment_id)):
        if value is None:
            continue
        cleaned = _clean_provenance_id(value)
        if cleaned is None:
            return JSONResponse(status_code=400, content={
                "status": "invalid_request", "records": [],
                "reason": f"'{name}' is not a valid provenance identifier.",
            })
        filters[name] = cleaned
    if source is not None:
        cleaned_source = _clean_provenance_id(source)
        if cleaned_source is None:
            return JSONResponse(status_code=400, content={
                "status": "invalid_request", "records": [],
                "reason": "'source' is not a valid source label.",
            })
        filters["source"] = cleaned_source
    if not filters:
        return JSONResponse(status_code=400, content={
            "status": "invalid_request", "records": [],
            "reason": "At least one exact filter (record_id, source, source_id or experiment_id) is required.",
        })
    try:
        records = find_provenance_records(**filters)
    except Exception as exc:
        return _provenance_failure(type(exc).__name__)
    if not records:
        return JSONResponse(status_code=404, content={
            "status": "not_found", "records": [], "count": 0,
            "reason": "No stored provenance record matches the supplied exact identifiers.",
            "filters": filters,
        })
    return {
        "status": "found" if len(records) == 1 else "ambiguous",
        "records": records, "count": len(records), "filters": filters,
        "ambiguous": len(records) > 1,
    }

@app.get("/api/provenance/records/{record_id:path}")
def provenance_record(record_id: str):
    """Retrieve one stored provenance record by its exact record_id."""
    cleaned = _clean_provenance_id(record_id)
    if cleaned is None:
        return JSONResponse(status_code=400, content={
            "status": "invalid_record_id", "record": None, "records": [],
            "record_id": record_id,
            "reason": "The record ID is empty, too long, or contains control characters.",
        })
    try:
        record = get_provenance_record(cleaned)
    except Exception as exc:
        return _provenance_failure(type(exc).__name__)
    if record is None:
        return JSONResponse(status_code=404, content={
            "status": "not_found", "record": None, "records": [],
            "record_id": cleaned,
            "reason": "No stored provenance record has this record_id.",
        })
    return {"status": "found", "record": record, "records": [record], "record_id": cleaned}

@app.get("/api/evidence/{candidate_id}")
def evidence(candidate_id: str):
    t=time.perf_counter(); return contract({"status":"unavailable", "items":[], "reason":"No candidate evidence cache is configured.", "candidate_id":candidate_id},t)
@app.get("/api/knowledge-graph/{disease}")
def graph(disease: str):
    t=time.perf_counter(); return contract({"status":"unavailable", "nodes":[], "edges":[], "reason":"No disease-target evidence provider configured."},t)
@app.get("/api/research/report/{report_id}")
def report(report_id: str):
    t=time.perf_counter(); return contract({"status":"not_found", "report":None, "report_id":report_id},t)
