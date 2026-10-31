# DrugDiscover AI � Project Status

**Checkpoint date:** 2026-10-31  
**Scope:** Source review and verification checkpoint. Backend tests and a cached frontend build were run; provider live calls and registry installation were attempted.  
**Status meanings:** `DONE` = implemented and successfully exercised; `PARTIAL` = implementation exists but has a known gap; `NOT STARTED` = no functional implementation; `NOT VERIFIED` = implementation is present but its current required verification has not succeeded or cannot be performed here.

## Overall project completion summary

The repository contains a working FastAPI/Next dashboard structure, source adapters for Open Targets, ChEMBL, PubChem, PubMed and a guarded DrugComb adapter, evidence normalization/ranking, experimental ratio handling, safety fallbacks, and a configurable Gemma response validator. Current verification on 2026-10-31: backend compilation passed and **70 tests passed**, including mocked provider and API route tests. The disease-search test now mocks the actual Open Targets dependency. A frontend production build passed only against cached Next.js 15.5.5; the manifest requires 15.5.28. TypeScript `npx tsc --noEmit` passed against the cached install. The exact 15.5.28 build is unverified. Live biomedical APIs remain unavailable from this environment.

The highest-impact gaps are: DrugComb is disabled until its deployed query parameter and response schema are verified; DrugBank has no credentials or verified account schema; the declared frontend version is Next.js 15.5.28 while installed `node_modules` contains 15.5.5 and there is no lockfile; and the complete live disease-to-Gemma workflow has not been exercised. Several API endpoints are placeholders. The app must not be treated as a clinical tool.

## Completed

### Conservative missing-DDI behavior

- **Status:** `DONE`
- **Files:** `backend/main.py`, `backend/services/drugbank_service.py`, `backend/engines/ddi_engine.py`, `backend/engines/safety_engine.py`, `backend/tests/test_evidence_safety.py`, `backend/tests/test_combination_integrations.py`, `backend/tests/test_api_endpoints.py`
- **What works:** When the current DrugBank adapter cannot provide data, safety returns `ddi_risk_level=UNKNOWN` and a workflow decision of `REVIEW`. Tests cover unknown DDI handling and confirm that missing evidence does not produce Low risk.
- **What is missing:** No live interaction source is connected, so this only verifies conservative fallback behavior. It is not a medical safety assessment.
- **Next action:** Keep the fallback unchanged; implement a live provider only after authorized access and its schema are verified, then add source-backed tests.

### Combination record normalization and experimental ratio interpretation

- **Status:** `DONE` for normalization and conservative interpretation using mocked records
- **Files:** `backend/services/drugcomb_service.py`, `backend/engines/combination_engine.py`, `backend/engines/ratio_analysis.py`, `backend/tests/test_combination_integrations.py`, `backend/tests/test_workflow.py`
- **What works:** Recognized source fields are mapped without computing synergy; original rows are retained. Mismatched named pairs are excluded. Cell line, metric, assay, study, concentrations, units, ratio, version, citations, and source IDs are preserved. Distinct dose/context records are not pooled; incomplete context prevents comparability claims. DDI warning labels map only from recognized source severities; missing or unrecognized severity remains UNKNOWN. Tests cover these behaviors with mocked records.
- **What is missing:** No verified live DrugComb query contract or real response has been used. A source ratio may be absent, and unrecognized response shapes remain unavailable.
- **Next action:** Verify the deployed API request and response schema, then add a captured/fixture response derived from a real source response with provenance and a live smoke test where access permits.

### Gemma response schema and citation filtering

