# DrugDiscover AI contributor guide

## Project goal
Build an evidence-grounded biomedical research prototype. Read `drugdiscover_ai_codex_prompt.xml` before changing scientific behavior; it is the primary specification.

## Working rules
- Preserve source provenance, identifiers, units, experimental conditions, and timestamps.
- Missing, inaccessible, conflicting, or unverified evidence must remain explicitly missing/unknown. Never synthesize API findings, citations, molecular properties, interaction warnings, or synergy scores.
- Distinguish computational hypotheses from in-vitro, animal, and clinical evidence. This is not a clinical decision or dosing tool.
- External services must fail gracefully and report source availability. DrugBank access is conditional on authorised credentials.
- Keep backend modules separated by domain: `services/` retrieves data, `engines/` interprets it, `api/` exposes it.
- Keep the frontend responsive and show source state, limitations, and evidence alongside conclusions.
- Add no test claims without running the relevant checks. Do not commit secrets; use `.env.example`.

## Run
See `README.md` for installation and launch commands. The backend can run without external APIs; live evidence requires network access and configured services.
