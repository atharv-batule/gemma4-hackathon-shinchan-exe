"use client";

import React, { useMemo, useState } from "react";

export type ClaimCheck = {
  status: "matched" | "mismatch" | "missing" | string;
  field?: string;
  expected?: any;
  source_value?: any;
  checked?: any;
  reason?: string;
};

export type VerifiedClaim = {
  claim_index: number;
  claim_text: string;
  claim_tag: "sourced" | "inferred" | "unknown" | string;
  citation_source?: string | null;
  citation_record_id?: string | null;
  ledger_record_id?: string | null;
  status: "VERIFIED" | "ID_ONLY" | "MISMATCH" | "UNVERIFIABLE" | string;
  uncited_claim?: boolean;
  reason_code?: string;
  reason?: string;
  checks?: ClaimCheck[];
};

export type VerificationPayload = {
  status?: string;
  summary?: {
    VERIFIED?: number;
    ID_ONLY?: number;
    MISMATCH?: number;
    UNVERIFIABLE?: number;
    [key: string]: number | undefined;
  };
  results?: VerifiedClaim[];
  limitations?: string[];
  [key: string]: any;
};

interface CitationVerificationTableProps {
  verification: VerificationPayload | { data?: VerificationPayload; validation?: { claim_verification?: VerificationPayload } };
  title?: string;
  subtitle?: string;
  onOpenProvenance?: (recordId: string) => void;
  onReverify?: () => void;
  reverifyBusy?: boolean;
}

function displayValue(val: unknown): string {
  if (val === null || val === undefined || val === "") return "—";
  if (typeof val === "object") return JSON.stringify(val);
  return String(val);
}

function statusKind(status: string): string {
  switch (status) {
    case "VERIFIED":
      return "good";
    case "ID_ONLY":
      return "warning";
    case "MISMATCH":
      return "danger";
    case "UNVERIFIABLE":
    default:
      return "muted";
  }
}

