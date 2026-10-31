from __future__ import annotations
import time
from typing import Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from backend.services.provenance_ledger import attach_provenance, build_evidence_ledger, make_source_check, source_checks_snapshot

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
    result["synergy_heatmap"] = build_synergy_heatmap(
        result.get("evidence", []), source_status=records.get("status", "unavailable")
    )
    return contract(result,t)
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
@app.get("/api/evidence/{candidate_id}")
def evidence(candidate_id: str):
    t=time.perf_counter(); return contract({"status":"unavailable", "items":[], "reason":"No candidate evidence cache is configured.", "candidate_id":candidate_id},t)
@app.get("/api/knowledge-graph/{disease}")
def graph(disease: str):
    t=time.perf_counter(); return contract({"status":"unavailable", "nodes":[], "edges":[], "reason":"No disease-target evidence provider configured."},t)
@app.get("/api/research/report/{report_id}")
def report(report_id: str):
    t=time.perf_counter(); return contract({"status":"not_found", "report":None, "report_id":report_id},t)


