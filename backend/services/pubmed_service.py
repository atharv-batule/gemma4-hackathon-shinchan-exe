from .biomedical_data import get_json, unavailable


def _object(value, context: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid PubMed response: expected {context} object")
    return value


def _pmids(payload: object) -> list[str]:
    root = _object(payload, "ESearch root")
    result = _object(root.get("esearchresult"), "ESearch result")
    ids = result.get("idlist")
    if not isinstance(ids, list) or any(not isinstance(pmid, (str, int)) for pmid in ids):
        raise ValueError("Invalid PubMed response: expected esearchresult.idlist")
    return [str(pmid) for pmid in ids]

async def search(query: str, limit: int=10) -> dict:
    try:
        ids=await get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", {"db":"pubmed","term":query,"retmode":"json","retmax":max(1,min(int(limit),100))})
        pmids=_pmids(ids)
        if not pmids: return {"status":"ok","source":"PubMed","records":[]}
        summary=await get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", {"db":"pubmed","id":','.join(pmids),"retmode":"json"})
        root=_object(summary, "ESummary root")
        result=_object(root.get("result"), "ESummary result")
        records=[]
        for pmid in pmids:
            row=result.get(pmid)
            if row is not None:
                row=_object(row, f"ESummary record {pmid}")
                records.append({**row, "pmid":pmid, "source":"PubMed", "source_url":f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"})
        return {"status":"ok","source":"PubMed","records":records,"requested_pmids":pmids,"missing_pmids":[pmid for pmid in pmids if not any(row["pmid"] == pmid for row in records)]}
    except Exception as e: return unavailable("PubMed", e)