- **Status:** `DONE` for mocked schema validation and citation allowlisting
- **Files:** `backend/ai/gemma_service.py`, `backend/ai/prompts.py`, `backend/ai/response_schemas.py`, `backend/tests/test_gemma.py`
- **What works:** The adapter requests structured JSON only when supplied evidence contains non-empty source records, validates the completion envelope and strict Pydantic schema, deduplicates and allowlists citation IDs against the supplied evidence, and returns explicit unavailable/error states. Mocked tests cover unconfigured provider, empty evidence, malformed completions, invalid schema, and unsupported citations.
- **What is missing:** The current environment has no Gemma endpoint/model configured. No real inference request or resulting scientific explanation has been verified.
- **Next action:** Configure an authorized OpenAI-compatible Gemma endpoint and model, then run a limited evidence-bundle integration check and verify returned citations against the supplied records.

### Deterministic citation verifier & detailed status table

- **Status:** DONE
- **Files:** ackend/ai/citation_verifier.py, ackend/main.py, ackend/tests/test_citation_verifier.py, rontend/app/CitationVerificationTable.tsx, rontend/app/page.tsx, rontend/app/styles.css
- **What works:** Deterministic citation record ID and source verification against the active evidence ledger; structured field checks (drug_names, metric, cell_line, units, context, values); supports VERIFIED, ID_ONLY, MISMATCH, and UNVERIFIABLE. Fake PMID rejection is tested. Normal Gemma explanations now fully render claim verification results in a detailed status table with summary cards, sticky headers, index, status badge, claim tag, claim text, citation with direct provenance ledger links, individual structured check chips with expected vs actual values, and diagnostic reason codes. The verifier demo provides multi-state testing (VERIFIED, ID_ONLY, MISMATCH, UNVERIFIABLE), fake-PMID rejection testing, re-verification of explanation claims against the current ledger, and a sample grounded explanation with verifiable claims. Free-text scientific entailment is explicitly and prominently disclaimed in both the notice box and limitations list. 13 unit tests pass.

### Backend compilation and automated test suite

- **Status:** `DONE` for compilation and current automated unit/route suite
- **Files:** `backend/`, `backend/tests/`, `IMPLEMENTATION_REPORT.md`
- **What works:** On 2026-10-31, `python -m compileall -q backend` passed and `python -m unittest discover -s backend/tests -v` passed **70 tests**. Coverage includes API smoke paths, provider mapping/failure handling, evidence/safety behavior, ratios, Gemma schema validation, and a mocked disease-to-combination sequence. The disease-search route test patches the actual Open Targets dependency.
- **What is missing:** Automated provider payloads and workflow evidence are mocked; live upstream provider calls failed due network restrictions. The full workflow with PubChem resolution, actual DrugBank evidence, and actual Gemma inference is not verified.
- **Next action:** Rerun compilation and the full suite after later code changes; report live verification separately from mocked tests.

## Partially Completed

### Open Targets disease search and target retrieval

- **Status:** `PARTIAL`
- **Files:** `backend/services/opentargets_service.py`, `backend/engines/repurposing_engine.py`, `backend/main.py`, `backend/tests/test_target_integrations.py`
- **What works:** The adapter issues GraphQL disease search and associated-target queries, keeps disease/target IDs, symbols, association scores, evidence, and URLs, and avoids silently choosing among ambiguous disease matches. Unit tests mock GraphQL results and ambiguity.
- **What is missing:** No live Open Targets request has been verified. Associated-target retrieval has mocked unit coverage only.
- **Next action:** Verify disease search and target retrieval against live GraphQL when outbound access is available; record source status/date.

### ChEMBL drug-target activity retrieval

- **Status:** `PARTIAL`
- **Files:** `backend/services/chembl_service.py`, `backend/engines/repurposing_engine.py`, `backend/engines/target_analysis.py`, `backend/tests/test_target_integrations.py`
- **What works:** The repurposing engine defaults to ChEMBL target retrieval for Open Targets gene symbols. The adapter retains drug/target/activity/assay IDs, measured activity and units, confidence, and available assay context. Mock tests cover normalization and engine wiring.
- **What is missing:** No live ChEMBL request has been verified. Gene-symbol synonym matching and target/activity API filters have not been validated against an upstream response in this environment. Service validates collection envelopes and reports partial failures.
- **Next action:** Run a live request for a resolved human target, verify the returned target/activity schema and filtering, and document record counts and retrieval date without substituting sample evidence.

