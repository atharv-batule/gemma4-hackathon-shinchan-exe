import json
import os
import unittest
from unittest.mock import MagicMock, patch
from backend.ai.gemma_service import explain_evidence

class GemmaTests(unittest.TestCase):
    def test_unconfigured_provider_is_unavailable(self):
        with patch.dict(os.environ,{"GEMMA_BASE_URL":"","GEMMA_MODEL":""},clear=False):
            result=explain_evidence({"data":{}})
        self.assertEqual(result["status"],"unavailable")
        self.assertIsNone(result["data"])

    def test_valid_response_schema_and_unsupported_citation_removed(self):
        completion={"summary":"Only the supplied record can support this summary.","key_findings":["Observed target evidence."],"uncertainty":["No clinical evidence supplied."],"missing_evidence":["No DDI coverage."],"citations":["PMID:123","invented"],"claims":[{"claim_text":"A retrieved publication record was supplied.","citation":{"source":"PubMed","record_id":"PubMed:PMID:123"},"claim_tag":"sourced","details":{}}],"research_hypothesis":None}
        response=MagicMock()
        response.json.return_value={"choices":[{"message":{"content":json.dumps(completion)}}]}
        client=MagicMock(); client.__enter__.return_value=client; client.__exit__.return_value=False; client.post.return_value=response
        with patch.dict(os.environ,{"GEMMA_BASE_URL":"http://localhost:8080/v1","GEMMA_MODEL":"gemma-4","GEMMA_API_KEY":""},clear=False), patch("backend.ai.gemma_service.httpx.Client",return_value=client):
            result=explain_evidence({"citations":["PMID:123"],"evidence":[{"source_id":"PMID:123"}],"evidence_ledger":[{"record_id":"PubMed:PMID:123","source":"PubMed","source_id":"PMID:123","raw_json":{"pmid":"123"}}]})
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["data"]["citations"],["PMID:123"])
        self.assertEqual(result["validation"]["unsupported_citations_removed"],1)
        self.assertTrue(result["validation"]["citation_ids_checked_against_bundle"])
        self.assertEqual(result["validation"]["semantic_grounding"],"requires human review")
        self.assertEqual(result["validation"]["claim_verification"]["results"][0]["status"], "ID_ONLY")

    def test_empty_evidence_does_not_call_model(self):
        client = MagicMock()
        with patch.dict(os.environ,{"GEMMA_BASE_URL":"http://localhost:8080/v1","GEMMA_MODEL":"gemma-4"},clear=False), patch(
            "backend.ai.gemma_service.httpx.Client",return_value=client
        ):
            result=explain_evidence({"data":{"candidates":[],"targets":[],"publications":[]}})
        self.assertEqual(result["status"],"insufficient_evidence")
        client.assert_not_called()

    def test_malformed_completion_is_unavailable(self):
        response=MagicMock()
        response.json.return_value={"choices":[{"message":{"content":[{"text":"not text"}]}}]}
        client=MagicMock(); client.__enter__.return_value=client; client.__exit__.return_value=False; client.post.return_value=response
        with patch.dict(os.environ,{"GEMMA_BASE_URL":"http://localhost:8080/v1","GEMMA_MODEL":"gemma-4","GEMMA_API_KEY":""},clear=False), patch(
            "backend.ai.gemma_service.httpx.Client",return_value=client
        ):
            result=explain_evidence({"evidence":[{"source_id":"PMID:1"}]})
        self.assertEqual(result["status"],"unavailable")
        self.assertIsNone(result["data"])

    def test_extra_or_empty_schema_fields_are_rejected(self):
        completion={"summary":"","key_findings":[],"uncertainty":[],"missing_evidence":[],"citations":[],"research_hypothesis":None,"unsupported":"x"}
        response=MagicMock(); response.json.return_value={"choices":[{"message":{"content":json.dumps(completion)}}]}
        client=MagicMock(); client.__enter__.return_value=client; client.__exit__.return_value=False; client.post.return_value=response
        with patch.dict(os.environ,{"GEMMA_BASE_URL":"http://localhost:8080/v1","GEMMA_MODEL":"gemma-4","GEMMA_API_KEY":""},clear=False), patch(
            "backend.ai.gemma_service.httpx.Client",return_value=client
        ):
            result=explain_evidence({"evidence":[{"source_id":"PMID:1"}]})
        self.assertEqual(result["status"],"unavailable")

    def test_duplicate_valid_citations_are_deduplicated(self):
        completion={"summary":"One supplied record is present.","key_findings":[],"uncertainty":[],"missing_evidence":[],"citations":["PMID:1","PMID:1"],"claims":[{"claim_text":"Record present.","citation":{"source":"PubMed","record_id":"PubMed:PMID:1"},"claim_tag":"sourced","details":{"values":{"pmid":"1"}}}],"research_hypothesis":None}
        response=MagicMock(); response.json.return_value={"choices":[{"message":{"content":json.dumps(completion)}}]}
        client=MagicMock(); client.__enter__.return_value=client; client.__exit__.return_value=False; client.post.return_value=response
        with patch.dict(os.environ,{"GEMMA_BASE_URL":"http://localhost:8080/v1","GEMMA_MODEL":"gemma-4","GEMMA_API_KEY":""},clear=False), patch(
            "backend.ai.gemma_service.httpx.Client",return_value=client
        ):
            result=explain_evidence({"evidence":[{"source_id":"PMID:1"}]})
        self.assertEqual(result["data"]["citations"],["PMID:1"])

    def test_claim_numeric_mismatch_is_exposed_in_gemma_result(self):
        completion={"summary":"A sourced claim.","key_findings":[],"uncertainty":[],"missing_evidence":[],"citations":["DrugComb:block-1"],"claims":[{"claim_text":"ZIP was 9.","citation":{"source":"DrugComb","record_id":"DrugComb:block-1"},"claim_tag":"sourced","details":{"metric":"ZIP","values":{"ZIP":9}}}],"research_hypothesis":None}
        response=MagicMock(); response.json.return_value={"choices":[{"message":{"content":json.dumps(completion)}}]}
        client=MagicMock(); client.__enter__.return_value=client; client.__exit__.return_value=False; client.post.return_value=response
        ledger={"evidence_ledger":[{"record_id":"DrugComb:block-1","source":"DrugComb","source_id":"block-1","raw_json":{"ZIP":7.2,"metric":"ZIP"}}]}
        with patch.dict(os.environ,{"GEMMA_BASE_URL":"http://localhost:8080/v1","GEMMA_MODEL":"gemma-4","GEMMA_API_KEY":""},clear=False), patch("backend.ai.gemma_service.httpx.Client",return_value=client):
            result=explain_evidence({"evidence":[{"source_id":"block-1"}],**ledger})
        self.assertEqual(result["validation"]["claim_verification"]["results"][0]["status"], "MISMATCH")

if __name__=='__main__': unittest.main()
