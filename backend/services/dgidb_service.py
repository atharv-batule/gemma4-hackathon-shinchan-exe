from .biomedical_data import get_json, unavailable

async def drug_gene_interactions(genes: list[str]) -> dict:
    if not genes: return {"status":"ok","source":"DGIdb","records":[]}
    try:
        data=await get_json("https://dgidb.org/api/v2/interactions.json", {"genes":','.join(genes)})
        return {"status":"ok","source":"DGIdb","records":data.get("matchedTerms",[])}
    except Exception as e: return unavailable("DGIdb", e)
