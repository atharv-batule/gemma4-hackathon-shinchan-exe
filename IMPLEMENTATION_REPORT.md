# Implementation report

## Delivered
- Wired Open Targets disease resolution and disease-associated targets, ChEMBL target activity records, and PubMed retrieval into the repurposing engine defaults. Ambiguous disease names return an explicit unresolved status; target and activity provenance is retained.
- Upgraded PubChem lookups to resolve compound names to CIDs first, preserve multiple/ambiguous matches, and return only PubChem-sourced chemical properties with missing fields left missing.
- Added frontend drug identity/property lookup and a workflow control that carries a selected repurposing candidate into Drug A for combination investigation.
- Added DrugComb `/response/` adapter that preserves original rows, source identifiers, cell line, study, metric, concentrations, and units. Because the deployed API query-parameter contract could not be verified here, it remains disabled unless parameter names are explicitly configured after verification; no parameters or synergy scores are guessed.
- DrugBank remains gated. The adapter reports configuration state but does not call an unverified, account-specific endpoint. Safety remains `UNKNOWN`/`REVIEW` without interaction evidence.
- Combination ratio analysis keeps contexts separate by cell line, metric, unit, and study. It retains source ratios and labels arithmetic concentration ratios as computed experimental context, never clinical dosage.
- Added Gemma schema/citation tests and frontend rendering for summary, findings, uncertainty, missing evidence, and supplied citations.
- Added timed contract envelopes to API routes, dotenv loading, updated setup documentation, and all-route endpoint smoke tests.

## Verification performed
- `python -m compileall -q backend`: passed.
- `python -m unittest discover -s backend/tests -v`: 33 tests passed, including mocked service adapter tests, smoke checks for all 12 API paths, and a disease-to-combination workflow test.
- Uvicorn launched successfully and `/health` returned HTTP 200. The API endpoint suite uses mocks to avoid presenting fabricated API responses.
- Frontend `npm install --offline --no-audit --no-fund` and `npm run build` succeeded with Next.js 15.5.5 installed from cache. The build uncovered and fixed malformed nullish-coalescing expressions in the existing UI.

