"""Per-request source checks and evidence provenance serialization.

This module records only metadata present in provider results or observable at
the application boundary. It does not infer upstream HTTP status or license.

Built ledger records are retained in a bounded process-local store so the API
can retrieve one exact record by ``record_id`` after the originating response
has been returned. The store is not a database: it is empty after a restart and
never substitutes records from another response.
"""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import copy
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

# Bound the record store so long-running processes do not grow without limit.
# Oldest records are dropped first; a missing record is reported as not found.
_MAX_STORED_RECORDS = 5000
_stored_records: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_METADATA_KEYS = (
    "retrieved_at", "http_status", "license", "attribution",
    "transformations", "experiment_id", "cached",
)


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


def _transformations(value: Any) -> list[str]:
    """Normalize declared transformations to ordered, human-readable strings.

    Only transformations explicitly declared by an adapter or engine are
    reported. Nothing is inferred from data differences.
    """
    items: list[str] = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return items
    for item in value:
        text: str | None = None
        if isinstance(item, str) and item.strip():
            text = item.strip()
        elif isinstance(item, dict):
            label = item.get("type") or item.get("operation") or item.get("kind")
            detail = item.get("detail") or item.get("description")
            if label and detail:
                text = f"{label}: {detail}"
            elif label:
                text = str(label).strip()
            elif detail:
                text = str(detail).strip()
        if text and text not in items:
            items.append(text)
    return items


def _source_records(value: Any, source_hint: str | None = None, inherited_metadata: dict[str, Any] | None = None):
    """Yield record-like dictionaries that carry an explicit source label."""
    if isinstance(value, dict):
        metadata = dict(inherited_metadata or {})
        for metadata_key in _METADATA_KEYS:
            if metadata_key == "transformations":
                continue
            if value.get(metadata_key) is not None:
                metadata[metadata_key] = value[metadata_key]
        own_transformations = _transformations(value.get("transformations"))
        if own_transformations:
            metadata["transformations"] = (
                _transformations(metadata.get("transformations")) + own_transformations
            )
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
                if metadata_key == "transformations":
                    item["transformations"] = list(metadata_value)
                else:
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


def _http_status(value: Any) -> int | None:
    # Booleans are ints in Python; reject them and out-of-range values instead
    # of treating arbitrary data as an HTTP status.
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 100 <= value <= 599 else None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _metadata_status(*, http_status: int | None, license_value: str | None,
                     attribution: str | None, retrieved_at_provided: bool) -> dict[str, str]:
    return {
        "http_status": "PROVIDED" if http_status is not None else "UNKNOWN",
        "license": "PROVIDED" if license_value is not None else "NOT_PROVIDED",
        "attribution": "PROVIDED" if attribution is not None else "NOT_PROVIDED",
        "retrieved_at": "PROVIDED" if retrieved_at_provided else "UNKNOWN",
    }


