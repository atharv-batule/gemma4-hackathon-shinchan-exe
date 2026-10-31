"""Per-request source checks and evidence provenance serialization.

This module records only metadata present in provider results or observable at
the application boundary. It does not infer upstream HTTP status or license.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import threading
from typing import Any


SOURCE_CHECK_STATES = {"CHECKED_FOUND", "CHECKED_EMPTY", "NOT_CHECKED", "SKIPPED"}
KNOWN_SOURCES = (
    "Open Targets", "ChEMBL", "PubChem", "PubMed", "DrugComb",
    "DrugBank", "Gemma", "RDKit",
)
_lock = threading.Lock()
_latest_checks: dict[str, dict[str, Any]] = {
    source: {
        "source": source,
        "state": "NOT_CHECKED",
        "reason": "No request to this source has been recorded in this process.",
        "record_count": None,
        "checked_at": None,
    }
    for source in KNOWN_SOURCES
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _records(envelope: Any) -> list[dict[str, Any]]:
    if isinstance(envelope, list):
        return [item for item in envelope if isinstance(item, dict)]
    if not isinstance(envelope, dict):
        return []
    values = envelope.get("records")
    if isinstance(values, list):
        return [item for item in values if isinstance(item, dict)]
    matches = envelope.get("matches")
    return [item for item in matches if isinstance(item, dict)] if isinstance(matches, list) else []


def _reason_for(envelope: Any, state: str, count: int) -> str:
    if isinstance(envelope, dict):
        for key in ("error", "reason", "detail"):
            value = envelope.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        errors = envelope.get("errors")
        if isinstance(errors, list) and errors:
            return "Partial provider result: " + "; ".join(str(item) for item in errors)
    if state == "CHECKED_FOUND":
        return f"Provider returned {count} record(s)."
    if state == "CHECKED_EMPTY":
        return "Provider request succeeded and returned no matching records."
    return "Provider request was not completed; no source evidence was checked."


def make_source_check(source: str, envelope: Any, *, skipped: bool = False) -> dict[str, Any]:
    """Map an adapter envelope to one of the four source-check states."""
    records = _records(envelope)
    status = envelope.get("status") if isinstance(envelope, dict) else None
    if records:
        count = len(records)
    elif isinstance(envelope, dict):
        count = envelope.get("record_count") or 0
    else:
        count = 0
    if skipped or status in {"not_run", "skipped"}:
        state = "SKIPPED"
    elif status == "ok" and isinstance(envelope, dict) and envelope.get("query") == "" and not records:
        state = "SKIPPED"
    elif status in {"ok", "available", "success", "evidence_found"} or (status == "partial" and count > 0):
        state = "CHECKED_FOUND" if count else "CHECKED_EMPTY"
    elif status in {"not_found", "no_records", "no_properties", "empty"}:
        # Explicit no-match/empty responses mean the provider was contacted and
        # returned no record in the requested collection.
        state = "CHECKED_EMPTY"
    elif status == "ambiguous" and count:
        state = "CHECKED_FOUND"
    else:
        state = "NOT_CHECKED"
    detail = _reason_for(envelope, state, count)
    check = {
        "source": source,
        "state": state,
        "reason": detail,
        "record_count": count if state in {"CHECKED_FOUND", "CHECKED_EMPTY"} else None,
        "checked_at": utc_now(),
    }
    with _lock:
        _latest_checks[source] = dict(check)
    return check


def source_checks_snapshot() -> dict[str, dict[str, Any]]:
    """Return a copy of last process-local provider checks for /health."""
    with _lock:
        return {key: dict(value) for key, value in _latest_checks.items()}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _source_hint(key: str, inherited: str | None) -> str | None:
    aliases = {
        "disease_gene": "Open Targets",
        "drug_target": "ChEMBL",
        "publications": "PubMed",
        "PubChem": "PubChem",
        "ChEMBL": "ChEMBL",
        "Open Targets": "Open Targets",
        "PubMed": "PubMed",
        "DrugComb": "DrugComb",
        "DrugBank": "DrugBank",
        "Gemma": "Gemma",
        "RDKit": "RDKit",
    }
    return aliases.get(key, inherited)


def _source_records(value: Any, source_hint: str | None = None, inherited_metadata: dict[str, Any] | None = None):
    """Yield record-like dictionaries that carry an explicit source label."""
    if isinstance(value, dict):
        metadata = dict(inherited_metadata or {})
        for metadata_key in ("retrieved_at", "http_status", "license"):
            if value.get(metadata_key) is not None:
                metadata[metadata_key] = value[metadata_key]
        is_record = any(
            k in value for k in (
                "source_id", "id", "pmid", "drug_id", "target_id", "CID",
                "molecule_chembl_id", "target_chembl_id", "activity_id",
                "disease_id", "block_id", "blockid",
            )
        )
        source = value.get("source") if isinstance(value.get("source"), str) else source_hint
        if is_record and source:
            item = dict(value)
            item.setdefault("source", source)
            if not value.get("source"):
                item.setdefault("source_record", dict(value))
            for metadata_key, metadata_value in metadata.items():
                item.setdefault(metadata_key, metadata_value)
            yield item
        for key, child in value.items():
            if key in {"source_record", "raw_json"}:
                continue
            if key == "sources" and isinstance(child, dict):
                for provider, envelope in child.items():
                    yield from _source_records(envelope, _source_hint(provider, source), metadata)
            else:
                yield from _source_records(child, source, metadata)
    elif isinstance(value, list):
        for child in value:
            yield from _source_records(child, source_hint, inherited_metadata)


def build_evidence_ledger(value: Any) -> list[dict[str, Any]]:
    """Build unique traceable ledger items from returned source records.

    ``raw_json`` is populated only when an adapter explicitly retained its raw
    source row. ``normalized_record`` always preserves what this layer received.
    Upstream HTTP status and license stay null unless explicitly supplied.
    """
    ledger: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for record in _source_records(value):
        normalized = dict(record)
        source = str(record.get("source"))
        raw_source_record = record.get("source_record") if isinstance(record.get("source_record"), dict) else None
        raw_allowed = record.get("raw_display_permitted") is True
        # Do not expose raw upstream content without explicit display permission.
        raw = raw_source_record if raw_allowed else None
        normalized.pop("source_record", None)
        hash_input = raw_source_record if raw_source_record is not None else normalized
        digest = hashlib.sha256(_canonical_json(hash_input).encode("utf-8")).hexdigest()
        source_id_value = (record.get("source_id") or record.get("id") or record.get("pmid")
                           or record.get("drug_id") or record.get("target_id") or record.get("CID")
                           or record.get("molecule_chembl_id") or record.get("target_chembl_id")
                           or record.get("activity_id") or record.get("disease_id")
                           or record.get("block_id") or record.get("blockid"))
        source_id = str(source_id_value) if source_id_value is not None else None
        base_id = f"{source}:{source_id}" if source_id else f"{source}:sha256:{digest}"
        if base_id in seen and seen[base_id] == digest:
            continue
        record_id = base_id if base_id not in seen else f"{base_id}@{digest[:12]}"
        if seen.get(record_id) == digest:
            continue
        seen[record_id] = digest
        ledger.append({
            "record_id": record_id,
            "source": source,
            "source_id": source_id,
            "url": record.get("url") or record.get("source_url"),
            "retrieved_at": record.get("retrieved_at") or record.get("_retrieved_at") or utc_now(),
            "http_status": record.get("http_status"),
            "content_hash": f"sha256:{digest}",
            "license": record.get("license"),
            "raw_display_permitted": raw_allowed,
            "raw_data_status": "permitted" if raw_allowed else "not_displayed_permission_unconfirmed",
            "raw_json": raw,
            "normalized_record": normalized,
        })
    return ledger


def attach_provenance(result: dict[str, Any], source_envelopes: dict[str, tuple[str, Any]], *, skipped_sources: set[str] | None = None) -> dict[str, Any]:
    """Attach ledger/checks to a response and update /health's latest checks."""
    checks: dict[str, dict[str, Any]] = {}
    skipped_sources = skipped_sources or set()
    for source, (label, envelope) in source_envelopes.items():
        checks[source] = make_source_check(label, envelope, skipped=source in skipped_sources)
    result["source_checks"] = checks
    result["evidence_ledger"] = build_evidence_ledger(result)
    return result

