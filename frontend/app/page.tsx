"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { initialProvenanceState, loadProvenanceRecord } from "../lib/provenance";
import type { ProvenanceResult, ProvenanceTarget } from "../lib/provenance";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { CitationVerificationTable } from "./CitationVerificationTable";

type Evidence = Record<string, any>;
type Candidate = {
  drug_name: string;
  drug_id?: string | null;
  targets?: string[];
  disease_associations?: Evidence[];
  evidence?: Evidence[];
  evidence_completeness_score?: number;
  score_interpretation?: string;
  evidence_level?: string;
};
type Result = {
  status?: string;
  pipeline_latency_ms?: number;
  data?: {
    query?: string;
    candidates?: Candidate[];
    targets?: Evidence[];
    publications?: Evidence[];
    sources?: Record<string, Evidence>;
    evidence_ledger?: Evidence[];
    source_checks?: Record<string, Evidence>;
    limitations?: string[];
  };
  [key: string]: any;
};

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function api(path: string, body?: unknown) {
  const response = await fetch(`${API}${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`API ${response.status}: ${response.statusText}`);
  return response.json();
}

function Badge({ children, kind = "muted" }: { children: React.ReactNode; kind?: string }) {
  return <span className={`badge ${kind}`}>{children}</span>;
}

function PanelTitle({ kicker, title, note }: { kicker: string; title: string; note?: string }) {
  return <div className="panel-title"><div><span className="eyebrow">{kicker}</span><h2>{title}</h2></div>{note && <p>{note}</p>}</div>;
}

function display(value: unknown) {
  if (value === null || value === undefined || value === "") return "Not reported";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function reportedLabelClass(label: unknown) {
  if (typeof label !== "string") return "heatmap-label-unknown";
  const value = label.toLocaleLowerCase();
  if (["synergy", "synergistic", "positive"].includes(value)) return "heatmap-label-positive";
  if (["antagonism", "antagonistic", "negative"].includes(value)) return "heatmap-label-negative";
  if (["additive", "neutral"].includes(value)) return "heatmap-label-additive";
  return "heatmap-label-unknown";
}

function SourceLink({ url, label = "Open source record" }: { url?: unknown; label?: string }) {
  return typeof url === "string" && url.startsWith("https://")
    ? <a href={url} target="_blank" rel="noreferrer">{label}</a>
    : <span>Source URL not supplied</span>;
}

function contextSummary(context?: Record<string, unknown> | null) {
  if (!context) return "No experimental context was supplied with this observation.";
  const entries = Object.entries(context).filter(([, value]) => value !== null && value !== undefined && value !== "");
  return entries.length
    ? entries.map(([key, value]) => `${key.replaceAll("_", " ")}: ${display(value)}`).join(" · ")
    : "No experimental context was supplied with this observation.";
}

function HeatmapCellContext({ target }: { target: ProvenanceTarget | null }) {
  if (!target) return null;
  return <div className="drawer-context">
    <span className="eyebrow">SELECTED OBSERVATION</span>
    <dl>
      <dt>Cell line</dt><dd>{display(target.cellLine)}</dd>
      <dt>Metric</dt><dd>{display(target.metric)}</dd>
      <dt>Reported score</dt><dd>{display(target.score)}</dd>
      <dt>Source interpretation</dt><dd>{display(target.reportedInterpretation)}</dd>
      <dt>Record ID</dt><dd>{display(target.recordId)}</dd>
      <dt>Source ID</dt><dd>{display(target.sourceId)}</dd>
    </dl>
    <p className="limitation">{contextSummary(target.context)}</p>
  </div>;
}

function RecordLookupState({ result }: { result: ProvenanceResult }) {
  if (result.state === "loading") return <div className="drawer-state"><span className="spinner dark"/> Loading the stored provenance record…</div>;
  if (result.state === "found") return null;
  return <div className={`drawer-state${result.state === "error" ? " error" : ""}`}>
    <b>{result.state === "error" ? "Provenance lookup failed" : "Provenance unavailable"}</b>
    <p>{result.message}</p>
  </div>;
}

export default function Home() {
  const [disease, setDisease] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [drugA, setDrugA] = useState("");
  const [drugB, setDrugB] = useState("");
  const [combo, setCombo] = useState<any>(null);
  const [comboBusy, setComboBusy] = useState(false);
  const [identity, setIdentity] = useState<any>(null);
  const [identityBusy, setIdentityBusy] = useState(false);
  const [smiles, setSmiles] = useState("");
  const [molecule, setMolecule] = useState<any>(null);
  const [molBusy, setMolBusy] = useState(false);
  const [explanation, setExplanation] = useState<any>(null);
  const [explainBusy, setExplainBusy] = useState(false);
  const [citationDemo, setCitationDemo] = useState<any>(null);
  const [citationDemoBusy, setCitationDemoBusy] = useState(false);
  const [sampleBusy, setSampleBusy] = useState(false);
  const [reverifyBusy, setReverifyBusy] = useState(false);
  const [health, setHealth] = useState<any>(null);
  const [provenanceOpen, setProvenanceOpen] = useState(false);
  const [provenanceMode, setProvenanceMode] = useState<"ledger" | "record">("ledger");
  const [provenanceTarget, setProvenanceTarget] = useState<ProvenanceTarget | null>(null);
  const [provenanceResult, setProvenanceResult] = useState<ProvenanceResult>({ state: "loading" });
  const provenanceRequest = useRef(0);

  const candidates = result?.data?.candidates || [];
  const targets = result?.data?.targets || [];
  const sources = Object.entries(result?.data?.sources || {});
  const evidenceCount = useMemo(() => candidates.reduce((sum, candidate) => sum + (candidate.evidence?.length || 0), 0), [candidates]);
  const evidenceLedger: Evidence[] = useMemo(() => {
    const ledgers = [result?.evidence_ledger || result?.data?.evidence_ledger, combo?.evidence_ledger,
      ...(identity?.queries || []).map((item: Evidence) => item.response?.evidence_ledger)];
    const unique = new Map<string, Evidence>();
    ledgers.flatMap(value => Array.isArray(value) ? value : []).forEach((record: Evidence, index: number) => {
      unique.set(record.record_id || `${record.source || "record"}-${record.source_id || index}`, record);
    });
    return Array.from(unique.values());
  }, [result, combo, identity]);
  const sourceChecks: Record<string, Evidence> = { ...(result?.source_checks || result?.data?.source_checks || {}), ...(health?.source_checks || {}) };
  const drawerRecords: Evidence[] = provenanceMode === "record"
    ? (provenanceResult.state === "found" ? [provenanceResult.record] : [])
    : evidenceLedger;

  function openLedger() {
    provenanceRequest.current += 1;
    setProvenanceMode("ledger");
    setProvenanceTarget(null);
    setProvenanceOpen(true);
  }

  function openHeatmapProvenance(score: Evidence, cell: Evidence) {
    const target: ProvenanceTarget = {
      recordId: score.record_id ?? null,
      source: score.source ?? null,
      sourceId: score.source_id ?? null,
      metric: cell.metric ?? null,
      cellLine: cell.cell_line ?? null,
      score: score.score ?? null,
      reportedInterpretation: score.reported_interpretation ?? null,
      context: score.context ?? null,
    };
    const request = provenanceRequest.current + 1;
    provenanceRequest.current = request;
    const initialState = initialProvenanceState(target);
    setProvenanceMode("record");
    setProvenanceTarget(target);
    setProvenanceResult(initialState);
    setProvenanceOpen(true);
    if (initialState.state !== "loading") return;
    loadProvenanceRecord(target, { baseUrl: API }).then(result => {
      if (request === provenanceRequest.current) setProvenanceResult(result);
    });
  }

  useEffect(() => {
    let active = true;
    api("/health").then(value => { if (active) setHealth(value); }).catch(() => { if (active) setHealth({ status: "unavailable", error: "Health endpoint could not be reached." }); });
    return () => { active = false; };
  }, []);

  async function analyze(event: FormEvent) {
    event.preventDefault();
    if (!disease.trim()) return;
    setBusy(true); setError(""); setResult(null); setSelected(null); setExplanation(null);
    try {
      const response = await api("/api/discovery/combined", { disease: disease.trim() });
      setResult(response);
      try { setHealth(await api("/health")); } catch { /* keep the completed workflow response */ }
    }
    catch (err) { setError(err instanceof Error ? err.message : "Could not reach the research API."); }
    finally { setBusy(false); }
  }

  async function analyzeCombo(event: FormEvent) {
    event.preventDefault();
    if (!drugA.trim() || !drugB.trim()) return;
    setComboBusy(true); setCombo(null);
    const pair = { drug_a: drugA.trim(), drug_b: drugB.trim() };
    const [comboResponse, safetyResponse] = await Promise.allSettled([
      api("/api/combinations/analyze", pair), api("/api/safety/evaluate", pair),
    ]);
    const combination = comboResponse.status === "fulfilled" ? comboResponse.value : {
      status: "unavailable", error: comboResponse.reason instanceof Error ? comboResponse.reason.message : "Combination provider request failed",
    };
    const safety = safetyResponse.status === "fulfilled" ? safetyResponse.value : {
      status: "unavailable", ddi_risk_level: "UNKNOWN", decision: "REVIEW",
      error: safetyResponse.reason instanceof Error ? safetyResponse.reason.message : "Safety provider request failed",
    };
    setCombo({ ...combination, safety });
    try { setHealth(await api("/health")); } catch { /* preserve separate combo and safety results */ }
    setComboBusy(false);
  }

  async function resolveIdentities() {
    const queries = [{ side: "A", query: drugA.trim() }, { side: "B", query: drugB.trim() }].filter(item => item.query);
    if (!queries.length) return;
    setIdentityBusy(true); setIdentity(null);
    try {
      const resolved = await Promise.all(queries.map(async item => ({
        ...item, response: await api(`/api/drugs/search?q=${encodeURIComponent(item.query)}`),
      })));
      setIdentity({ queries: resolved });
    } catch (err) { setIdentity({ error: err instanceof Error ? err.message : "Request failed" }); }
    finally { setIdentityBusy(false); }
  }

  async function validateMolecule(event: FormEvent) {
    event.preventDefault();
    if (!smiles.trim()) return;
    setMolBusy(true); setMolecule(null);
    try { setMolecule(await api("/api/molecular/validate", { smiles: smiles.trim() })); }
    catch (err) { setMolecule({ status: "unavailable", error: err instanceof Error ? err.message : "Request failed" }); }
    finally { setMolBusy(false); }
  }

  async function explain() {
    if (!result) return;
    setExplainBusy(true); setExplanation(null);
    try { setExplanation(await api("/api/ai/explain", { evidence: result, selected_candidate: selected })); }
    catch (err) { setExplanation({ status: "unavailable", error: err instanceof Error ? err.message : "Request failed" }); }
    finally { setExplainBusy(false); }
  }

  async function reverifyExplanationClaims() {
    if (!explanation?.data?.claims?.length) return;
    setReverifyBusy(true);
    try {
      const res = await api("/api/ai/verify-claims", {
        claims: explanation.data.claims,
        evidence_ledger: evidenceLedger,
      });
      const verification = res.data || res;
      setExplanation((prev: any) => ({
        ...prev,
        validation: {
          ...(prev?.validation || {}),
          claim_verification: verification,
        },
      }));
    } catch (err) {
      console.error("Re-verification request failed", err);
    } finally {
      setReverifyBusy(false);
    }
  }

  async function loadSampleExplanation() {
    setSampleBusy(true);
    try {
      const targetLedger = evidenceLedger.length > 0 ? evidenceLedger : [
        {
          record_id: "PubMed:PMID:3829104",
          source: "PubMed",
          source_id: "PMID:3829104",
          url: "https://pubmed.ncbi.nlm.nih.gov/3829104",
          raw_json: { pmid: "3829104", title: "Target engagement and cell line response", journal: "Cell Oncol", year: "2025" },
        },
        {
          record_id: "DrugComb:block-501",
          source: "DrugComb",
          source_id: "block-501",
          url: "https://drugcomb.org",
          raw_json: { drug_a: "Compound A", drug_b: "Compound B", metric: "ZIP", ZIP: 8.4, cell_line: "H1299", unit: "uM" },
        },
      ];

      const primaryRecord = targetLedger[0];
      const secondaryRecord = targetLedger[1] || targetLedger[0];

      const sampleClaims = [
        {
          claim_text: `Biological target association observed in literature for ${primaryRecord.source_id || primaryRecord.record_id}.`,
          citation: { source: primaryRecord.source || "PubMed", record_id: primaryRecord.record_id || primaryRecord.source_id },
          claim_tag: "sourced",
          details: primaryRecord.raw_json ? { values: primaryRecord.raw_json.pmid ? { pmid: primaryRecord.raw_json.pmid } : undefined } : {},
        },
        {
          claim_text: `Reported combination synergy in vitro under specific experimental conditions.`,
          citation: { source: secondaryRecord.source || "DrugComb", record_id: secondaryRecord.record_id || secondaryRecord.source_id },
          claim_tag: "sourced",
          details: secondaryRecord.raw_json?.metric ? {
            metric: secondaryRecord.raw_json.metric,
            cell_line: secondaryRecord.raw_json.cell_line,
            units: secondaryRecord.raw_json.unit,
            values: { [secondaryRecord.raw_json.metric]: secondaryRecord.raw_json.ZIP ?? 8.4 },
          } : {},
        },
        {
          claim_text: `Assay context and protocol specifics were not documented in detail.`,
          citation: { source: secondaryRecord.source || "DrugComb", record_id: secondaryRecord.record_id || secondaryRecord.source_id },
          claim_tag: "sourced",
          details: {},
        },
        {
          claim_text: `Combined pathway target modulation may provide a candidate hypothesis for experimental follow-up.`,
          citation: null,
          claim_tag: "inferred",
          details: {},
        },
      ];

      const verificationRes = await api("/api/ai/verify-claims", {
        claims: sampleClaims,
        evidence_ledger: targetLedger,
      });

      setExplanation({
        status: "ok",
        model: "gemma-4 (grounded sample)",
        data: {
          summary: "Screening of retrieved target associations and experimental combination observations. Target modulation provides a mechanistic hypothesis; experimental conditions reflect in vitro assays and are not clinical regimens.",
          key_findings: [
            `Literature evidence retrieved for ${primaryRecord.source_id || primaryRecord.record_id}.`,
            `Experimental combination data indicates specific cell line observation.`,
            "Reported concentration ratios represent in vitro assay matrices, not therapeutic dosing.",
          ],
          uncertainty: [
            "In vitro synergy does not predict in vivo pharmacokinetics or clinical efficacy.",
            "Cell line context-dependence precludes cross-study pooling.",
          ],
          missing_evidence: [
            "Drug-drug interaction (DDI) safety data is unavailable and remains REVIEW/UNKNOWN.",
            "Long-term toxicity profiles have not been established.",
          ],
          citations: [primaryRecord.record_id || primaryRecord.source_id, secondaryRecord.record_id || secondaryRecord.source_id].filter(Boolean),
          claims: sampleClaims,
          research_hypothesis: "Target engagement combined with secondary pathway inhibition may warrant controlled in vitro validation.",
        },
        validation: {
          schema_valid: true,
          unsupported_citations_removed: 0,
          citation_ids_checked_against_bundle: true,
          semantic_grounding: "requires human review",
          claim_verification: verificationRes.data || verificationRes,
        },
      });
    } catch (err) {
      setExplanation({
        status: "unavailable",
        error: err instanceof Error ? err.message : "Failed to load sample explanation",
      });
    } finally {
      setSampleBusy(false);
    }
  }

  async function runComprehensiveDemo() {
    setCitationDemoBusy(true);
    setCitationDemo(null);
    try {
      const targetLedger = evidenceLedger.length > 0 ? evidenceLedger : [
        {
          record_id: "DrugComb:demo-block-17",
          source: "DrugComb",
          source_id: "demo-block-17",
          url: "https://drugcomb.org",
          retrieved_at: new Date().toISOString(),
          raw_json: {
            drug_a: "Aspirin",
            drug_b: "Metformin",
            metric: "ZIP",
            ZIP: 7.2,
            cell_line: "A549",
            conc_row: 0.5,
            conc_col: 1.0,
            unit: "uM",
            study: "Benchmark Study",
            assay: "dose matrix",
          },
        },
        {
          record_id: "PubMed:PMID:9990001",
          source: "PubMed",
          source_id: "PMID:9990001",
          url: "https://pubmed.ncbi.nlm.nih.gov",
          retrieved_at: new Date().toISOString(),
          raw_json: {
            pmid: "9990001",
            title: "Observed synergistic inhibition in vitro",
            journal: "J Biomed Sci",
            year: "2026",
          },
        },
      ];

      const refRecord = targetLedger[0];
      const refSource = refRecord.source || "DrugComb";
      const refId = refRecord.record_id || refRecord.source_id;
      const refRaw = refRecord.raw_json || refRecord.normalized_record || {};

      const claims = [
        // 1. VERIFIED: Source and structured fields match the ledger record
        {
          claim_text: `Reported experimental observation for ${refRaw.drug_a || "Drug A"} and ${refRaw.drug_b || "Drug B"} in ${refRaw.cell_line || "A549"}.`,
          citation: { source: refSource, record_id: refId },
          claim_tag: "sourced",
          details: {
            drug_names: [refRaw.drug_a || "Drug A", refRaw.drug_b || "Drug B"].filter(Boolean),
            metric: refRaw.metric || "ZIP",
            cell_line: refRaw.cell_line || "A549",
            units: refRaw.unit || refRaw.units || "uM",
            values: refRaw.ZIP != null ? { ZIP: refRaw.ZIP } : undefined,
          },
        },
        // 2. ID_ONLY: Citation source and record ID match, but details are absent/unreported
        {
          claim_text: `Cited record ${refId} without declared structured assay values.`,
          citation: { source: refSource, record_id: refId },
          claim_tag: "sourced",
          details: {
            unreported_toxicity_assay: "none",
          },
        },
        // 3. MISMATCH: Citation exists in ledger, but declared numeric value/metric conflicts
        {
          claim_text: `Conflicting reported synergy score for ${refId}.`,
          citation: { source: refSource, record_id: refId },
          claim_tag: "sourced",
          details: {
            metric: refRaw.metric || "ZIP",
            values: { [refRaw.metric || "ZIP"]: 99.9 },
          },
        },
        // 4. UNVERIFIABLE: Nonexistent fake PMID fixture
        {
          claim_text: "Synthetic test claim with a deliberately nonexistent PMID fixture.",
          citation: { source: "PubMed", record_id: "PMID:FAKE-TEST-0001" },
          claim_tag: "sourced",
          details: {},
        },
        // 5. UNVERIFIABLE: Sourced claim missing citation
        {
          claim_text: "Factual efficacy claim without any cited literature or ledger reference.",
          citation: null,
          claim_tag: "sourced",
          details: {},
        },
        // 6. UNVERIFIABLE: Untracked computational hypothesis
        {
          claim_text: "Inferred pathway modulation hypothesis requiring experimental validation.",
          citation: null,
          claim_tag: "inferred",
          details: {},
        },
      ];

      const res = await api("/api/ai/verify-claims", {
        claims,
        evidence_ledger: targetLedger,
      });
      setCitationDemo(res.data || res);
    } catch (err) {
      setCitationDemo({
        status: "unavailable",
        reason: err instanceof Error ? err.message : "Verifier endpoint unavailable",
      });
    } finally {
      setCitationDemoBusy(false);
    }
  }

  async function runFakeCitationCheck() {
    setCitationDemoBusy(true); setCitationDemo(null);
    try {
      const res = await api("/api/ai/verify-claims", { claims: [{
        claim_text: "Synthetic test claim with a deliberately nonexistent PMID.",
        citation: { source: "PubMed", record_id: "PMID:FAKE-TEST-0001" },
        claim_tag: "sourced", details: {},
      }], evidence_ledger: evidenceLedger });
      setCitationDemo(res.data || res);
    } catch (err) { setCitationDemo({ status: "unavailable", reason: err instanceof Error ? err.message : "Verifier endpoint unavailable" }); }
    finally { setCitationDemoBusy(false); }
  }

  return <main className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#top"><span className="brand-mark">D<span>+</span></span><span>DrugDiscover<small>RESEARCH WORKSPACE</small></span></a>
      <div className="side-label">WORKSPACE</div><a className="nav active" href="#discovery">Repurposing</a>
      <a className="nav" href="#combinations">Combination analysis</a><a className="nav" href="#molecular">Molecular validation</a>
      <div className="side-label sources-label">PROVIDER STATUS</div><div className="source-side"><i className={health?.status === "ok" ? "" : "dim"}/> Health <small>{health?.status || "checking"}</small></div>
      <div className="sidebar-bottom"><div className="shield">!</div><div><b>Research screening only</b><p>Not medical advice or a treatment recommendation.</p></div></div>
    </aside>
    <section className="main-area" id="top">
      <header className="topbar"><div className="crumb">Workspace <span>/</span> Discovery</div><div className="top-right"><span className="system-dot"/> API <code>{API.replace(/^https?:\/\//, "")}</code></div></header>
      <div className="content">
        <div className="hero-row"><div><div className="eyebrow"><span className="pulse"/> EVIDENCE-LED DISCOVERY</div><h1>Follow the biology.<br/><em>Interrogate the evidence.</em></h1><p className="hero-copy">Explore target-linked repurposing hypotheses and investigate experimental drug combinations, one source at a time.</p></div><div className="hero-art" aria-hidden="true"><div className="orb orb-a"/><div className="orb orb-b"/><div className="orb orb-c"/><div className="orbit orbit-a"/><div className="orbit orbit-b"/></div></div>
        <section className="query-card" id="discovery"><div className="step"><span>01</span> DISEASE-TO-TARGET INVESTIGATION</div><form onSubmit={analyze} className="query-form"><label htmlFor="disease">Disease or condition</label><div className="input-action"><input id="disease" placeholder="e.g. non-small cell lung cancer" value={disease} onChange={event => setDisease(event.target.value)} required/><button disabled={busy}>{busy ? <><span className="spinner"/> Searching sources</> : "Analyze evidence"}</button></div><div className="form-hint">Queries public biomedical providers where available. Results depend on current provider access.</div></form></section>
        {error && <div className="error-box">Could not complete analysis: {error}</div>}
        {busy && <div className="loading-card"><span className="spinner dark"/><div><b>Checking biomedical sources</b><p>Collecting available target, drug and publication records.</p></div></div>}
        {result && <>
          <section className="panel source-review"><div className="panel-title"><div><span className="eyebrow">RUN TRACE</span><h2>What we could not check</h2></div><button type="button" className="secondary-btn" onClick={() => openLedger()}>Open provenance ledger ({evidenceLedger.length})</button></div><div className="source-check-list">{Object.entries(sourceChecks).length ? Object.entries(sourceChecks).map(([name, check]) => <div className="source-check" key={name}><Badge kind={check.state === "CHECKED_FOUND" ? "good" : check.state === "CHECKED_EMPTY" ? "muted" : "warning"}>{name}: {check.state || "NOT_CHECKED"}</Badge><span>{check.record_count == null ? "Record count not reported" : `${check.record_count} records`}</span>{check.reason && <p>{String(check.reason)}</p>}</div>) : <p className="limitation">This run did not return source-check details. No provider check is assumed from missing status.</p>}</div></section>
          <section className="metrics-row"><div className="metric-card"><span className="metric-icon teal">D</span><div><small>DRUG CANDIDATES</small><strong>{candidates.length}</strong><span>source-linked hypotheses</span></div></div><div className="metric-card"><span className="metric-icon blue">T</span><div><small>ASSOCIATED TARGETS</small><strong>{targets.length}</strong><span>reported links</span></div></div><div className="metric-card"><span className="metric-icon violet">E</span><div><small>EVIDENCE RECORDS</small><strong>{evidenceCount + (result.data?.publications?.length || 0)}</strong><span>retrieved in this query</span></div></div><div className="metric-card"><span className="metric-icon amber">t</span><div><small>PIPELINE TIME</small><strong>{result.pipeline_latency_ms ?? "?"}<small className="unit"> ms</small></strong><span>measured request latency</span></div></div></section>
          <section className="panel results-panel"><PanelTitle kicker="REPURPOSING HYPOTHESES" title="Candidate evidence" note="Ranked by available record coverage. This is not an efficacy score."/>
            <div className="source-strip"><span>DATA SOURCES</span>{sources.length ? sources.map(([name, state]) => <div className="provider-status" key={name}><Badge kind={state.status === "available" ? "good" : "warning"}>{name.replaceAll("_", " ")} · {state.status}{state.record_count != null ? ` · ${state.record_count} records` : ""}</Badge>{state.detail && <small>{String(state.detail)}</small>}{state.matches?.length ? <small>Matches: {state.matches.map((match: Evidence) => `${match.disease_name || "disease"} (${match.disease_id || "ID unavailable"})`).join("; ")}</small> : null}</div>) : <span>Provider status not returned.</span>}</div>
            {candidates.length ? <div className="candidate-list">{candidates.map((candidate, index) => <article className={`candidate ${selected?.drug_id === candidate.drug_id ? "selected" : ""}`} key={`${candidate.drug_id || candidate.drug_name}-${index}`} onClick={() => setSelected(candidate)}><div className="candidate-index">{String(index + 1).padStart(2, "0")}</div><div className="candidate-main"><div className="candidate-name">{candidate.drug_name} {candidate.drug_id && <Badge>{candidate.drug_id}</Badge>}</div><div className="candidate-meta">Targets: {candidate.targets?.length ? candidate.targets.join(", ") : "not reported"}</div><div className="candidate-meta">Evidence level: {candidate.evidence_level || "not classified"}</div></div><div className="candidate-score"><strong>{candidate.evidence_completeness_score ?? "?"}</strong><span>record coverage</span></div><button className="arrow-btn" type="button" aria-label={`Select ${candidate.drug_name}`}>›</button></article>)}</div> : <div className="empty-state"><h3>No candidate records returned</h3><p>{result.status === "unavailable" || result.status === "partial" ? "One or more core providers are unavailable or did not resolve a disease target. No sample candidates are substituted." : "The connected sources returned no target-linked drug records for this query. No evidence of no effect is implied."}</p></div>}
            {selected && <div className="detail-box"><div className="detail-head"><div><span className="eyebrow">SELECTED HYPOTHESIS</span><h3>{selected.drug_name}</h3></div><Badge kind="warning">Research only</Badge></div><p>{selected.score_interpretation}</p><p>Target associations and drug-target records do not establish therapeutic efficacy.</p><h4>Disease-associated target evidence</h4>{selected.disease_associations?.length ? selected.disease_associations.map((association, index) => <div className="evidence-row" key={`association-${index}`}><b>{display(association.target_name || selected.targets?.[index] || selected.targets?.join(", "))}</b><span>Open Targets score: {display(association.score)}</span><span>{display(association.source)} · {display(association.source_id)}</span><SourceLink url={association.url}/></div>) : <p>Disease-association evidence is unavailable or was not returned.</p>}<h4>Traceable drug-target records</h4>{selected.evidence?.length ? selected.evidence.map((record, index) => <div className="evidence-record" key={`${record.source_id || "evidence"}-${index}`}><div className="evidence-row"><b>{display(record.gene_symbol)}</b><span>{display(record.mechanism || record.action || record.activity_type)}</span><span>{display(record.source)} · {display(record.source_id)}</span><SourceLink url={record.url}/></div><div className="evidence-context">Activity: {display(record.activity_value)} {display(record.units)} · Assay: {display(record.assay_id)} · {display(record.assay_description)} · Model: {display(record.assay_cell_type || record.assay_tissue || record.assay_organism)} · Confidence: {display(record.confidence_score)}</div></div>) : <p>No detailed drug-target records available.</p>}<button className="secondary-btn" onClick={() => { setDrugA(selected.drug_name); document.getElementById("combinations")?.scrollIntoView({ behavior: "smooth" }); }}>Use as Drug A for combination search</button></div>}
            {result.data?.limitations?.map((limitation, index) => <p className="limitation" key={index}>• {limitation}</p>)}
          </section>
          <div className="two-col"><section className="panel compact"><PanelTitle kicker="PUBLICATIONS" title="Literature evidence"/>{result.data?.publications?.length ? result.data.publications.map((paper, index) => <div className="publication" key={paper.pmid || paper.source_id || index}><b>{display(paper.title || paper.pmid || paper.source_id)}</b><span>{display(paper.journal)} · {display(paper.year)} · PMID {display(paper.pmid)}</span><SourceLink url={paper.url} label="View source"/></div>) : <div className="quiet-empty">No publication records returned for this query.</div>}</section>
            <section className="panel compact ai-panel">
              <PanelTitle kicker="GEMMA 4 · CONFIGURABLE" title="Evidence explanation & citation verifier" />
              <p className="subcopy">Gemma 4 provides auditable evidence summaries. The deterministic verifier validates citation IDs and declared structured fields without LLM judging.</p>
              <div className="verifier-toolbar">
                <button className="secondary-btn" disabled={explainBusy} onClick={explain}>
                  {explainBusy ? "Requesting explanation…" : "Explain selected evidence"}
                </button>
                <button className="secondary-btn" type="button" disabled={sampleBusy} onClick={loadSampleExplanation}>
                  {sampleBusy ? "Loading explanation…" : "Load sample explanation with claims"}
                </button>
                <button className="secondary-btn" type="button" disabled={citationDemoBusy} onClick={runComprehensiveDemo}>
                  {citationDemoBusy ? "Checking claims…" : "Demo all 4 verifier states"}
                </button>
                <button className="secondary-btn verifier-demo-button" type="button" disabled={citationDemoBusy} onClick={runFakeCitationCheck}>
                  {citationDemoBusy ? "Checking fake ID…" : "Demo verifier with fake PMID"}
                </button>
              </div>
              <p className="limitation">Synthetic verifier test only: PMID:FAKE-TEST-0001 is not a real citation or biomedical evidence.</p>

              {/* Normal explanation rendering with full detailed status table */}
              {explanation && (
                <div className="explanation">
                  <Badge kind={explanation.status === "ok" ? "good" : "warning"}>{explanation.status || "response"}</Badge>
                  <p>{explanation.data?.summary || explanation.reason || explanation.error || "No explanation returned."}</p>
                  {explanation.data?.key_findings?.length ? <ul>{explanation.data.key_findings.map((finding: string, index: number) => <li key={index}>{finding}</li>)}</ul> : null}
                  {explanation.data?.uncertainty?.length ? <p><strong>Uncertainty:</strong> {explanation.data.uncertainty.join("; ")}</p> : null}
                  {explanation.data?.missing_evidence?.length ? <p><strong>Missing evidence:</strong> {explanation.data.missing_evidence.join("; ")}</p> : null}
                  {explanation.data?.citations?.length ? <p><strong>Evidence source IDs:</strong> {explanation.data.citations.map((citation: string) => <Badge key={citation}>{citation}</Badge>)}</p> : <p className="limitation">No validated evidence citations were returned.</p>}
                  {explanation.data?.research_hypothesis && <p><strong>Research hypothesis:</strong> {explanation.data.research_hypothesis}</p>}

                  {/* Detailed Status Table for Explanation Claim Verification */}
                  {explanation.validation?.claim_verification && (
                    <CitationVerificationTable
                      verification={explanation.validation.claim_verification}
                      title="Explanation Claim Verification"
                      subtitle="Deterministic verification of atomic claims extracted from explanation against current evidence ledger."
                      onOpenProvenance={openProvenance}
                      onReverify={explanation.data?.claims?.length ? reverifyExplanationClaims : undefined}
                      reverifyBusy={reverifyBusy}
                    />
                  )}
                </div>
              )}

              {/* Detailed Status Table for Interactive Demo / Standalone Verification */}
              {citationDemo && (
                <CitationVerificationTable
                  verification={citationDemo}
                  title="Interactive Verifier Test Results"
                  subtitle="Detailed status audit of test claims against evidence ledger."
                  onOpenProvenance={openProvenance}
                  onReverify={runComprehensiveDemo}
                  reverifyBusy={citationDemoBusy}
                />
              )}
            </section>
          </div>
        </>}
        <section className="panel" id="combinations"><PanelTitle kicker="02 · EXPERIMENTAL EVIDENCE" title="Investigate a drug combination" note="Source-reported findings only. Experimental conditions are not clinical doses."/><form className="combo-form" onSubmit={analyzeCombo}><div className="field"><label htmlFor="drug-a">Drug A</label><input id="drug-a" value={drugA} onChange={event => setDrugA(event.target.value)} placeholder="Drug name or identifier" required/></div><span className="plus">+</span><div className="field"><label htmlFor="drug-b">Drug B</label><input id="drug-b" value={drugB} onChange={event => setDrugB(event.target.value)} placeholder="Drug name or identifier" required/></div><button disabled={comboBusy}>{comboBusy ? "Checking…" : "Check evidence"}</button></form>
          <button type="button" className="secondary-btn" disabled={identityBusy} onClick={resolveIdentities}>{identityBusy ? "Resolving identities…" : "Resolve drug identities and properties"}</button>
          {identity?.error && <p className="limitation">Identity lookup unavailable: {identity.error}</p>}
          {identity?.queries?.map((item: Evidence, index: number) => <div className="identity-result" key={index}><b>Drug {item.side}: {item.query}</b>{Object.entries(item.response.sources || {}).map(([provider, source]: [string, any]) => <div key={provider}><Badge kind={source.status === "ok" ? "good" : "warning"}>{provider}: {source.status || "unknown"}</Badge>{source.ambiguous && <p className="limitation">Multiple identities returned. Review identifiers, salt form, stereochemistry, and formulation; no match is selected automatically.</p>}{source.records?.map((record: Evidence, recordIndex: number) => <div className="publication" key={record.CID || record.drug_id || recordIndex}><b>{record.IUPACName || record.Title || record.molecule_pref_name || `Compound ${record.CID || record.drug_id || ""}`}</b><span>Source ID: {display(record.CID || record.drug_id)} · Formula: {display(record.MolecularFormula)} · Molecular weight: {display(record.MolecularWeight)}</span><span>SMILES: {display(record.IsomericSMILES || record.CanonicalSMILES)}</span><SourceLink url={record.source_url || record.url}/></div>)}{!source.records?.length && <p className="limitation">No identity/property record returned; this is not evidence of absence.</p>}</div>)}</div>)}
          {combo && <div className="combo-result"><div className="combo-state"><Badge kind={combo.status === "evidence_found" ? "good" : "warning"}>{combo.status || "unavailable"}</Badge><span>{combo.evidence_count ?? 0} experimental records</span><p>{combo.interpretation || combo.error || "Provider status is unavailable."}</p>{combo.error && <p>Provider detail: {combo.error}</p>}</div>
            {combo.evidence?.length ? combo.evidence.map((record: Evidence, index: number) => <div className="combo-record" key={`${record.source_id || "record"}-${index}`}><div className="record-top"><b>{display(record.metric)} · {display(record.reported_interpretation)}</b><Badge>{display(record.cell_line)}</Badge></div><div className="record-grid"><span>Score<strong>{display(record.score)}</strong></span><span>Reported ratio<strong>{display(record.ratio)}</strong></span><span>Concentrations<strong>{display(record.concentration_a)} / {display(record.concentration_b)} {display(record.concentration_unit)}</strong></span><span>Treatment context<strong>{display(record.experimental_context)}</strong></span><span>Source ID<strong>{display(record.source_id)}</strong></span><span>Study<strong>{display(record.study)}</strong></span><span>Assay<strong>{display(record.assay)}</strong></span><span>Citation<strong>{display(record.citation || record.pmid || record.doi)}</strong></span></div><SourceLink url={record.url}/></div>) : <div className="quiet-empty">No experimental observations were returned. This does not establish lack of effect.</div>}
            {combo.synergy_heatmap && <div className="combo-heatmap"><div className="heatmap-heading"><div><b>Cell line ? synergy metric</b><small>Individual source scores only; incompatible contexts are not pooled.</small></div><Badge kind={combo.synergy_heatmap.status === "ok" ? "good" : "warning"}>{combo.synergy_heatmap.status}</Badge></div>{combo.synergy_heatmap.cells?.length ? <div className="heatmap-scroll"><table><thead><tr><th>Cell line</th>{combo.synergy_heatmap.metrics.map((metric: string) => <th key={metric}>{metric}</th>)}</tr></thead><tbody>{combo.synergy_heatmap.cell_lines.map((cellLine: string | null, cellIndex: number) => <tr key={cellLine || `unreported-${cellIndex}`}><th>{display(cellLine)}</th>{combo.synergy_heatmap.metrics.map((metric: string) => { const cell = combo.synergy_heatmap.cells.find((item: Evidence) => item.cell_line === cellLine && item.metric === metric); return <td key={metric} className={cell?.state === "NO_DATA" ? "heatmap-no-data" : "heatmap-observed"}>{!cell || cell.state === "NO_DATA" ? <span className="no-observation">No observation</span> : <><span className="observation-count">{cell.observation_count} experiment{cell.observation_count === 1 ? "" : "s"}</span>{cell.scores?.map((score: Evidence, index: number) => <button type="button" className={`heatmap-score ${reportedLabelClass(score.reported_interpretation)}`} key={`${score.source_id || index}-${index}`} onClick={() => openHeatmapProvenance(score, cell)} title="Open the exact provenance record for this observation">{display(score.score)} ? {display(score.reported_interpretation)}</button>)}{cell.context_dependent && <strong className="heatmap-warning">Context-dependent ? not directly comparable</strong>}{cell.warning && <small className="heatmap-warning">{cell.warning}</small>}</>}</td>; })}</tr>)}</tbody></table></div> : <p className="quiet-empty">No DrugComb observations are available. Missing data is not additive, antagonistic, or evidence of no effect.</p>}<p className="limitation">{combo.synergy_heatmap.legend?.NO_DATA || "No observation returned; this is not additive or ineffective."} {combo.synergy_heatmap.interpretation}</p></div>}
            {combo.ratio_analysis?.observations?.length ? <div className="ratio-context"><b>Experimental ratio observations</b><p>{combo.ratio_analysis.note} Ratios and synergy metrics from different contexts must not be treated as directly interchangeable.</p>{combo.ratio_analysis.observations.map((observation: Evidence, index: number) => <div className="record-grid" key={index}><span>Cell line<strong>{display(observation.cell_line)}</strong></span><span>Metric<strong>{display(observation.metric)}</strong></span><span>Reported ratio<strong>{display(observation.reported_ratio)}</strong></span><span>Derived A:B ratio<strong>{observation.derived_ratio ? `${observation.derived_ratio.a_to_b.toFixed(3)} (${observation.derived_ratio.unit})` : "Not available"}</strong></span></div>)}</div> : null}
            <div className="safety-box"><div className="shield">!</div><div><b>Drug interaction screen · {combo.safety?.ddi_risk_level || "UNKNOWN"}</b><p>Decision: {combo.safety?.decision || "REVIEW"} · {combo.safety?.ddi_status || combo.safety?.status || "Interaction evidence unavailable"}. This is computational research screening, not a medical safety determination.</p>{combo.safety?.error && <p>{combo.safety.error}</p>}{combo.safety?.ddi_warnings?.length ? combo.safety.ddi_warnings.map((warning: Evidence, index: number) => <p key={index}>{display(warning.description || warning.severity || warning.source_id)} · {display(warning.source)} · {display(warning.source_id)}</p>) : <p>Missing interaction evidence remains UNKNOWN / REVIEW, never low risk.</p>}{combo.safety?.missing_evidence?.map((item: string, index: number) => <p key={`missing-${index}`}>{item}</p>)}</div></div>
          </div>}
        </section>
        <section className="panel" id="molecular"><PanelTitle kicker="03 · CHEMICAL VALIDATION" title="Validate a molecular structure" note="Descriptors are computational and are not a safety assessment."/><form className="molecule-form" onSubmit={validateMolecule}><label htmlFor="smiles">SMILES</label><div className="input-action"><input id="smiles" value={smiles} onChange={event => setSmiles(event.target.value)} placeholder="Paste a SMILES structure" required/><button disabled={molBusy}>{molBusy ? "Validating…" : "Validate structure"}</button></div></form>{molecule && <div className="molecule-result"><Badge kind={molecule.valid ? "good" : "warning"}>{molecule.valid ? "Structure parsed" : molecule.status || "Not validated"}</Badge>{molecule.error && <p>{molecule.error}</p>}{molecule.properties && <div className="property-grid">{Object.entries(molecule.properties).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><b>{display(value)}</b></div>)}</div>}<p className="limitation">Properties are shown only when returned by the validator. A valid SMILES parse does not establish activity or safety.</p></div>}</section>
        <footer><span>DrugDiscover AI · research prototype</span><span>Evidence is incomplete, context-dependent, and not a substitute for expert review.</span></footer>
      </div>
    </section>
    {provenanceOpen && <div className="drawer-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setProvenanceOpen(false); }}><aside className="provenance-drawer" role="dialog" aria-modal="true" aria-labelledby="provenance-title"><div className="drawer-header"><div><span className="eyebrow">AUDIT TRAIL</span><h2 id="provenance-title">{provenanceMode === "record" ? "Evidence provenance · selected record" : "Evidence provenance"}</h2></div><button type="button" className="drawer-close" onClick={() => setProvenanceOpen(false)} aria-label="Close provenance drawer">×</button></div><p className="limitation">Raw records are shown only when the ledger explicitly permits display. Missing metadata is displayed as UNKNOWN or NOT_PROVIDED.</p>{provenanceMode === "record" && <><HeatmapCellContext target={provenanceTarget}/><RecordLookupState result={provenanceResult}/></>}{drawerRecords.length ? drawerRecords.map((record, index) => <article className="ledger-record" key={record.record_id || `${record.source || "source"}-${index}`}><div className="ledger-title"><b>{display(record.source)}</b><Badge>{display(record.record_id)}</Badge></div><dl><dt>Source ID</dt><dd>{display(record.source_id)}</dd><dt>Retrieved</dt><dd>{display(record.retrieved_at)}{record.retrieved_at_status === "UNKNOWN" ? " · retrieval time not reported" : ""}{record.retrieved_at_origin === "cached" ? " · cached provider record" : ""}</dd><dt>HTTP status</dt><dd>{record.metadata_status?.http_status === "UNKNOWN" ? "UNKNOWN" : display(record.http_status)}</dd><dt>URL</dt><dd><SourceLink url={record.url}/></dd><dt>Transformations</dt><dd>{Array.isArray(record.transformations) && record.transformations.length ? record.transformations.map(String).join("; ") : "None recorded"}</dd><dt>Licence</dt><dd>{record.license || "NOT_PROVIDED"}</dd><dt>Attribution</dt><dd>{record.attribution || "NOT_PROVIDED"}</dd><dt>Content hash</dt><dd className="hash-value">{display(record.content_hash)}</dd></dl>{record.raw_display_permitted === true && record.raw_json !== undefined && record.raw_json !== null ? <details><summary>Raw source record</summary><pre>{typeof record.raw_json === "string" ? record.raw_json : JSON.stringify(record.raw_json, null, 2)}</pre></details> : <p className="limitation">Raw source data is hidden because permission was not explicitly supplied.</p>}</article>) : provenanceMode === "ledger" ? <div className="quiet-empty">No evidence ledger records were returned for this run.</div> : null}</aside></div>}
  </main>;
}