### PubChem drug identification and molecular properties

- **Status:** `PARTIAL`
- **Files:** `backend/services/pubchem_service.py`, `backend/main.py`, `frontend/app/page.tsx`, `backend/tests/test_pubchem_service.py`
- **What works:** The code resolves drug-name queries to CIDs before requesting PubChem properties, preserves multiple matches and ambiguity, encodes query path segments, and leaves missing values missing. The UI displays CID, formula, molecular weight, and SMILES when returned. Four mocked service tests are present.
- **What is missing:** No live PubChem lookup has been verified. PubChem identity resolution is separate from combination analysis; the chosen PubChem identity is not currently used to standardize/resolve the DrugComb pair. The PUG properties requested now use `ConnectivitySMILES` and `SMILES`; schema/CID validation and missing-field tests are present.
- **Next action:** Verify live name-to-CID and property responses; implement explicit identifier selection if desired, and only pass a canonical identity into a combination provider if that provider's identity schema is verified.

### Repurposing evidence ranking and evidence-level distinctions

- **Status:** `PARTIAL`
- **Files:** `backend/engines/repurposing_engine.py`, `backend/engines/target_analysis.py`, `backend/services/opentargets_service.py`, `backend/services/chembl_service.py`, `frontend/app/page.tsx`
- **What works:** Candidate hypotheses are generated from target-linked records; evidence provenance and activity values are retained. The completeness score is labeled as coverage, not efficacy, and evidence level is not inferred as clinical.
- **What is missing:** The default live source chain is unverified. Experimental, preclinical, and clinical evidence dimensions are currently marked �not separately assessed,� not comprehensively assembled or classified.
- **Next action:** Verify the Open Targets?ChEMBL live path, then add separately sourced evidence classification only where source records support it. Do not treat the rank/coverage score as treatment efficacy.

### DrugComb experimental combination provider

- **Status:** `PARTIAL`
- **Files:** `backend/services/drugcomb_service.py`, `backend/engines/combination_engine.py`, `backend/engines/ratio_analysis.py`, `backend/main.py`, `frontend/app/page.tsx`, `.env.example`
- **What works:** `/response/` is the configured resource path. The adapter recognizes a bounded set of response shapes and metric fields, retains raw rows/context, filters explicitly mismatched drug pairs, and fails closed on unrecognized payloads, HTTP errors, and timeouts. The UI displays evidence and uncertainty.
- **What is missing:** `DRUGCOMB_DRUG_A_PARAM` and `DRUGCOMB_DRUG_B_PARAM` are unset because authoritative material reviewed establishes the host/resource but not deployed query parameters or response schema. A direct request was unreachable. Therefore the adapter returns `unavailable` by default and no experimental records are retrieved live.
- **Next action:** Obtain current deployed endpoint documentation or a working response documenting parameters and schema. Configure only verified names, retain a provenance-backed fixture, then run a live query. Mocked tests cover request mapping, invalid payload, missing configuration, and timeout but do not verify universal API parameter names.

### DrugBank provider assessment

- **Status:** `PARTIAL`
- **Files:** `backend/services/drugbank_service.py`, `backend/main.py`, `backend/engines/ddi_engine.py`, `backend/engines/safety_engine.py`, `.env.example`, `backend/tests/test_combination_integrations.py`
- **What works:** The provider returns a clear unavailable state and does not send requests against an unverified endpoint/schema. It reports configuration booleans without exposing secrets. Current process check found `DRUGBANK_API_KEY` and `DRUGBANK_API_BASE` unset; project-root `.env` is absent.
- **What is missing:** No authorized credentials, account-specific documentation, endpoint, or interaction response schema is available. No DrugBank interaction evidence is retrieved.
- **Next action:** Obtain authorized DrugBank API access and the account-specific API documentation/schema. Implement only against that material, keep credentials private, then test an authorized pair lookup and preserve source IDs/warning details.

