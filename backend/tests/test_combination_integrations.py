import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from backend.engines.combination_engine import analyze_combination
from backend.engines.ratio_analysis import compare_experimental_ratios
from backend.engines.ddi_engine import screen_interactions
from backend.engines.safety_engine import evaluate_safety
from backend.services.drugcomb_service import _normalize, search_combinations
from backend.services.drugbank_service import interaction_lookup


class CombinationContextTests(unittest.TestCase):
    def test_normalizes_only_reported_metrics_and_retains_raw_row(self):
        row = {
            "id": 44, "drug_row": "Compound X", "drug_col": "Compound Y",
            "cell_line": "A549", "conc_row": 0.5, "conc_col": 1.0,
            "unit": "uM", "ZIP": 8.2, "Bliss": None, "study": "Study 1",
        }
        records = _normalize(row)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["metric"], "ZIP")
        self.assertEqual(records[0]["score"], 8.2)
        self.assertEqual(records[0]["source_id"], 44)
        self.assertEqual(records[0]["source_record"], row)

    def test_combination_preserves_cell_line_and_experimental_context(self):
        row = {"id": "b1", "drug_row": "A", "drug_col": "B", "cell_line": "A549",
               "conc_row": 0.5, "conc_col": 1.0, "unit": "uM", "ZIP": 8.2}
        evidence = _normalize(row)
        result = analyze_combination("A", "B", evidence)
        self.assertEqual(result["evidence"][0]["cell_line"], "A549")
        self.assertEqual(result["evidence"][0]["concentration_a"], 0.5)
        self.assertEqual(result["evidence"][0]["concentration_b"], 1.0)
        self.assertEqual(result["evidence"][0]["score"], 8.2)
        self.assertEqual(result["ratio_analysis"]["observations"][0]["derived_ratio"]["a_to_b"], 0.5)
        self.assertIsNone(result["synergy_conclusion"])

    def test_ratio_comparison_keeps_incompatible_contexts_separate(self):
        result = compare_experimental_ratios([
            {"concentration_a": 1, "concentration_b": 1, "concentration_unit": "uM", "cell_line": "A549", "metric": "ZIP"},
            {"concentration_a": 1, "concentration_b": 1, "concentration_unit": "uM", "cell_line": "MCF7", "metric": "ZIP"},
        ])
        self.assertEqual(result["context_count"], 2)
        self.assertFalse(result["contexts_comparable"])
        self.assertEqual(len(result["observations"]), 2)

    def test_ratio_comparison_marks_missing_context_unknown(self):
        result = compare_experimental_ratios([{
            "concentration_a": 1, "concentration_b": 1,
            "concentration_unit": "uM", "metric": "ZIP",
        }])
        self.assertEqual(result["status"], "observed")
        self.assertFalse(result["context_metadata_complete"])
        self.assertFalse(result["contexts_comparable"])

    def test_ratio_contexts_keep_dose_rows_separate(self):
        result = compare_experimental_ratios([
            {"concentration_a": 1, "concentration_b": 1, "concentration_unit": "uM", "cell_line": "A549", "metric": "ZIP", "study": "S1", "assay": "screen"},
            {"concentration_a": 2, "concentration_b": 1, "concentration_unit": "uM", "cell_line": "A549", "metric": "ZIP", "study": "S1", "assay": "screen"},
        ])
        self.assertEqual(result["context_count"], 2)
        self.assertFalse(result["contexts_comparable"])

    def test_combination_excludes_explicitly_mismatched_pairs(self):
        result = analyze_combination("A", "B", [
            {"drug_a": "A", "drug_b": "B", "metric": "ZIP", "score": 2},
            {"drug_a": "A", "drug_b": "C", "metric": "ZIP", "score": 99},
        ])
        self.assertEqual(result["evidence_count"], 1)
        self.assertEqual(result["excluded_mismatched_pair_count"], 1)
        self.assertIsNone(result["synergy_conclusion"])

    def test_unknown_ddi_is_never_low(self):
        result = evaluate_safety("A", "B")
        self.assertEqual(result["ddi_risk_level"], "UNKNOWN")
        self.assertEqual(result["decision"], "REVIEW")
        self.assertTrue(result["missing_evidence"])

    def test_ddi_warning_without_severity_remains_unknown(self):
        result = screen_interactions("A", "B", [{"description": "source warning"}], source_status="available")
        self.assertEqual(result["ddi_risk_level"], "UNKNOWN")
        self.assertEqual(result["status"], "warnings_found_severity_unknown")

    def test_ddi_severity_uses_only_recognized_source_labels(self):
        self.assertEqual(screen_interactions("A", "B", [{"severity": "moderate"}])["ddi_risk_level"], "Moderate")
        self.assertEqual(screen_interactions("A", "B", [{"severity": "major"}])["ddi_risk_level"], "High")


class ServiceAvailabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_drugcomb_does_not_guess_parameter_names(self):
        with patch.dict(os.environ, {}, clear=True):
            result = await search_combinations("A", "B")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])

    async def test_drugcomb_rejects_blank_drug_ids_without_request(self):
        with patch("backend.services.drugcomb_service.httpx.AsyncClient") as client:
            result = await search_combinations("  ", "B")
        self.assertEqual(result["status"], "invalid_request")
        client.assert_not_called()

    async def test_drugcomb_configured_request_keeps_provider_rows(self):
        # The parameter names here are explicitly supplied configuration. This
        # test does not assert or imply that these are DrugComb's universal API
        # parameter names.
        response = MagicMock()
        response.json.return_value = [{
            "id": "block-1", "drug_row": "A", "drug_col": "B",
            "cell_line": "A549", "conc_row": 0.5, "conc_col": 1.0,
            "unit": "uM", "ZIP": 8.2,
        }]
        response.raise_for_status.return_value = None
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.get = AsyncMock(return_value=response)
        env = {
            "DRUGCOMB_DRUG_A_PARAM": "configured_a",
            "DRUGCOMB_DRUG_B_PARAM": "configured_b",
            "DRUGCOMB_CELL_LINE_PARAM": "configured_cell",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "backend.services.drugcomb_service.httpx.AsyncClient", return_value=client
        ):
            result = await search_combinations("A", "B", cell_line="A549")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["records"][0]["score"], 8.2)
        self.assertEqual(result["records"][0]["cell_line"], "A549")
        client.get.assert_awaited_once()
        args, kwargs = client.get.await_args
        self.assertEqual(args[0], "https://api.drugcomb.org/response/")
        self.assertEqual(kwargs["params"], {
            "configured_a": "A", "configured_b": "B", "configured_cell": "A549"
        })

    async def test_drugcomb_unrecognized_payload_is_unavailable(self):
        response = MagicMock()
        response.json.return_value = {"unexpected": "shape"}
        response.raise_for_status.return_value = None
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.get = AsyncMock(return_value=response)
        env = {"DRUGCOMB_DRUG_A_PARAM": "a", "DRUGCOMB_DRUG_B_PARAM": "b"}
        with patch.dict(os.environ, env, clear=True), patch(
            "backend.services.drugcomb_service.httpx.AsyncClient", return_value=client
        ):
            result = await search_combinations("A", "B")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])

    async def test_drugcomb_mixed_valid_and_invalid_rows_fails_closed(self):
        response = MagicMock()
        response.json.return_value = [{"id": "block-1"}, "not a record"]
        response.raise_for_status.return_value = None
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.get = AsyncMock(return_value=response)
        env = {"DRUGCOMB_DRUG_A_PARAM": "a", "DRUGCOMB_DRUG_B_PARAM": "b"}
        with patch.dict(os.environ, env, clear=True), patch(
            "backend.services.drugcomb_service.httpx.AsyncClient", return_value=client
        ):
            result = await search_combinations("A", "B")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])

    async def test_drugcomb_timeout_is_unavailable_without_evidence(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        env = {"DRUGCOMB_DRUG_A_PARAM": "a", "DRUGCOMB_DRUG_B_PARAM": "b"}
        with patch.dict(os.environ, env, clear=True), patch(
            "backend.services.drugcomb_service.httpx.AsyncClient", return_value=client
        ):
            result = await search_combinations("A", "B")
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["records"], [])

    def test_drugbank_reports_authorization_state_without_exposing_key(self):
        with patch.dict(os.environ, {"DRUGBANK_API_KEY": "secret"}, clear=True):
            result = interaction_lookup("A", "B")
        self.assertEqual(result["status"], "unavailable")
        self.assertTrue(result["credential_configured"])
        self.assertNotIn("secret", str(result))


if __name__ == "__main__":
    unittest.main()
