"""Gemma adapter for OpenAI-compatible local or remote inference servers.

Configure GEMMA_BASE_URL (base URL, optionally ending in /v1), GEMMA_MODEL,
and optional GEMMA_API_KEY. Nothing is sent unless the provider is configured.
"""
from __future__ import annotations
import json
import os
import re
from typing import Any
import httpx
from pydantic import ValidationError
from .prompts import SYSTEM_PROMPT, user_prompt
from .response_schemas import Explanation
from .citation_verifier import verify_claims


def _citation_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k.lower() in {"citation", "citation_id", "record_id", "source_id", "pmid", "doi", "url", "reference"} and isinstance(v, (str, int)):
                found.add(str(v))
            elif k.lower() in {"citations", "citation_ids", "references"} and isinstance(v, list):
                found.update(str(item) for item in v if isinstance(item, (str, int)))
            else:
                found |= _citation_ids(v)
    elif isinstance(value, list):
        for item in value: found |= _citation_ids(item)
    return found


def _contains_source_records(value: Any) -> bool:
    """Require at least one non-empty source-record collection before inference."""
    evidence_keys = {"evidence", "evidence_ledger", "records", "targets", "candidates", "publications",
                     "drug_target_records", "disease_associations", "combination_evidence",
                     "ddi_warnings", "toxicity_evidence"}
    if isinstance(value, dict):
        for key, child in value.items():
            if key.casefold() in evidence_keys and isinstance(child, list) and child:
                return True
            if _contains_source_records(child):
                return True
    elif isinstance(value, list):
        return any(_contains_source_records(item) for item in value)
    return False


def _find_evidence_ledger(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        candidate = value.get("evidence_ledger")
        if isinstance(candidate, list) and all(isinstance(row, dict) for row in candidate):
            return candidate
        for child in value.values():
            found = _find_evidence_ledger(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_evidence_ledger(child)
            if found:
                return found
    return []


def _decode(content: str) -> dict[str, Any]:
    content = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.S | re.I)
    if match: content = match.group(1)
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start: raise ValueError("Provider response did not contain a JSON object")
    value = json.loads(content[start:end + 1])
    if not isinstance(value, dict): raise ValueError("Provider response must be a JSON object")
    return value


def explain_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    base = {"status": "unavailable", "model": os.getenv("GEMMA_MODEL") or None, "data": None}
    base_url = os.getenv("GEMMA_BASE_URL", "").strip().rstrip("/")
    model = os.getenv("GEMMA_MODEL", "").strip()
    if not base_url or not model:
        return {**base, "reason": "Gemma provider is not configured. Set GEMMA_BASE_URL and GEMMA_MODEL; GEMMA_API_KEY is optional for local providers."}
    if not isinstance(evidence, dict) or not _contains_source_records(evidence):
        return {**base, "status": "insufficient_evidence", "reason": "No non-empty source evidence records were supplied; an explanation was not requested."}
    endpoint = base_url if base_url.endswith("/chat/completions") else base_url + ("" if base_url.endswith("/v1") else "/v1") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    key = os.getenv("GEMMA_API_KEY", "").strip()
    if key: headers["Authorization"] = "Bearer " + key
    body = {"model": model, "temperature": 0.1, "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt(evidence)}], "response_format": {"type": "json_object"}}
    try:
        with httpx.Client(timeout=90, headers=headers) as client:
            response = client.post(endpoint, json=body)
            response.raise_for_status()
            envelope = response.json()
        if not isinstance(envelope, dict):
            raise ValueError("Invalid completion envelope")
        content = envelope["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("Completion content must be text")
        parsed = _decode(content)
        result = Explanation.model_validate(parsed)
        permitted = _citation_ids(evidence)
        citations = list(dict.fromkeys(c for c in result.citations if c in permitted))
        rejected_count = len(result.citations) - len(citations)
        result.citations = citations
        ledger = _find_evidence_ledger(evidence)
        claim_verification = verify_claims(
            [claim.model_dump() for claim in result.claims], ledger
        )
        return {"status": "ok", "model": model, "data": result.model_dump(),
                "validation": {"schema_valid": True, "unsupported_citations_removed": rejected_count,
                               "citation_ids_checked_against_bundle": True,
                               "semantic_grounding": "requires human review",
                               "claim_verification": claim_verification},
                "reason": None}
    except (httpx.HTTPError, KeyError, IndexError, TypeError, AttributeError, ValueError, ValidationError) as exc:
        return {**base, "reason": f"Gemma request or response validation failed ({type(exc).__name__}). Supplied evidence remains unchanged."}
