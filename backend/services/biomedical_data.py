"""Small HTTP helpers shared by public biomedical data adapters.

Failures are represented as unavailable sources; adapters never substitute guessed data.
"""
from __future__ import annotations
import httpx

TIMEOUT = 12.0
HEADERS = {"User-Agent": "DrugDiscoverAI/0.1 (research prototype)"}

async def get_json(url: str, params: dict | None = None, *, meta: dict | None = None) -> dict | list:
    """Fetch JSON and optionally record the observed HTTP status.

    ``meta`` is filled only when the HTTP layer actually returned a status, so
    callers can keep provenance metadata unknown when no request completed.
    """
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        response = await client.get(url, params=params)
        if meta is not None:
            meta["http_status"] = response.status_code
        response.raise_for_status()
        return response.json()

def unavailable(source: str, error: Exception) -> dict:
    return {"status": "unavailable", "source": source, "records": [], "error": str(error)}
