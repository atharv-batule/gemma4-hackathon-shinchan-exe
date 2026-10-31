from __future__ import annotations
import asyncio
from .biomedical_data import get_json, unavailable

BASE = "https://www.ebi.ac.uk/chembl/api/data"


def _rows(payload: object, key: str) -> list[dict]:
    """Validate the collection envelope returned by ChEMBL's JSON API."""
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise ValueError(f"Invalid ChEMBL response: expected a '{key}' list")
    rows = payload[key]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Invalid ChEMBL response: '{key}' contains a non-object row")
    return rows

def _normalize_activity(row: dict) -> dict:
    molecule_id=row.get("molecule_chembl_id")
    target_id=row.get("target_chembl_id")
    return {"drug_name":row.get("molecule_pref_name") or molecule_id,"drug_id":molecule_id,"target_id":target_id,"gene_symbol":row.get("target_symbol"),"mechanism":row.get("action_type"),"action":row.get("action_type"),"activity_type":row.get("standard_type"),"activity_value":row.get("standard_value"),"units":row.get("standard_units"),"pchembl_value":row.get("pchembl_value"),"assay_description":row.get("assay_description"),"assay_id":row.get("assay_chembl_id"),"assay_cell_type":row.get("assay_cell_type"),"assay_tissue":row.get("assay_tissue"),"assay_organism":row.get("assay_organism"),"bao_label":row.get("bao_label"),"confidence_score":row.get("confidence_score"),"source":"ChEMBL","source_id":row.get("activity_id"),"url":f"https://www.ebi.ac.uk/chembl/compound_report_card/{molecule_id}" if molecule_id else None}

async def search_drug(name: str) -> dict:
    try:
        data=await get_json(f"{BASE}/molecule.json", {"pref_name__ilike":name, "limit":20})
        return {"status":"ok", "source":"ChEMBL", "records":_rows(data, "molecules")}
    except Exception as e: return unavailable("ChEMBL", e)

async def target_activities(target_id: str) -> dict:
    try:
        data=await get_json(f"{BASE}/activity.json", {"target_chembl_id":target_id,"limit":100})
        return {"status":"ok", "source":"ChEMBL", "records":_rows(data, "activities")}
    except Exception as e: return unavailable("ChEMBL", e)

async def _activities_for_target(target_id: str, gene_symbol: str) -> list[dict]:
    data=await get_json(f"{BASE}/activity.json", {"target_chembl_id":target_id,"limit":100,"format":"json"})
    rows=_rows(data, "activities")
    out=[]
    for row in rows:
        # Prefer target-specific, curated binding/functional measurements. Do
        # not turn unqualified assay records into mechanistic evidence.
        if row.get("confidence_score") not in (None, 8, 9): continue
        if not row.get("molecule_chembl_id"): continue
        item=_normalize_activity({**row,"target_symbol":gene_symbol})
        if item.get("activity_value") is not None:
            item["evidence_class"]="experimental assay record"
        else:
            item["evidence_class"]="drug-target record; activity value not reported"
        out.append(item)
    return out

async def drug_targets_for_genes(gene_symbols: list[str], *, disease: str | None = None, per_gene_limit: int = 100) -> dict:
    """Retrieve ChEMBL target activities for gene symbols with source IDs/assay context."""
    genes=list(dict.fromkeys(g.strip() for g in gene_symbols if isinstance(g,str) and g.strip()))[:15]
    if not genes: return {"status":"ok","source":"ChEMBL","records":[],"reason":"No target symbols were provided."}
    async def one_gene(gene: str):
        # ChEMBL target synonyms contain gene symbols for many curated targets.
        return gene, await get_json(f"{BASE}/target.json", {"target_synonym__icontains":gene,"limit":20,"format":"json"})
    try:
        target_results=await asyncio.gather(*(one_gene(g) for g in genes),return_exceptions=True)
        tasks=[]; seen=set(); errors=[]
        for item in target_results:
            if isinstance(item,Exception): errors.append(type(item).__name__); continue
            gene,data=item
            for target in _rows(data, "targets"):
                # Only human targets and curated single-protein targets are
                # appropriate for gene-level target associations here.
                if target.get("organism") not in (None,"Homo sapiens"): continue
                if target.get("target_type") not in (None,"SINGLE PROTEIN"): continue
                target_id=target.get("target_chembl_id")
                if not target_id or target_id in seen: continue
                seen.add(target_id); tasks.append((gene,target_id))
        results=await asyncio.gather(*(_activities_for_target(t,g) for g,t in tasks),return_exceptions=True)
        records=[]
        for pair,result in zip(tasks,results):
            if isinstance(result,Exception): errors.append(type(result).__name__)
            else: records.extend(result)
        status = "partial" if errors and records else ("unavailable" if errors else "ok")
        return {"status":status,"source":"ChEMBL","query_genes":genes,"records":records[:per_gene_limit*len(genes)],"target_count":len(tasks),"errors":errors or None}
    except Exception as exc:
        return unavailable("ChEMBL",exc)