def build_evidence_ledger(value: Any) -> list[dict[str, Any]]:
    """Build unique traceable ledger items from returned source records.

    ``raw_json`` is populated only when an adapter explicitly retained its raw
    source row and permitted display. ``normalized_record`` always preserves
    what this layer received. Upstream HTTP status and license stay null unless
    explicitly supplied, and the corresponding ``metadata_status`` says
    UNKNOWN/NOT_PROVIDED rather than implying a value.

    Built records are also retained in the bounded process-local store used by
    the provenance retrieval endpoints.
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
        transformations = _transformations(record.get("transformations"))
        if source_id_value is not None and not isinstance(source_id_value, str):
            note = (f"identifier_canonicalisation: source_id {type(source_id_value).__name__} "
                    f"coerced to string '{source_id}'")
            if note not in transformations:
                transformations.append(note)
        base_id = f"{source}:{source_id}" if source_id else f"{source}:sha256:{digest}"
        if base_id in seen and seen[base_id] == digest:
            continue
        record_id = base_id if base_id not in seen else f"{base_id}@{digest[:12]}"
        if seen.get(record_id) == digest:
            continue
        seen[record_id] = digest
        retrieved_value = _text(record.get("retrieved_at") or record.get("_retrieved_at"))
        cached = record.get("cached") is True
        http_status = _http_status(record.get("http_status"))
        license_value = _text(record.get("license"))
        attribution = _text(record.get("attribution"))
        ledger.append({
            "record_id": record_id,
            "source": source,
            "source_id": source_id,
            "url": record.get("url") or record.get("source_url"),
            "retrieved_at": retrieved_value or utc_now(),
            "retrieved_at_status": "PROVIDED" if retrieved_value else "UNKNOWN",
            "retrieved_at_origin": "cached" if cached and retrieved_value else (
                "provider" if retrieved_value else "unknown"),
            "http_status": http_status,
            "content_hash": f"sha256:{digest}",
            "license": license_value,
            "attribution": attribution,
            "transformations": transformations,
            "experiment_id": _text(record.get("experiment_id")) if isinstance(record.get("experiment_id"), str) else record.get("experiment_id"),
            "metadata_status": _metadata_status(
                http_status=http_status,
                license_value=license_value,
                attribution=attribution,
                retrieved_at_provided=bool(retrieved_value),
            ),
            "raw_display_permitted": raw_allowed,
            "raw_data_status": "permitted" if raw_allowed else "not_displayed_permission_unconfirmed",
            "raw_json": raw,
            "normalized_record": normalized,
        })
    register_ledger_records(ledger)
    return ledger


# ---------------------------------------------------------------------------
# Process-local provenance record store and exact matching helpers
# ---------------------------------------------------------------------------

def register_ledger_records(records: list[dict[str, Any]]) -> None:
    """Retain built ledger records for later retrieval by exact record ID."""
    if not records:
        return
    with _lock:
        for record in records:
            record_id = record.get("record_id")
            if not isinstance(record_id, str) or not record_id:
                continue
            _stored_records[record_id] = copy.deepcopy(record)
            _stored_records.move_to_end(record_id)
        while len(_stored_records) > _MAX_STORED_RECORDS:
            _stored_records.popitem(last=False)


def get_provenance_record(record_id: str) -> dict[str, Any] | None:
    """Return one stored ledger record by exact ID, or None if unknown."""
    with _lock:
        value = _stored_records.get(record_id)
        return copy.deepcopy(value) if value is not None else None


def find_provenance_records(
    *,
    record_id: str | None = None,
    source: str | None = None,
    source_id: str | None = None,
    experiment_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return stored records matching every supplied exact filter.

    Source labels are compared case-insensitively; identifiers and experiment
    IDs are compared exactly. No fuzzy or fallback matching is performed.
    """
    with _lock:
        values = list(_stored_records.values())
    matches: list[dict[str, Any]] = []
    for item in values:
        if record_id is not None and item.get("record_id") != record_id:
            continue
        if source is not None and str(item.get("source", "")).strip().casefold() != source.strip().casefold():
            continue
        if source_id is not None and item.get("source_id") != source_id:
            continue
        if experiment_id is not None and item.get("experiment_id") != experiment_id:
            continue
        matches.append(copy.deepcopy(item))
    return matches


def annotate_heatmap_provenance(heatmap: dict[str, Any], ledger: list[dict[str, Any]]) -> dict[str, Any]:
    """Attach an exact ledger record reference to each heatmap observation.

    Matching requires an exact source label plus source ID pair that resolves to
    exactly one ledger record. Missing identifiers, unknown pairs, and ambiguous
    pairs are marked UNAVAILABLE/AMBIGUOUS and carry no record ID. The heatmap
    is never replaced with the whole ledger.
    """
    index: dict[tuple[str, str], list[str]] = {}
    for item in ledger:
        source_value = item.get("source")
        source_id_value = item.get("source_id")
        record_id = item.get("record_id")
        if not isinstance(source_value, str) or source_id_value is None or not isinstance(record_id, str):
            continue
        key = (source_value.strip().casefold(), str(source_id_value))
        index.setdefault(key, []).append(record_id)

    for cell in heatmap.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        for score in cell.get("scores") or []:
            if not isinstance(score, dict):
                continue
            source_value = score.get("source")
            source_id_value = score.get("source_id")
            score["record_id"] = None
            if not isinstance(source_value, str) or not source_value.strip():
                score["provenance_state"] = "UNAVAILABLE"
                score["provenance_reason"] = "The observation has no source label; no record can be matched exactly."
                continue
            if source_id_value is None or not str(source_id_value).strip():
                score["provenance_state"] = "UNAVAILABLE"
                score["provenance_reason"] = "The observation has no source identifier; no ledger record was selected."
                continue
            matches = index.get((source_value.strip().casefold(), str(source_id_value)), [])
            if len(matches) == 1:
                score["record_id"] = matches[0]
                score["provenance_state"] = "AVAILABLE"
                score["provenance_reason"] = "Matched to exactly one ledger record by source and source ID."
            elif len(matches) > 1:
                score["provenance_state"] = "AMBIGUOUS"
                score["provenance_reason"] = "Multiple ledger records share this source and source ID; no record was selected automatically."
            else:
                score["provenance_state"] = "UNAVAILABLE"
                score["provenance_reason"] = "No ledger record matches this source and source ID."
    return heatmap


def attach_provenance(result: dict[str, Any], source_envelopes: dict[str, tuple[str, Any]], *, skipped_sources: set[str] | None = None) -> dict[str, Any]:
    """Attach ledger/checks to a response and update /health's latest checks."""
    checks: dict[str, dict[str, Any]] = {}
    skipped_sources = skipped_sources or set()
    for source, (label, envelope) in source_envelopes.items():
        checks[source] = make_source_check(label, envelope, skipped=source in skipped_sources)
    result["source_checks"] = checks
    result["evidence_ledger"] = build_evidence_ledger(result)
    return result