### Disease-to-combination dashboard flow

- **Status:** `PARTIAL`
- **Files:** `frontend/app/page.tsx`, `frontend/app/styles.css`, `backend/main.py`, `backend/engines/repurposing_engine.py`, `backend/engines/combination_engine.py`, `backend/tests/test_workflow.py`
- **What works:** The UI can submit a disease, show target-linked candidate results and source states, carry a selected candidate into Drug A, resolve entered names via PubChem, query combination evidence, invoke safety screening, and request a Gemma explanation. The mocked workflow test passes a candidate into a separate combination endpoint and checks preserved experimental context.
- **What is missing:** The workflow test mocks Open Targets, ChEMBL, PubMed, and DrugComb; it does not verify live responses, PubChem resolution, Gemma inference, or interaction source retrieval in the same run. DrugComb is unavailable by default and DrugBank has no source data.
- **Next action:** After provider access is verified, execute and record the full workflow, including PubChem identity decision and Gemma citation checks. Keep unavailable stages visible when a provider cannot be reached.

### Molecular structure validation

- **Status:** `PARTIAL`
- **Files:** `backend/services/rdkit_service.py`, `backend/engines/molecular_engine.py`, `backend/main.py`, `frontend/app/page.tsx`, `backend/tests/test_evidence_safety.py`
- **What works:** Blank/non-string structures are rejected. When RDKit is installed, the code parses SMILES, computes descriptors, and names Lipinski rule violations; without RDKit it returns explicit unavailable status and null properties. It does not classify parse success as safety. Tests confirm missing RDKit never yields synthetic properties.
- **What is missing:** RDKit is not installed and is not listed in `backend/requirements.txt`; current runtime has only tested the unavailable path. Invalid/valid structure parsing and property values have not been verified in this environment.
- **Next action:** Add/install a platform-appropriate RDKit dependency if the environment supports it, then test known valid and invalid structures and report descriptor source as computed.

### Gemma configured-provider explanation

- **Status:** `PARTIAL`
- **Files:** `backend/ai/gemma_service.py`, `backend/ai/prompts.py`, `backend/ai/response_schemas.py`, `backend/main.py`, `frontend/app/page.tsx`, `backend/tests/test_gemma.py`
- **What works:** API route calls a configurable provider only when non-empty source evidence exists; prompt treats evidence as untrusted, forbids unsupported claims/dosing, and asks for uncertainty/conflicts/missing evidence. Completion shape and strict schema are validated; citations are allowlisted to supplied IDs. The dashboard renders explanation and uncertainty.
- **What is missing:** Current process has no `GEMMA_BASE_URL` or configured model; only mocked schema behavior is tested. The UI path is not verified with actual model output.
- **Next action:** Configure a supported Gemma provider and verify one grounded request, schema validation, citation filtering, and UI display using supplied evidence only.

## Not Completed

### DrugBank live interaction screening

- **Status:** `NOT STARTED` for live lookup (the unavailable-provider fallback is implemented)
- **Files:** `backend/services/drugbank_service.py`, `backend/main.py`, `backend/engines/ddi_engine.py`, `backend/engines/safety_engine.py`
- **What works:** Missing-access fallback is implemented and tested.
- **What is missing:** Authorized account access, verified endpoint/schema, identifier resolution, and actual interaction retrieval.
- **Next action:** Obtain authorized documentation and credentials; then implement and test the provider without exposing secrets.

### Persistent research reports and SQLite storage

- **Status:** `NOT STARTED`
- **Files:** `backend/main.py`, `backend/models/` (directory only/no model files listed), `backend/utils/` (directory only/no utility files listed)
- **What works:** A report lookup route exists but returns `not_found`; it is not persistence or report generation.
- **What is missing:** Database schema, migrations/initialization, report creation, persistence, and retrieval.
- **Next action:** Implement SQLite persistence and a report-create/read path only after core evidence providers are verified.

### Evidence cache and populated knowledge graph

