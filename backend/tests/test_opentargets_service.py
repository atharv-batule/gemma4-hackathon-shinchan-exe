import unittest
from unittest.mock import AsyncMock, patch
import httpx
from backend.services import opentargets_service as ot

class OpenTargetsServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_disease_search_maps_source_identifiers_and_names(self):
        async def graphql(query, variables):
            self.assertIn('entityNames: ["disease"]', query)
            self.assertEqual(variables, {"q":"lung cancer", "size":8})
            return {"search":{"hits":[{"id":"EFO_0001071","name":"lung cancer","entity":"disease"}]}}
        with patch.object(ot,"_graphql",side_effect=graphql) as request:
            result=await ot.search_diseases("lung cancer")
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["records"],[{"disease_id":"EFO_0001071","disease_name":"lung cancer","entity":"disease","url":"https://platform.opentargets.org/disease/EFO_0001071"}])
        request.assert_awaited_once()

    async def test_blank_query_returns_empty_without_request(self):
        with patch.object(ot,"_graphql",new_callable=AsyncMock) as request:
            result=await ot.search_diseases("  ")
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["records"],[])
        request.assert_not_awaited()

    async def test_malformed_or_missing_search_hits_are_unavailable_not_empty_success(self):
        for payload in ({"search":{}},{"search":{"hits":[{}, {"id":"EFO_X"}]}}):
            with self.subTest(payload=payload), patch.object(ot,"_graphql",new_callable=AsyncMock,return_value=payload):
                result=await ot.search_diseases("unknown condition")
                self.assertEqual(result["status"],"unavailable")
                self.assertEqual(result["records"],[])

    async def test_invalid_target_rows_are_unavailable(self):
        async def graphql(query, variables):
            if "DiseaseSearch" in query:
                return {"search":{"hits":[{"id":"EFO_X","name":"condition","entity":"disease"}]}}
            return {"disease":{"id":"EFO_X","name":"condition","associatedTargets":{"rows":"invalid"}}}
        with patch.object(ot,"_graphql",side_effect=graphql):
            result=await ot.disease_targets("condition")
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["records"],[])

    async def test_graphql_error_becomes_explicit_unavailable(self):
        with patch.object(ot,"_graphql",new_callable=AsyncMock,side_effect=RuntimeError("graphql failed")):
            result=await ot.search_diseases("condition")
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["source"],"Open Targets")
        self.assertEqual(result["records"],[])
        self.assertIn("graphql failed",result["error"])

    async def test_timeout_becomes_explicit_unavailable_for_disease_target_lookup(self):
        with patch.object(ot,"_graphql",new_callable=AsyncMock,side_effect=httpx.ReadTimeout("timed out")):
            result=await ot.disease_targets("condition")
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["records"],[])
        self.assertTrue(result["error"])

    async def test_unmatched_disease_has_no_associated_targets(self):
        with patch.object(ot,"_graphql",new_callable=AsyncMock,return_value={"search":{"hits":[]}}):
            result=await ot.disease_targets("unmapped condition")
        self.assertEqual(result["status"],"ok")
        self.assertEqual(result["records"],[])
        self.assertEqual(result["reason"],"No disease match returned.")

if __name__ == "__main__":
    unittest.main()