## Remaining limitations
- **Frontend patch version:** npm registry access fails with EACCES. The code built with cached Next.js 15.5.5, but that release is not suitable for deployment. The manifest has been advanced to Next.js 15.5.28, the fixed Maintenance LTS release, but this sandbox cannot install that version or regenerate a matching lockfile. Run `npm install` and `npm run build` after registry access is available. See the [official Next.js security update](https://nextjs.org/blog/nextjs-security-update-october-14-2026).
- Live Open Targets, ChEMBL, PubChem, PubMed, and DrugComb HTTP requests were not verified because outbound networking is restricted. API tests use mocked responses.
- DrugComb query parameter names must be configured only after verifying the active DrugComb API contract. As shipped, combination lookup is explicit unavailable without those names; the adapter recognizes only known response fields and retains the complete source record.
- DrugBank still requires authorized access and a verified account-specific endpoint/schema; none is configured.
- RDKit is not installed in the current backend environment; molecular endpoint reports unavailable with null properties. ADMET prediction, docking, SQLite report persistence, knowledge graph population, and persistent report generation remain unimplemented.
- No API suggests treatment or patient-specific dosage. Target associations are not efficacy claims; lack of DDI data is not classified as low risk.


## Verification update ? 2026-10-31

### Backend
- `python -m compileall -q backend`: **passed**.
- `python -m unittest discover -s backend/tests -v`: **70 passed**. All provider payloads in automated tests are mocked; no test result implies upstream availability.
- Corrected the disease-search endpoint test to patch `backend.services.opentargets_service.search_diseases` (the route's actual dependency). Added Open Targets service tests for mapping, empty/malformed search data, GraphQL errors, timeouts, and unmatched disease behavior.
- ChEMBL response collection validation and explicit partial/unavailable handling are covered by mocked schema/failure tests. PubChem CID/property envelope validation, updated PUG property names (`ConnectivitySMILES`, `SMILES`), and absent-property behavior are covered by mocked tests. DrugComb tests cover no configuration, caller-supplied parameter mapping, malformed payload, and timeout; supplied names are test configuration only and do not assert DrugComb's real parameter contract.

### Live provider checks
On 2026-10-31, direct asynchronous requests were attempted for Open Targets disease search and target retrieval (`lung cancer`), ChEMBL target activity (`ESR1`), PubChem identity lookup (`aspirin`), and PubMed (`lung cancer`). Each returned `unavailable`, zero records, with connection failures (`All connection attempts failed` / `ConnectError`). These are failed live attempts, not mocked successes. DrugComb was not called because the query parameter and response schema are not verified; its public host/resource are described in literature, but this environment could not reach the service. DrugBank was not called: no authorized credentials/account schema are available (`DRUGBANK_API_KEY` and `DRUGBANK_API_BASE` were absent). Gemma was not called: `GEMMA_BASE_URL` and `GEMMA_MODEL` are not configured. DrugComb parameter-name environment variables are also absent.

### Frontend
- `npm run build`: **passed with cached Next.js 15.5.5** (production static build). `npx tsc --noEmit`: **passed** using that same cached install.
- `frontend/package.json` declares Next.js **15.5.28**; installed `frontend/node_modules/next` is **15.5.5**. No ESLint/lint script or configuration is present. The required-version build is therefore **NOT VERIFIED**. No package lockfile exists.
- `npm install --no-audit --no-fund --fetch-retries=0 --fetch-timeout=15000` failed while fetching `https://registry.npmjs.org/next` with npm `EACCES` / `All connection attempts failed`; npm also could not write its log under the user cache path. No lint script is configured.

### Remaining integration and safety limitations
- DrugComb needs authoritative deployed parameter names, response schema, and access requirements, then a live response test. Do not configure guessed parameter names. References checked: [DrugComb update paper](https://academic.oup.com/nar/article/49/W1/W174/6290546) and [API usage in a peer-reviewed study](https://pmc.ncbi.nlm.nih.gov/articles/PMC11290087/).
- DrugBank needs authorized credentials plus account-specific endpoint/API documentation. Current adapter intentionally sends no request.
- Repurposing and complete disease-to-combination demonstrations remain mocked/unverified end to end because all live source requests failed. PubChem identity resolution is not used to standardize the DrugComb pair.
- Gemma grounding and citations are mock-tested only; a real model request is unverified.
- Drug interaction absence stays `UNKNOWN`/`REVIEW`. Experimental concentrations are not clinical dosing; target associations and computational outputs are not efficacy or medical safety conclusions.

### Exact verification commands
From project root (PowerShell):

```powershell
python -m compileall -q backend
python -m unittest discover -s backend/tests -v
python -m uvicorn backend.main:app --reload
```

Frontend, after registry access is restored:

```powershell
cd frontend
npm install
node -p "require('./node_modules/next/package.json').version" # must print 15.5.28
npm run build
npm run dev
```

The package currently has no lint script.


## Integrated workstream closeout ? 2026-10-31

The project was reviewed and updated in the existing architecture across biomedical providers, repurposing, combination/safety, molecular/Gemma, and frontend workstreams. Files updated include provider adapters and tests under `backend/services/` and `backend/tests/`; repurposing and combination/safety engines under `backend/engines/`; Gemma modules under `backend/ai/`; `frontend/app/page.tsx`; and `frontend/app/styles.css`. No package or dependency manifest changes were made during the frontend workstream.

Final verification after integration:
- Backend `python -m compileall -q backend`: passed.
- Backend `python -m unittest discover -s backend/tests -v`: **70 passed**. API route smoke tests and all provider tests are mocked; the workflow test is mocked.
- Frontend `npx tsc --noEmit`: passed.
- Frontend `npm run build`: passed using installed Next.js **15.5.5**. `frontend/package.json` declares **15.5.28**; npm install failed with EACCES accessing the registry, no lockfile exists, and build using 15.5.28 remains unverified.
- Live checks for Open Targets disease search/targets, ChEMBL ESR1 activity, PubChem aspirin, and PubMed lung-cancer search all returned unavailable due connection failures. No live biomedical provider succeeded.

Changes improve strict Open Targets/PubMed/ChEMBL/PubChem response validation, partial/unavailable provider reporting, source record provenance, repurposing coverage-only ranking, experiment-context separation, mismatch filtering, conservative DDI severity mapping, explicit RDKit unavailable behavior, Gemma evidence prerequisites and citation allowlisting, and dashboard error/source/context rendering. DrugComb stays fail-closed because exact deployed parameters and response schema could not be verified. DrugBank stays unavailable because no authorized credential or account documentation/schema was found. Gemma has no configured endpoint/model; RDKit is not installed.

The project is a runnable research MVP shell with tested mocked flows, not a fully connected live biomedical platform. A complete live end-to-end disease-to-combination demonstration could not be verified due external network and provider access blockers.


## Provenance retrieval closeout - 2026-10-31

### Delivered changes
The remaining provenance and source-check work was completed without rebuilding the ledger or the source-check panel.

- **Exact heatmap-to-record navigation**: `annotate_heatmap_provenance()` in `backend/services/provenance_ledger.py` attaches a `record_id` to each heatmap observation only when the observation's source label and source ID resolve to exactly one ledger record. Missing source labels, missing source IDs, unknown pairs, and duplicated source IDs are marked `UNAVAILABLE`/`AMBIGUOUS` with no record ID and a reason. The combination route applies this to the generated heatmap, leaving the heatmap's existing fields unchanged. In `frontend/app/page.tsx`, clicking a cell opens a record-only drawer for that exact `record_id`, keeps the cell's metric, score, cell line, and experimental context visible, and never falls back to the full ledger. The explicit "Open provenance ledger" button still opens the complete session ledger.
- **Record retrieval endpoints**: `GET /api/provenance/records/{record_id}` returns one stored record by exact ID, and `GET /api/provenance/records` retrieves records by exact `record_id`, `source`, `source_id`, or `experiment_id` (at least one filter required). Responses distinguish found, ambiguous, not found (404), invalid identifier (400), and store failure (503). `build_evidence_ledger()` now also retains built records in a bounded 5,000-record process-local store; its returned structure and all existing response contracts are unchanged. The frontend drawer uses these endpoints through `frontend/lib/provenance.ts`.
- **Metadata**: ledger records now report `transformations`, `http_status`, `license`, `attribution`, `retrieved_at_status`, `retrieved_at_origin`, `experiment_id`, and a `metadata_status` object whose values are only `PROVIDED`, `UNKNOWN`, or `NOT_PROVIDED`. Transformations are recorded only when they occur: adapter-declared unit conversions, the combination engine's metric canonicalisation (e.g. `zip` to `ZIP`), and the ledger's own source-ID string coercion. `biomedical_data.get_json()` can now record the observed response status, and the PubChem and ChEMBL adapters pass it through. Cached envelopes keep their original `retrieved_at` and are marked as cached. Raw records are still emitted only when `raw_display_permitted` is true. The drawer displays `UNKNOWN`/`NOT_PROVIDED`/`None recorded` instead of inventing values.

### Tests added
- `backend/tests/test_provenance_retrieval.py`: **20 tests** covering exact heatmap-cell-to-record matching, missing `source_id`, missing source label, unmatched records, ambiguous source IDs, individual retrieval, unknown and invalid record IDs, required query filters, source/experiment retrieval, store failure, restricted raw-record display, transformation metadata, present and missing HTTP status and licence, cached/unreported retrieval timestamps, and DDI safety remaining `UNKNOWN`/`REVIEW` when DrugBank evidence was not checked.
- `frontend/lib/provenance.test.ts`: **9 tests** (Node built-in test runner) covering drawer loading, exact lookup, found record, empty/not-found, ambiguous, HTTP and network errors, and no-identifier states. `tsconfig.json` enables `allowImportingTsExtensions` for the `.ts` test import.

### Verification performed
- `python -m compileall -q backend`: passed.
- `python -m unittest discover -s backend/tests`: **118 tests passed** (including the 20 new provenance retrieval tests). All provider payloads remain mocked.
- `npx tsc --noEmit` (in `frontend`): passed.
- `node --test lib/provenance.test.ts` (in `frontend`): 9 passed.
- `npm run build` (in `frontend`): passed with the cached **Next.js 15.5.5**. The manifest still declares 15.5.28, which is not installed, so the declared-version build remains unverified.

### Limitations
- The provenance record store is in-memory and bounded; records do not survive a backend restart or span workers. It is not the planned SQLite persistence layer.
- Live DrugComb data is still unavailable, so exact heatmap navigation was exercised only with mocked provider records. Open Targets, PubMed, DrugComb, and DrugBank still do not report an HTTP status, and no provider supplies a licence/attribution value; those ledger fields correctly remain `UNKNOWN`/`NOT_PROVIDED`.
- The frontend checks are type checks, helper-unit tests, and a production build. Drawer states were not exercised in a live browser against a running backend.
- Drug interaction evidence remains `UNKNOWN`/`REVIEW`; nothing in this change is a clinical safety or dosing conclusion.