- **Status:** `NOT STARTED`
- **Files:** `backend/main.py`, `frontend/app/page.tsx`
- **What works:** Evidence and graph routes return explicit unavailable/empty responses.
- **What is missing:** Candidate evidence retrieval by ID, graph node/edge construction, and source-backed visualization.
- **Next action:** Build these from retained provider records after source adapters and stable identifiers are verified.

### ADMET prediction, structural alerts, and docking

- **Status:** `NOT STARTED`
- **Files:** `backend/engines/admet_engine.py`, `backend/services/docking_service.py`, `backend/services/rdkit_service.py`
- **What works:** ADMET and docking modules explicitly report unavailable rather than fake estimates.
- **What is missing:** Validated prediction source/model, supported alert rules, protein/ligand inputs, and docking runtime.
- **Next action:** Treat as optional; only implement with validated inputs and label all calculations/predictions distinctly from experiment/clinical evidence.

### DGIdb and ZINC in the discovery workflow

- **Status:** `NOT STARTED` for workflow integration
- **Files:** `backend/services/dgidb_service.py`, `backend/services/zinc_service.py`, `backend/engines/repurposing_engine.py`
- **What works:** Service modules exist; ChEMBL/Open Targets currently provide the active repurposing path.
- **What is missing:** DGIdb and ZINC are not consumed by repurposing, ranking, or frontend results.
- **Next action:** Verify source interfaces/licensing, then decide whether each adds distinct evidence needed by the MVP before integrating.

### Frontend linting command

- **Status:** `NOT STARTED`
- **Files:** `frontend/package.json`
- **What works:** `dev`, `build`, and `start` scripts are declared.
- **What is missing:** No lint script or configured lint dependency/rules are present; lint has not been run.
- **Next action:** Add linting only after dependency installation is resolved, then run it and record findings.

## Verification Required

### Live biomedical API connectivity and actual schemas

- **Status:** `NOT VERIFIED`
- **Files:** `backend/services/opentargets_service.py`, `backend/services/chembl_service.py`, `backend/services/pubchem_service.py`, `backend/services/pubmed_service.py`, `backend/services/drugcomb_service.py`, `backend/tests/`
- **What works:** Source adapters and mocked tests exist for normalization, ambiguous identity handling, target activity provenance, and unavailable cases.
- **What is missing:** No live Open Targets, ChEMBL, PubChem, PubMed, or DrugComb response has been verified in this environment. The latest report identifies outbound network restrictions.
- **Next action:** Run live smoke checks when network access is available; log only source, retrieval time/status, IDs, and schema observations. Do not substitute mocked results for live evidence.

### Disease-search route test isolation

- **Status:** `DONE`
- **Files:** `backend/main.py`, `backend/tests/test_api_endpoints.py`, `backend/tests/test_opentargets_service.py`
- **What works:** The route test patches and asserts the actual `opentargets_service.search_diseases` dependency and returned Open Targets record. Provider tests verify mapping, blank/malformed results, GraphQL error, timeout, and unmatched disease behavior. The final integrated full suite passed 70 tests. These tests are mocked/unit tests; no live provider call succeeded.
- **What is missing:** Verification is mocked; no live GraphQL call succeeded.
- **Next action:** Run live smoke checks when outbound networking is available.

### Complete integrated workflow (live providers and Gemma)

- **Status:** `NOT VERIFIED`
- **Files:** `backend/tests/test_workflow.py`, `backend/main.py`, provider services, `backend/ai/gemma_service.py`, `frontend/app/page.tsx`
- **What works:** The mocked test verifies a candidate appears from mocked target/activity inputs and a mocked combination record retains cell-line, source ID, and experimental context. The frontend now separately handles combination and safety request failures and displays provider status, experimental method/context, molecular and Gemma states.
- **What is missing:** This is not an end-to-end live test; the test does not call PubChem identity resolution, DrugBank, or Gemma. DrugComb and DrugBank are unavailable by default.
- **Next action:** Execute a staged live workflow after provider access and credentials are available; record every stage's source status and preserve unknowns.

