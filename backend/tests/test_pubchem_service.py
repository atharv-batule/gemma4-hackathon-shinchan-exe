import unittest
import httpx
from unittest.mock import AsyncMock, patch
from backend.services.pubchem_service import search_drug, compound_properties

class PubChemServiceTests(unittest.IsolatedAsyncioTestCase):
    @patch("backend.services.pubchem_service.get_json", new_callable=AsyncMock)
    async def test_search_resolves_ids_then_fetches_source_properties(self, get_json):
        get_json.side_effect = [
            {"IdentifierList": {"CID": [101, 102]}},
            {"PropertyTable": {"Properties": [{"CID": 101, "MolecularWeight": 123.4, "IsomericSMILES": "CCO"}]}}
        ]
        result = await search_drug("compound/name & salt")
        self.assertEqual(get_json.await_args_list[0].args[0].split("/compound/name/")[1].split("/")[0], "compound%2Fname%20%26%20salt")
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["ambiguous"])
        self.assertEqual(result["resolved_cids"], [101, 102])
        self.assertEqual(result["records"][0]["MolecularWeight"], 123.4)
        self.assertEqual(result["properties_missing_for_cids"], [102])

    @patch("backend.services.pubchem_service.get_json", new_callable=AsyncMock)
    async def test_no_match_is_not_reported_as_unavailable_or_empty_success(self, get_json):
        get_json.return_value = {"IdentifierList": {"CID": []}}
        result = await search_drug("unknown query")
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["records"], [])
        self.assertFalse(result["ambiguous"])
        get_json.assert_awaited_once()

    @patch("backend.services.pubchem_service.get_json", new_callable=AsyncMock)
    async def test_missing_property_stays_missing(self, get_json):
        get_json.return_value = {"PropertyTable": {"Properties": [{"CID": 2244, "MolecularFormula": "C9H8O4"}]}}
        result = await compound_properties(2244)
        self.assertEqual(result["records"][0]["MolecularFormula"], "C9H8O4")
        self.assertNotIn("MolecularWeight", result["records"][0])

    async def test_empty_query_rejected_without_network(self):
        result = await search_drug("  ")
        self.assertEqual(result["status"], "invalid_query")

    @patch("backend.services.pubchem_service.get_json", new_callable=AsyncMock)
    async def test_malformed_identifier_envelope_is_unavailable(self, get_json):
        get_json.return_value = {"IdentifierList": {"CID": "2244"}}
        result = await search_drug("aspirin")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])

    @patch("backend.services.pubchem_service.get_json", new_callable=AsyncMock)
    async def test_invalid_cid_is_not_silently_dropped(self, get_json):
        get_json.return_value = {"IdentifierList": {"CID": [2244, "bad"]}}
        result = await search_drug("aspirin")
        self.assertEqual(result["status"], "unavailable")

    @patch("backend.services.pubchem_service.get_json", new_callable=AsyncMock)
    async def test_property_timeout_is_reported_as_unavailable(self, get_json):
        get_json.side_effect = [{"IdentifierList": {"CID": [2244]}}, httpx.TimeoutException("timed out")]
        result = await search_drug("aspirin")
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("timed out", result["error"])

    @patch("backend.services.pubchem_service.get_json", new_callable=AsyncMock)
    async def test_malformed_property_schema_is_unavailable(self, get_json):
        get_json.side_effect = [{"IdentifierList": {"CID": [2244]}}, {"PropertyTable": {"Properties": {}}}]
        result = await search_drug("aspirin")
        self.assertEqual(result["status"], "unavailable")

    def test_uses_current_documented_smiles_property_names(self):
        from backend.services.pubchem_service import PROPERTY_NAMES
        self.assertIn("ConnectivitySMILES", PROPERTY_NAMES)
        self.assertIn("SMILES", PROPERTY_NAMES)
        self.assertNotIn("CanonicalSMILES", PROPERTY_NAMES)
        self.assertNotIn("IsomericSMILES", PROPERTY_NAMES)

if __name__ == "__main__":
    unittest.main()
