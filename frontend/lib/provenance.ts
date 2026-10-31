/**
 * Exact provenance lookup for one heatmap observation.
 *
 * Only exact identifiers are sent to the provenance endpoint. When no
 * identifier is available the result is an explicit "unavailable" state; the
 * full evidence ledger is never used as a fallback.
 */

export type ProvenanceTarget = {
  recordId?: string | null;
  source?: string | null;
  sourceId?: string | null;
  metric?: string | null;
  cellLine?: string | null;
  score?: unknown;
  reportedInterpretation?: string | null;
  context?: Record<string, unknown> | null;
};

export type ProvenanceRecord = Record<string, any>;

export type ProvenanceResult =
  | { state: "loading" }
  | { state: "found"; record: ProvenanceRecord; message: string }
  | { state: "not_found" | "unavailable" | "error"; message: string };

type ResponseLike = { ok: boolean; status: number; json: () => Promise<any> };
export type FetchLike = (url: string) => Promise<ResponseLike>;

const DEFAULT_BASE_URL = "http://localhost:8000";
export const PROVENANCE_PATH = "/api/provenance/records";

function identifier(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text ? text : null;
}

/** Build the exact-match query string, or null when nothing can be matched. */
export function provenanceQuery(target: ProvenanceTarget): string | null {
  const recordId = identifier(target.recordId);
  if (recordId) return new URLSearchParams({ record_id: recordId }).toString();
  const source = identifier(target.source);
  const sourceId = identifier(target.sourceId);
  if (source && sourceId) return new URLSearchParams({ source, source_id: sourceId }).toString();
  return null;
}

function unavailableMessage(target: ProvenanceTarget): string {
  if (!identifier(target.source)) {
    return "Provenance unavailable: this observation has no source label, so no record could be matched exactly.";
  }
  return "Provenance unavailable: this observation has no source identifier or record ID, so no record was selected.";
}

/** State to show while a lookup is pending (or when no lookup is possible). */
export function initialProvenanceState(target: ProvenanceTarget): ProvenanceResult {
  if (provenanceQuery(target)) return { state: "loading" };
  return { state: "unavailable", message: unavailableMessage(target) };
}

/** Load exactly one stored provenance record; never substitutes a ledger. */
export async function loadProvenanceRecord(
  target: ProvenanceTarget,
  options: { baseUrl?: string; fetchImpl?: FetchLike } = {},
): Promise<ProvenanceResult> {
  const query = provenanceQuery(target);
  if (!query) return initialProvenanceState(target);
  const baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
  const fetchImpl = options.fetchImpl ?? (fetch as unknown as FetchLike);
  let response: ResponseLike;
  try {
    response = await fetchImpl(`${baseUrl}${PROVENANCE_PATH}?${query}`);
  } catch {
    return { state: "error", message: "Provenance lookup failed: the provenance endpoint could not be reached." };
  }
  if (response.status === 404) {
    return { state: "not_found", message: "Provenance unavailable: no stored record matches this observation." };
  }
  if (!response.ok) {
    return { state: "error", message: `Provenance lookup failed (HTTP ${response.status}).` };
  }
  let payload: any;
  try {
    payload = await response.json();
  } catch {
    return { state: "error", message: "Provenance lookup failed: the response was not valid JSON." };
  }
  const records = Array.isArray(payload?.records) ? payload.records : [];
  if (payload?.status === "found" && records.length === 1) {
    return { state: "found", record: records[0], message: "" };
  }
  if (payload?.status === "found" && records.length > 1) {
    return {
      state: "not_found",
      message: "Provenance unavailable: multiple stored records match these identifiers; no record was selected automatically.",
    };
  }
  const reason = typeof payload?.reason === "string" && payload.reason.trim() ? payload.reason.trim() : null;
  return {
    state: "not_found",
    message: `Provenance unavailable: ${reason || "no stored record matches this observation."}`,
  };
}
