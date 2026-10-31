import unittest
import httpx
from unittest.mock import AsyncMock, patch
from backend.services import opentargets_service, chembl_service
from backend.engines.repurposing_engine import analyze_disease
from backend.engines.target_analysis import build_target_evidence, rank_candidates

class TargetIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_opentargets_returns_source_gene_and_score(self):
        async def fake(query, variables):
            if "DiseaseSearch" in query:
                return {"search":{"hits":[{"id":"EFO_X","name":"Condition X","entity":"disease"}]}}
            return {"disease":{"id":"EFO_X","name":"Condition X","associatedTargets":{"rows":[{"score":0.7,"target":{"id":"ENSG1","approvedSymbol":"GENE1","approvedName":"Gene One"},"datatypeScores":[{"id":"genetic_association","score":0.6}]}]}}}
        with patch.object(opentargets_service,"_graphql",side_effect=fake):
            result=await opentargets_service.disease_targets("Condition X")
        self.assertEqual(result["records"][0]["gene_symbol"],"GENE1")
        self.assertEqual(result["records"][0]["score"],0.7)
        self.assertEqual(result["records"][0]["source"],"Open Targets")

    async def test_opentargets_does_not_guess_ambiguous_disease(self):
        with patch.object(opentargets_service,"search_diseases",return_value={"status":"ok","records":[{"disease_id":"E1","disease_name":"X one"},{"disease_id":"E2","disease_name":"X two"}]}):
            result=await opentargets_service.disease_targets("X")
        self.assertEqual(result["status"],"ambiguous")
        self.assertEqual(result["records"],[])

    async def test_chembl_normalizes_assay_provenance(self):
        async def fake_json(url,params=None):
            if url.endswith("target.json"):
                return {"targets":[{"target_chembl_id":"CHEMBL_T1","organism":"Homo sapiens"}]}
            return {"activities":[{"activity_id":123,"molecule_chembl_id":"CHEMBL_D1","molecule_pref_name":"Example","target_chembl_id":"CHEMBL_T1","standard_type":"IC50","standard_value":"12","standard_units":"nM","confidence_score":9,"assay_chembl_id":"CHEMBL_A1","assay_description":"binding assay"}]}
        with patch.object(chembl_service,"get_json",side_effect=fake_json):
            result=await chembl_service.drug_targets_for_genes(["GENE1"])
        self.assertEqual(result["status"],"ok")
        rec=result["records"][0]
        self.assertEqual(rec["drug_id"],"CHEMBL_D1")
        self.assertEqual(rec["source_id"],123)
        self.assertEqual(rec["units"],"nM")
        self.assertEqual(rec["evidence_class"],"experimental assay record")

    async def test_chembl_invalid_target_schema_is_not_empty_success(self):
        async def fake_json(url, params=None):
            return {"targets": {"unexpected": "object"}}
        with patch.object(chembl_service,"get_json",side_effect=fake_json):
            result=await chembl_service.drug_targets_for_genes(["GENE1"])
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["records"],[])

    async def test_chembl_upstream_timeout_is_not_empty_success(self):
        async def fake_json(url, params=None):
            if url.endswith("target.json"):
                return {"targets":[{"target_chembl_id":"CHEMBL_T1","organism":"Homo sapiens"}]}
            return {"activities":[{"activity_id":123,"molecule_chembl_id":"CHEMBL_D1","confidence_score":9}]}
        async def fail_second(url, params=None):
            if url.endswith("activity.json"):
                raise httpx.TimeoutException("upstream timed out")
            return await fake_json(url, params)
        with patch.object(chembl_service,"get_json",side_effect=fail_second):
            result=await chembl_service.drug_targets_for_genes(["GENE1"])
        self.assertEqual(result["status"],"unavailable")
        self.assertTrue(result["errors"])

    async def test_chembl_activity_schema_failure_is_not_silent(self):
        async def fake_json(url, params=None):
            if url.endswith("target.json"):
                return {"targets":[{"target_chembl_id":"CHEMBL_T1","organism":"Homo sapiens"}]}
            return {"activities": None}
        with patch.object(chembl_service,"get_json",side_effect=fake_json):
            result=await chembl_service.drug_targets_for_genes(["GENE1"])
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["records"],[])

    async def test_default_engine_calls_all_default_providers(self):
        async def genes(q): return {"status":"ok","records":[{"gene_symbol":"GENE1","source":"Open Targets","source_id":"E:ENSG1","score":0.4}]}
        async def drugs(symbols,**kwargs): return {"status":"ok","records":[{"gene_symbol":"GENE1","drug_name":"Example","drug_id":"CHEMBL1","source":"ChEMBL","source_id":"A1"}]}
        async def pubs(q): return {"status":"ok","records":[]}
        with patch("backend.services.opentargets_service.disease_targets",genes), patch("backend.services.chembl_service.drug_targets_for_genes",drugs), patch("backend.services.pubmed_service.search",pubs):
            result=await analyze_disease("Condition")
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["data"]["candidates"][0]["drug_id"],"CHEMBL1")

    async def test_engine_preserves_source_unavailability_and_skips_chEmbl_without_targets(self):
        async def genes(q): return {"status":"unavailable","source":"Open Targets","records":[],"reason":"upstream timeout"}
        async def drugs(*args, **kwargs): self.fail("ChEMBL must not be queried without resolved target symbols")
        async def pubs(q): return {"status":"ok","records":[]}
        result = await analyze_disease("Condition", disease_gene_provider=genes,
                                       drug_target_provider=drugs, publication_provider=pubs)
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["data"]["sources"]["disease_gene"]["status"], "unavailable")
        self.assertEqual(result["data"]["sources"]["drug_target"]["status"], "not_run")
        self.assertEqual(result["data"]["candidates"], [])

    async def test_engine_marks_partial_when_target_source_fails(self):
        async def genes(q): return {"status":"ok","records":[{"gene_symbol":"GENE1","source":"Open Targets","source_id":"EFO1:ENSG1","score":0.5}]}
        async def drugs(symbols, **kwargs): raise httpx.ReadTimeout("ChEMBL timed out")
        async def pubs(q): return {"status":"unavailable","records":[]}
        result = await analyze_disease("Condition", disease_gene_provider=genes,
                                       drug_target_provider=drugs, publication_provider=pubs)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["data"]["sources"]["drug_target"]["status"], "unavailable")
        self.assertEqual(result["data"]["sources"]["publications"]["status"], "unavailable")

    def test_candidates_keep_only_source_supplied_associations_and_assay_citations(self):
        combined = build_target_evidence(
            [{"gene_symbol":"GENE1","target_id":"ENSG1","source":"Open Targets","source_id":"EFO1:ENSG1","score":0.8,"url":"https://source.test/target"}],
            [{"gene_symbol":"GENE1","drug_name":"Example","drug_id":"CHEMBL1","source":"ChEMBL","source_id":"ACTIVITY1","assay_id":"ASSAY1","activity_type":"IC50","activity_value":"12","units":"nM","assay_description":"binding","assay_cell_type":"Cell X","url":"https://source.test/activity"}],
        )
        candidate = rank_candidates(combined["targets"])[0]
        self.assertEqual(candidate["disease_associations"][0]["source_id"], "EFO1:ENSG1")
        self.assertEqual(candidate["evidence"][0]["source_id"], "ACTIVITY1")
        self.assertEqual(candidate["evidence"][0]["assay_id"], "ASSAY1")
        self.assertEqual(candidate["evidence"][0]["assay_cell_type"], "Cell X")
        self.assertIn("not efficacy", candidate["score_interpretation"])
        self.assertNotIn("citation", candidate)

if __name__ == "__main__": unittest.main()