### Frontend dependency manifest, lockfile, and patched-version build

- **Status:** `NOT VERIFIED`
- **Files:** `frontend/package.json`, `frontend/package-lock.json` (absent), `frontend/node_modules/next/package.json`, `frontend/app/page.tsx`
- **What works:** The current package manifest declares Next.js `15.5.28`; existing cached `node_modules` has Next.js `15.5.5`. A production build passed on 2026-10-31 using cached 15.5.5; `npx tsc --noEmit` also passed.
- **What is missing:** The exact-declared version is not installed or tested, no `package-lock.json` exists, and `npm install --no-audit --no-fund --fetch-retries=0 --fetch-timeout=15000` failed with `EACCES` fetching `https://registry.npmjs.org/next` (all connection attempts failed). Build success using 15.5.5 does not verify 15.5.28.
- **Next action:** Restore registry access; run `npm install`, verify installed version exactly 15.5.28 and generated lockfile, then build and run lint/type checks if configured.

### Live Gemma response and citations

- **Status:** `NOT VERIFIED`
- **Files:** `backend/ai/gemma_service.py`, `backend/ai/response_schemas.py`, `backend/tests/test_gemma.py`, `frontend/app/page.tsx`
- **What works:** A mocked OpenAI-compatible response is schema-validated, and citations absent from the supplied evidence are removed.
- **What is missing:** No endpoint/model is configured in the current process, so no real Gemma request, scientific grounding quality, or live citations have been checked.
- **Next action:** Configure a supported authorized endpoint/model and test the full UI?API?Gemma response path with a bundle containing traceable identifiers.

### RDKit-valid and invalid structure calculations

- **Status:** `NOT VERIFIED`
- **Files:** `backend/services/rdkit_service.py`, `backend/engines/molecular_engine.py`, `backend/tests/test_evidence_safety.py`
- **What works:** Unavailable/null handling is tested when RDKit is absent.
- **What is missing:** Current environment has no RDKit, so valid/invalid parsing and calculated properties have not been exercised.
- **Next action:** Install RDKit in a supported environment and add/run valid SMILES, invalid SMILES, and descriptor tests.

## Provenance and source checks — completion update (2026-10-31)

### Exact heatmap-to-provenance navigation

- **Status:** `DONE` for mocked provider records; live DrugComb records remain unavailable
- **Files:** `backend/services/provenance_ledger.py`, `backend/main.py`, `frontend/app/page.tsx`, `frontend/lib/provenance.ts`, `frontend/app/styles.css`
- **What works:** Each heatmap observation is annotated with the exact `record_id` of the ledger record whose source and source ID match it. Matching requires both identifiers and exactly one ledger record; missing source, missing source ID, unknown pairs, and duplicated source IDs are marked `UNAVAILABLE`/`AMBIGUOUS` with no record ID. Clicking a cell opens a record-only drawer for that exact record, preserves the cell's metric, score, cell line, and experimental context, and shows "Provenance unavailable" with a reason when nothing matches. The full ledger is never opened as a fallback.
- **What is missing:** DrugComb is still unavailable by default, so a live run produces no heatmap observations. The provenance record store is process-local and is emptied on backend restart.
- **Next action:** Verify a live DrugComb response and confirm the same exact-match behavior on real rows.

### Persistent (process-local) provenance retrieval

- **Status:** `DONE`
- **Files:** `backend/services/provenance_ledger.py`, `backend/main.py`, `frontend/lib/provenance.ts`, `frontend/app/page.tsx`
- **What works:** `GET /api/provenance/records/{record_id}` retrieves one stored record by exact ID (400 invalid ID, 404 unknown, 503 store failure). `GET /api/provenance/records` retrieves records by exact `record_id`, `source`, `source_id`, or `experiment_id`, requires at least one filter, and returns 404 when nothing matches. Ledger generation and existing response contracts are unchanged; built records are also retained in a bounded 5,000-record store, so the drawer retrieves them independently of the frontend session.
- **What is missing:** The store is in memory, not SQLite; retrieval does not survive a restart and is not shared across workers.
- **Next action:** Move the store into the planned persistence layer while keeping the same response contract.