export function CitationVerificationTable({
  verification,
  title = "Deterministic Claim & Citation Verification",
  subtitle = "Checks citation source and record ID against the evidence ledger, and verifies declared structured fields.",
  onOpenProvenance,
  onReverify,
  reverifyBusy = false,
}: CitationVerificationTableProps) {
  const [filter, setFilter] = useState<string>("ALL");

  // Normalize verification payload shape from either direct result, .data, or .validation.claim_verification
  const normalized: VerificationPayload = useMemo(() => {
    if (!verification) return {};
    if ("validation" in verification && verification.validation?.claim_verification) {
      return verification.validation.claim_verification;
    }
    if ("data" in verification && verification.data && "results" in verification.data) {
      return verification.data;
    }
    return verification as VerificationPayload;
  }, [verification]);

  const results: VerifiedClaim[] = useMemo(() => {
    return Array.isArray(normalized.results) ? normalized.results : [];
  }, [normalized.results]);

  const summary = useMemo(() => {
    if (normalized.summary) {
      return {
        VERIFIED: normalized.summary.VERIFIED ?? 0,
        ID_ONLY: normalized.summary.ID_ONLY ?? 0,
        MISMATCH: normalized.summary.MISMATCH ?? 0,
        UNVERIFIABLE: normalized.summary.UNVERIFIABLE ?? 0,
      };
    }
    return {
      VERIFIED: results.filter(r => r.status === "VERIFIED").length,
      ID_ONLY: results.filter(r => r.status === "ID_ONLY").length,
      MISMATCH: results.filter(r => r.status === "MISMATCH").length,
      UNVERIFIABLE: results.filter(r => r.status === "UNVERIFIABLE").length,
    };
  }, [normalized.summary, results]);

  const filteredResults = useMemo(() => {
    if (filter === "ALL") return results;
    return results.filter(row => row.status === filter);
  }, [results, filter]);

  const limitations = normalized.limitations || [
    "Deterministic structured-field comparisons do not establish scientific entailment of free-text claims.",
    "No unit conversion is performed; units and experimental context are compared as reported.",
  ];

  if (!results.length) {
    return (
      <div className="verifier-card">
        <div className="verifier-card-header">
          <div>
            <h3>{title}</h3>
            <p>{subtitle}</p>
          </div>
          {onReverify && (
            <button
              type="button"
              className="secondary-btn"
              disabled={reverifyBusy}
              onClick={onReverify}
            >
              {reverifyBusy ? "Verifying claims…" : "Run verifier"}
            </button>
          )}
        </div>
        <p className="quiet-empty">No claim verification results to display.</p>
      </div>
    );
  }

  return (
    <div className="verifier-card" aria-label="Citation verification results">
      <div className="verifier-card-header">
        <div>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        {onReverify && (
          <button
            type="button"
            className="secondary-btn"
            disabled={reverifyBusy}
            onClick={onReverify}
            title="Re-run deterministic verification of these claims against the current evidence ledger"
          >
            {reverifyBusy ? "Verifying claims…" : "Re-verify claims"}
          </button>
        )}
      </div>

      {/* Mandatory scientific disclaimer regarding free-text entailment */}
      <div className="entailment-notice" role="note">
        <div className="shield" aria-hidden="true">!</div>
        <div>
          <b>Deterministic Structured Verification (No Free-Text Entailment)</b>
          <p>
            Free-text scientific entailment is <strong>intentionally not verified</strong>; only declared structured fields
            (identities, metrics, cell lines, units, experimental context, and reported numeric values) are compared
            deterministically against the run’s evidence ledger. Uncited claims or unverified prose must not be assumed factual.
          </p>
        </div>
      </div>

      {/* Summary Stat Cards */}
      <div className="verification-summary-strip" role="region" aria-label="Verification status summary">
        <div className="summary-stat-card">
          <span>VERIFIED</span>
          <strong style={{ color: "#236c56" }}>{summary.VERIFIED}</strong>
          <small>Source & all structured details match ledger</small>
        </div>
        <div className="summary-stat-card">
          <span>ID_ONLY</span>
          <strong style={{ color: "#9d783b" }}>{summary.ID_ONLY}</strong>
          <small>Source ID exists; structured details absent</small>
        </div>
        <div className="summary-stat-card">
          <span>MISMATCH</span>
          <strong style={{ color: "#b23b23" }}>{summary.MISMATCH}</strong>
          <small>Declared structured values conflict with record</small>
        </div>
        <div className="summary-stat-card">
          <span>UNVERIFIABLE</span>
          <strong style={{ color: "#72817d" }}>{summary.UNVERIFIABLE}</strong>
          <small>Absent from ledger, wrong source, or uncited</small>
        </div>
      </div>

      {/* Interactive Filter Bar */}
      <div className="verification-filter-bar" role="tablist" aria-label="Filter claims by status">
        <span className="filter-label">Filter:</span>
        <button
          type="button"
          className={`filter-tab ${filter === "ALL" ? "active" : ""}`}
          onClick={() => setFilter("ALL")}
          role="tab"
          aria-selected={filter === "ALL"}
        >
          All ({results.length})
        </button>
        <button
          type="button"
          className={`filter-tab ${filter === "VERIFIED" ? "active" : ""}`}
          onClick={() => setFilter("VERIFIED")}
          role="tab"
          aria-selected={filter === "VERIFIED"}
        >
          VERIFIED ({summary.VERIFIED})
        </button>
        <button
          type="button"
          className={`filter-tab ${filter === "ID_ONLY" ? "active" : ""}`}
          onClick={() => setFilter("ID_ONLY")}
          role="tab"
          aria-selected={filter === "ID_ONLY"}
        >
          ID_ONLY ({summary.ID_ONLY})
        </button>
        <button
          type="button"
          className={`filter-tab ${filter === "MISMATCH" ? "active" : ""}`}
          onClick={() => setFilter("MISMATCH")}
          role="tab"
          aria-selected={filter === "MISMATCH"}
        >
          MISMATCH ({summary.MISMATCH})
        </button>
        <button
          type="button"
          className={`filter-tab ${filter === "UNVERIFIABLE" ? "active" : ""}`}
          onClick={() => setFilter("UNVERIFIABLE")}
          role="tab"
          aria-selected={filter === "UNVERIFIABLE"}
        >
          UNVERIFIABLE ({summary.UNVERIFIABLE})
        </button>
      </div>

      {/* Detailed Status Table */}
      <div className="verification-table-wrapper">
        <table className="verification-table">
          <thead>
            <tr>
              <th scope="col" style={{ width: "32px" }}>#</th>
              <th scope="col" style={{ width: "110px" }}>Status</th>
              <th scope="col" style={{ width: "75px" }}>Tag</th>
              <th scope="col" style={{ minWidth: "220px" }}>Claim Statement</th>
              <th scope="col" style={{ minWidth: "140px" }}>Citation & Ledger</th>
              <th scope="col" style={{ minWidth: "180px" }}>Structured Field Checks</th>
              <th scope="col" style={{ minWidth: "180px" }}>Diagnostic Reason</th>
            </tr>
          </thead>
          <tbody>
            {filteredResults.map((claim, index) => {
              const displayIndex = claim.claim_index != null ? claim.claim_index + 1 : index + 1;
              const checks = Array.isArray(claim.checks) ? claim.checks : [];
              return (
                <tr key={`${claim.claim_index ?? index}-${claim.status}`}>
                  {/* # Index */}
                  <td>
                    <span style={{ font: "500 9px 'DM Mono', monospace", color: "#8b9995" }}>
                      {String(displayIndex).padStart(2, "0")}
                    </span>
                  </td>

                  {/* Status Badge */}
                  <td>
                    <span className={`badge ${statusKind(claim.status)}`}>
                      {claim.status}
                    </span>
                  </td>

                  {/* Claim Tag */}
                  <td>
                    <span className="badge muted">
                      {claim.claim_tag || "unknown"}
                    </span>
                  </td>

                  {/* Claim Text */}
                  <td>
                    <div style={{ lineHeight: 1.5, color: "#243b35" }}>
                      {claim.claim_text || "No claim text provided"}
                    </div>
                    {claim.uncited_claim && (
                      <span className="uncited-flag">⚠ Uncited factual claim</span>
                    )}
                  </td>

                  {/* Citation & Ledger Link */}
                  <td>
                    <div>
                      <strong>{claim.citation_source || "Uncited"}</strong>
                      {claim.citation_record_id ? (
                        <div style={{ font: "500 9px 'DM Mono', monospace", color: "#506963" }}>
                          {claim.citation_record_id}
                        </div>
                      ) : null}
                    </div>

                    {claim.ledger_record_id ? (
                      <button
                        type="button"
                        className="ledger-btn"
                        onClick={() => onOpenProvenance?.(claim.ledger_record_id!)}
                        title={`View ${claim.ledger_record_id} in provenance ledger`}
                      >
                        Ledger record ↗
                      </button>
                    ) : claim.citation_record_id ? (
                      <span className="citation-missing-alert">Absent from ledger</span>
                    ) : (
                      <span className="no-checks-text">No source ID</span>
                    )}
                  </td>

                  {/* Structured Field Checks */}
                  <td>
                    {checks.length > 0 ? (
                      <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                        {checks.map((chk, chkIdx) => {
                          if (chk.status === "matched") {
                            return (
                              <span className="check-chip good" key={chkIdx}>
                                ✓ <b>{chk.field}</b>: matched
                              </span>
                            );
                          }
                          if (chk.status === "mismatch") {
                            return (
                              <div className="check-chip danger" key={chkIdx}>
                                ✗ <b>{chk.field}</b>: expected{" "}
                                <span className="val-exp">{displayValue(chk.expected)}</span> ≠ source{" "}
                                <span className="val-src">{displayValue(chk.source_value)}</span>
                              </div>
                            );
                          }
                          return (
                            <span className="check-chip warning" key={chkIdx}>
                              ? <b>{chk.field}</b>: {chk.reason || "absent from record"}
                            </span>
                          );
                        })}
                      </div>
                    ) : (
                      <span className="no-checks-text">
                        {claim.claim_tag === "inferred" || claim.claim_tag === "unknown"
                          ? "Untracked (hypothesis)"
                          : "No structured details checked"}
                      </span>
                    )}
                  </td>

                  {/* Reason Code and Description */}
                  <td>
                    {claim.reason_code && (
                      <code className="reason-code-badge">{claim.reason_code}</code>
                    )}
                    <div className="reason-subcopy">{claim.reason}</div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Explicit Limitations list */}
      {limitations.length > 0 && (
        <div className="limitations-box">
          <b>Deterministic Verification Constraints & Limitations:</b>
          <ul>
            {limitations.map((lim, idx) => (
              <li key={idx}>{lim}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

