"""PubChem PUG REST lookup with explicit compound ambiguity and provenance.

Properties returned here are PubChem records, not locally computed descriptors.
Names are resolved to CIDs first so a fuzzy/multi-match lookup is never
silently treated as a single identified drug.
"""
from __future__ import annotations

from urllib.parse import quote
import httpx

from .biomedical_data import get_json, unavailable

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PROPERTY_NAMES = (
    # Current PUG REST property names (Canonical/IsomericSMILES were renamed).
    "IUPACName,ConnectivitySMILES,SMILES,MolecularFormula,MolecularWeight,"
    "XLogP,TPSA,HBondDonorCount,HBondAcceptorCount,RotatableBondCount,InChIKey"
)
MAX_CANDIDATES = 10


def _property_rows(payload: object) -> list[dict]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid PubChem response: expected a JSON object")
    table = payload.get("PropertyTable")
    if not isinstance(table, dict) or not isinstance(table.get("Properties"), list):
        raise ValueError("Invalid PubChem response: expected PropertyTable.Properties list")
    rows = table["Properties"]
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid PubChem response: Properties contains a non-object row")
    return rows


def _cids(payload: object) -> list[int]:
    if not isinstance(payload, dict):
        raise ValueError("Invalid PubChem response: expected a JSON object")
    identifiers = payload.get("IdentifierList")
    if not isinstance(identifiers, dict) or not isinstance(identifiers.get("CID"), list):
        raise ValueError("Invalid PubChem response: expected IdentifierList.CID list")
    values = identifiers["CID"]
    if any(isinstance(cid, bool) or not str(cid).isdigit() or int(cid) <= 0 for cid in values):
        raise ValueError("Invalid PubChem response: CID list contains an invalid identifier")
    return list(dict.fromkeys(int(cid) for cid in values))


def _not_found(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404


async def search_drug(name: str, *, limit: int = MAX_CANDIDATES) -> dict:
    """Resolve a submitted name to CIDs, then fetch PubChem property records.

    Multiple matches are preserved in `records` and flagged `ambiguous`; the
    caller must disambiguate salts, stereoisomers, and formulation variants.
    """
    query = name.strip() if isinstance(name, str) else ""
    if not query:
        return {"status": "invalid_query", "source": "PubChem PUG REST", "query": query, "records": [], "error": "A non-empty compound name is required."}
    if len(query) > 256:
        return {"status": "invalid_query", "source": "PubChem PUG REST", "query": query, "records": [], "error": "Compound query exceeds 256 characters."}

    # Encode the name as one path segment (e.g. '/', '&', and spaces cannot
    # change the PUG REST route or query semantics).
    encoded = quote(query, safe="")
    meta: dict = {}
    try:
        ids_json = await get_json(f"{BASE}/compound/name/{encoded}/cids/JSON", meta=meta)
        cids = _cids(ids_json)
        safe_limit = max(1, min(int(limit), 50))
        cids = cids[:safe_limit]
        if not cids:
            return {"status": "not_found", "source": "PubChem PUG REST", "query": query, "records": [], "ambiguous": False, "error": None}

        property_meta: dict = {}
        property_json = await get_json(f"{BASE}/compound/cid/{','.join(map(str, cids))}/property/{PROPERTY_NAMES}/JSON", meta=property_meta)
        records = _property_rows(property_json)
        # Keep only actual service records. Do not fill absent properties.
        records = [dict(record, source="PubChem PUG REST", source_url=f"{BASE}/compound/cid/{record.get('CID')}/property/{PROPERTY_NAMES}/JSON") for record in records if isinstance(record, dict)]
        returned_cids = {record.get("CID") for record in records}
        return {
            "status": "ok" if records else "no_properties",
            "source": "PubChem PUG REST",
            "query": query,
            "resolved_cids": cids,
            "records": records,
            "ambiguous": len(cids) > 1,
            "identity_note": "Multiple PubChem compounds matched. Review CID, stereochemistry, salt form, and formulation before treating a result as the intended drug." if len(cids) > 1 else "Verify the returned CID and chemical form against the intended drug identity.",
            "properties_missing_for_cids": [cid for cid in cids if cid not in returned_cids],
            "property_source": "PubChem PUG REST; values are source-reported and not calculated by this service",
            # Observed HTTP status of the request that supplied these records.
            "http_status": property_meta.get("http_status"),
            "error": None,
        }
    except Exception as exc:
        if _not_found(exc):
            return {"status": "not_found", "source": "PubChem PUG REST", "query": query, "records": [], "ambiguous": False, "http_status": meta.get("http_status"), "error": None}
        return {**unavailable("PubChem PUG REST", exc), "query": query, "ambiguous": None}


async def compound_properties(cid: int) -> dict:
    """Fetch one CID's source-reported structure and descriptors."""
    meta: dict = {}
    try:
        cid = int(cid)
        if cid <= 0:
            raise ValueError("CID must be a positive integer")
        response = await get_json(f"{BASE}/compound/cid/{cid}/property/{PROPERTY_NAMES}/JSON", meta=meta)
        records = _property_rows(response)
        rows = [dict(row, source="PubChem PUG REST", source_url=f"{BASE}/compound/cid/{cid}/property/{PROPERTY_NAMES}/JSON") for row in records]
        return {"status": "ok" if rows else "not_found", "source": "PubChem PUG REST", "cid": cid, "records": rows, "property_source": "PubChem PUG REST; values are source-reported and not calculated by this service", "http_status": meta.get("http_status")}
    except Exception as exc:
        if _not_found(exc):
            return {"status": "not_found", "source": "PubChem PUG REST", "cid": cid, "records": [], "error": None}
        return unavailable("PubChem PUG REST", exc)
