from __future__ import annotations

from typing import Any
from .biomedical_data import unavailable
import httpx

API = "https://api.platform.opentargets.org/api/v4/graphql"


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid Open Targets response: expected {context} object")
    return value


def _list(value: object, context: str) -> list[Any]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"Invalid Open Targets response: expected {context} list of objects")
    return value

async def _graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent":"DrugDiscoverAI/0.1 (research prototype)"}) as client:
        response = await client.post(API, json={"query":query,"variables":variables})
        response.raise_for_status()
        result=response.json()
    if not isinstance(result, dict):
        raise ValueError("Invalid Open Targets GraphQL response: expected JSON object")
    if result.get("errors"):
        raise RuntimeError("Open Targets GraphQL returned errors")
    return _object(result.get("data"), "data")

async def search_diseases(query: str, limit: int = 8) -> dict[str, Any]:
    """Search disease entities. Returned identifiers and labels are source records."""
    if not query.strip():
        return {"status":"ok","source":"Open Targets","records":[]}
    gql='''query DiseaseSearch($q: String!, $size: Int!) {
      search(queryString: $q, entityNames: ["disease"], page: {index: 0, size: $size}) {
        hits { id name entity }
      }
    }'''
    try:
        data=await _graphql(gql,{"q":query,"size":max(1,min(limit,20))})
        search=_object(data.get("search"), "search")
        hits=_list(search.get("hits"), "search.hits")
        if any(not isinstance(hit.get("id"), str) or not isinstance(hit.get("name"), str) for hit in hits):
            raise ValueError("Invalid Open Targets response: search hit is missing disease ID or name")
        return {"status":"ok","source":"Open Targets","query":query,"records":[{"disease_id":h.get("id"),"disease_name":h.get("name"),"entity":h.get("entity"),"url":f"https://platform.opentargets.org/disease/{h.get('id')}"} for h in hits if h.get("id") and h.get("name")]}
    except Exception as exc:
        return unavailable("Open Targets",exc)

async def disease_targets(query: str, limit: int = 30) -> dict[str, Any]:
    """Resolve a disease label, then return associated target-gene records.

    Exact label matching is preferred. For non-exact input only a unique search
    result is accepted, avoiding silent selection among ambiguous diseases.
    """
    matches=await search_diseases(query)
    if matches.get("status") != "ok":
        return {**matches,"records":[],"query":query}
    records=matches.get("records",[])
    exact=[r for r in records if r["disease_name"].casefold()==query.strip().casefold()]
    selected=exact[0] if len(exact)==1 else (records[0] if len(records)==1 else None)
    if not selected:
        return {"status":"ambiguous" if records else "ok","source":"Open Targets","query":query,"records":[],"matches":records,"reason":"Disease name did not resolve uniquely; choose a source disease identifier." if records else "No disease match returned."}
    gql='''query DiseaseTargets($id: String!, $size: Int!) {
      disease(efoId: $id) {
        id name
        associatedTargets(page: {index: 0, size: $size}) {
          rows { score target { id approvedSymbol approvedName } datatypeScores { id score } }
        }
      }
    }'''
    try:
        data=await _graphql(gql,{"id":selected["disease_id"],"size":max(1,min(limit,100))})
        disease=data.get("disease")
        if not disease:
            return {"status":"ok","source":"Open Targets","disease":selected,"records":[],"reason":"No associated target rows returned."}
        associated=_object(disease.get("associatedTargets"), "disease.associatedTargets")
        rows=_list(associated.get("rows"), "associatedTargets.rows")
        out=[]
        for row in rows:
            target=row.get("target") or {}
            symbol=target.get("approvedSymbol")
            if not symbol: continue
            out.append({"gene_symbol":symbol,"target_id":target.get("id"),"target_name":target.get("approvedName"),"source":"Open Targets","source_id":f"{disease.get('id')}:{target.get('id')}","score":row.get("score"),"evidence":row.get("datatypeScores"),"url":f"https://platform.opentargets.org/disease/{disease.get('id')}/associations"})
        return {"status":"ok","source":"Open Targets","disease":{"id":disease.get("id"),"name":disease.get("name")},"records":out}
    except Exception as exc:
        return unavailable("Open Targets",exc)