### Provenance metadata

- **Status:** `DONE` for metadata that adapters actually supply
- **Files:** `backend/services/provenance_ledger.py`, `backend/services/biomedical_data.py`, `backend/services/pubchem_service.py`, `backend/services/chembl_service.py`, `backend/engines/combination_engine.py`, `frontend/app/page.tsx`
- **What works:** Declared transformations are recorded, including unit conversions reported by an adapter, metric canonicalisation performed by the combination engine, and source ID string coercion actually performed by the ledger. PubChem and ChEMBL record the observed HTTP status of the request that supplied records. Licence and attribution are preserved when supplied and otherwise reported as `NOT_PROVIDED`; a missing HTTP status or retrieval time is `UNKNOWN`. Cached envelopes keep their original `retrieved_at` and are marked `retrieved_at_origin=cached`. Raw records are still returned only when `raw_display_permitted` is true.
- **What is missing:** Open Targets, PubMed, DrugComb, and DrugBank do not expose an HTTP status, so those ledger records stay `UNKNOWN`. No provider currently supplies a licence/attribution value, so those remain `NOT_PROVIDED`.
- **Next action:** Add status capture to the remaining adapters and set licence/attribution only from verified provider documentation.

### Tests added for provenance retrieval

- **Status:** `DONE`
- **Files:** `backend/tests/test_provenance_retrieval.py` (20 tests), `frontend/lib/provenance.test.ts` (9 tests), `frontend/tsconfig.json`
- **What works:** Backend coverage includes exact heatmap-to-record matching, missing `source_id`, missing/unmatched records, ambiguous IDs, individual retrieval, unknown and invalid IDs, query filters, store failure, restricted raw display, transformation metadata, present/missing HTTP status and licence, cached retrieval timestamps, and safety remaining `UNKNOWN` when DDI evidence was not checked. Frontend tests cover loading, found, empty, ambiguous, error, and no-identifier states. The full backend suite now passes 118 tests.

## Prioritized next-step checklist

1. [ ] Verify DrugComb's active `/response/` request parameters, response schema, and access requirements from authoritative current documentation or a working response; do not set guessed env vars.
2. [ ] Obtain authorized DrugBank credentials and account-specific API schema, or keep the documented unavailable fallback.
3. [x] Fix the Open Targets disease-search test mock target and rerun compilation plus all backend tests (70 passed; mocked).
4. [ ] Restore npm registry access; run `npm install`, verify Next.js 15.5.28 is actually installed and create/check the lockfile, then run the production build and lint if configured. Cached 15.5.5 build and TypeScript check passed; declared-version build remains unverified.
5. [ ] Run live Open Targets?ChEMBL?PubChem checks and capture a staged disease-to-combination workflow with source provenance.
6. [ ] Configure Gemma and verify actual evidence-grounded output/citation filtering end to end.
7. [ ] Install RDKit in the target runtime and verify valid/invalid structure parsing and computed descriptors.
8. [x] Add exact heatmap-cell-to-record provenance navigation, record retrieval endpoints, and metadata status fields (backend suite 118 passed; frontend helper tests 9 passed; build passed with cached Next.js 15.5.5).
9. [ ] Only then prioritize persistence/reports, populated graph, DGIdb/ZINC workflow use, ADMET, structural alerts, and docking.

## Exact project commands

From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
python -m compileall -q backend
python -m unittest discover -s backend/tests -v
python -m uvicorn backend.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Production frontend checks, after the declared dependency can be installed:

```powershell
cd frontend
npm install
node -p "require('./node_modules/next/package.json').version"
npm run build
```

Current verified-vs-declared version mismatch: **installed 15.5.5; declared 15.5.28; lockfile absent**. Do not claim the patched-version production build until the final command succeeds with 15.5.28 installed.
