"""Small HTTP helpers shared by public biomedical data adapters.

Failures are represented as unavailable sources; adapters never substitute guessed data.
"""
from __future__ import annotations
import httpx

TIMEOUT = 12.0
HEADERS = {"User-Agent": "DrugDiscoverAI/0.1 (research prototype)"}

async def get_json(url: str, params: dict | None = None) -> dict | list:
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()

def unavailable(source: str, error: Exception) -> dict:
    return {"status": "unavailable", "source": source, "records": [], "error": str(error)}
