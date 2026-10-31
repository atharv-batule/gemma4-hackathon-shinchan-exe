---
name: drug-discovery
description: Build evidence-grounded drug repurposing, drug combination, molecular validation and biomedical research workflows using Gemma 4.
---

# Drug discovery research workflow

- Standardise drug identity with source identifiers and preserve salt, stereochemistry, and formulation distinctions.
- Query biomedical sources through their documented interfaces. Record the source, source ID, retrieval status, and relevant experimental context.
- Separate hypothesis-generating target associations from experimental and clinical evidence. Never claim therapeutic efficacy from a mechanism or docking result.
- For combinations, report only source-observed synergy metrics and experimental concentrations, units, ratios, and cell line. Do not compare incompatible contexts as if equivalent.
- Screen interactions only from an accessible, authorised source. Unknown coverage produces `UNKNOWN`/`REVIEW`, never Low risk.
- Parse structures with RDKit where installed. Computed descriptors must be labeled as computed; unavailable descriptors remain null. Valid structure does not imply safety.
- Ground Gemma output only in supplied evidence, preserve citations, reject unsupported claims, and expose concise rationale rather than private chain-of-thought.
- Keep all output within computational research screening; never offer patient-specific treatment or dosing advice.
