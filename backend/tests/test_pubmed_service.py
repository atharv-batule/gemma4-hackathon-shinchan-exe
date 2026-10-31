import unittest
from unittest.mock import AsyncMock, patch
import httpx

from backend.services import pubmed_service


class PubMedProviderTests(unittest.IsolatedAsyncioTestCase):
    @patch("backend.services.pubmed_service.get_json", new_callable=AsyncMock)
    async def test_search_preserves_pmid_and_validated_citation_url(self, get_json):
        get_json.side_effect = [
            {"esearchresult": {"idlist": ["12345", "67890"]}},
            {"result": {"uids": ["12345", "67890"], "12345": {"title": "Study", "pubdate": "2024"}}},
        ]
        result = await pubmed_service.search("condition", limit=500)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["records"][0]["pmid"], "12345")
        self.assertEqual(result["records"][0]["source_url"], "https://pubmed.ncbi.nlm.nih.gov/12345/")
        self.assertEqual(result["missing_pmids"], ["67890"])
        self.assertEqual(get_json.await_args_list[0].args[1]["retmax"], 100)

    @patch("backend.services.pubmed_service.get_json", new_callable=AsyncMock)
    async def test_malformed_search_schema_is_unavailable(self, get_json):
        get_json.return_value = {"esearchresult": {"idlist": "12345"}}
        result = await pubmed_service.search("condition")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])

    @patch("backend.services.pubmed_service.get_json", new_callable=AsyncMock)
    async def test_timeout_is_unavailable(self, get_json):
        get_json.side_effect = httpx.TimeoutException("timed out")
        result = await pubmed_service.search("condition")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])


if __name__ == "__main__":
    unittest.main()
