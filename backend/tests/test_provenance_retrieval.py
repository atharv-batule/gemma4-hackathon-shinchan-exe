import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.engines.combination_engine import analyze_combination
from backend.main import app
from backend.services.provenance_ledger import (
    annotate_heatmap_provenance,
    build_evidence_ledger,
)


def _combo_record(source_id: str, *, score: float = 2.0, **overrides):
    row = {
        "source": "DrugComb", "source_id": source_id,
        "drug_a": "A", "drug_b": "B", "metric": "ZIP", "score": score,
        "cell_line": "A549", "study": "Study 1", "assay": "dose matrix",
        "concentration_a": 1.0, "concentration_b": 2.0, "concentration_unit": "uM",
    }
    row.update(overrides)
    return row


class HeatmapProvenanceMatchingTests(unittest.TestCase):
    def test_heatmap_cell_click_maps_to_its_exact_ledger_record(self):
        rows = [_combo_record("row-1", score=2.0), _combo_record("row-2", score=5.0, concentration_b=4.0)]
        with patch("backend.services.drugcomb_service.search_combinations", new_callable=AsyncMock,
                   return_value={"status": "ok", "source": "DrugComb", "records": rows}):
            payload = TestClient(app).post("/api/combinations/analyze",
                                           json={"drug_a": "A", "drug_b": "B"}).json()
        ledger_ids = {item["record_id"] for item in payload["evidence_ledger"]}
        self.assertEqual(ledger_ids, {"DrugComb:row-1", "DrugComb:row-2"})
        cell = next(item for item in payload["synergy_heatmap"]["cells"] if item["metric"] == "ZIP")
        self.assertEqual(cell["cell_line"], "A549")
        scores = {item["score"]: item for item in cell["scores"]}
        by_record = {item["record_id"]: item for item in cell["scores"]}
        self.assertEqual(by_record["DrugComb:row-1"]["score"], 2.0)
        self.assertEqual(by_record["DrugComb:row-2"]["score"], 5.0)
        for item in cell["scores"]:
            self.assertEqual(item["provenance_state"], "AVAILABLE")
            self.assertEqual(item["provenance_reason"], "Matched to exactly one ledger record by source and source ID.")
        detail = TestClient(app).get("/api/provenance/records/DrugComb:row-2")
        self.assertEqual(detail.status_code, 200)
        record = detail.json()["record"]
        self.assertEqual(record["source_id"], "row-2")
        self.assertEqual(record["normalized_record"]["score"], 5.0)
        self.assertEqual(record["normalized_record"]["concentration_b"], 4.0)
        self.assertNotEqual(scores[5.0]["record_id"], "DrugComb:row-1")

    def test_heatmap_cell_without_source_id_is_unavailable(self):
        rows = [_combo_record("ignored")]
        rows[0].pop("source_id")
        with patch("backend.services.drugcomb_service.search_combinations", new_callable=AsyncMock,
                   return_value={"status": "ok", "source": "DrugComb", "records": rows}):
            payload = TestClient(app).post("/api/combinations/analyze",
                                           json={"drug_a": "A", "drug_b": "B"}).json()
        score = payload["synergy_heatmap"]["cells"][0]["scores"][0]
        self.assertIsNone(score["record_id"])
        self.assertEqual(score["provenance_state"], "UNAVAILABLE")
        self.assertIn("source identifier", score["provenance_reason"])

    def test_heatmap_cell_without_matching_record_is_unavailable(self):
        heatmap = {"cells": [{"metric": "ZIP", "cell_line": "A549", "scores": [
            {"source": "DrugComb", "source_id": "unknown-row", "score": 1.0},
        ]}]}
        annotate_heatmap_provenance(heatmap, build_evidence_ledger({"records": [_combo_record("row-1")]}))
        score = heatmap["cells"][0]["scores"][0]
        self.assertIsNone(score["record_id"])
        self.assertEqual(score["provenance_state"], "UNAVAILABLE")
        self.assertIn("No ledger record matches", score["provenance_reason"])

    def test_heatmap_observation_without_source_label_is_unavailable(self):
        heatmap = {"cells": [{"metric": "ZIP", "scores": [{"source_id": "row-1", "score": 1.0}]}]}
        annotate_heatmap_provenance(heatmap, build_evidence_ledger({"records": [_combo_record("row-1")]}))
        score = heatmap["cells"][0]["scores"][0]
        self.assertIsNone(score["record_id"])
        self.assertEqual(score["provenance_state"], "UNAVAILABLE")
        self.assertIn("no source label", score["provenance_reason"])

    def test_ambiguous_source_id_does_not_select_a_record(self):
        ledger = [
            {"record_id": "DrugComb:x", "source": "DrugComb", "source_id": "x"},
            {"record_id": "DrugComb:x@abcdef123456", "source": "DrugComb", "source_id": "x"},
        ]
        heatmap = {"cells": [{"scores": [{"source": "DrugComb", "source_id": "x", "score": 1.0}]}]}
        annotate_heatmap_provenance(heatmap, ledger)
        score = heatmap["cells"][0]["scores"][0]
        self.assertIsNone(score["record_id"])
        self.assertEqual(score["provenance_state"], "AMBIGUOUS")
        self.assertIn("no record was selected automatically", score["provenance_reason"])

    def test_missing_record_id_falls_back_only_to_exact_source_and_source_id(self):
        ledger = build_evidence_ledger({"records": [_combo_record("row-1"), _combo_record("row-2")]})
        heatmap = {"cells": [{"scores": [{"source": "DrugComb", "source_id": "row-2", "score": 5.0}]}]}
        annotate_heatmap_provenance(heatmap, ledger)
        score = heatmap["cells"][0]["scores"][0]
        self.assertEqual(score["record_id"], "DrugComb:row-2")
        self.assertEqual(score["provenance_state"], "AVAILABLE")


class ProvenanceRetrievalTests(unittest.TestCase):
    def test_individual_record_is_retrieved_by_exact_record_id(self):
        ledger = build_evidence_ledger({"records": [{
            "source": "ChEMBL", "source_id": "retrieval-1", "activity_value": 7,
            "retrieved_at": "2024-01-01T00:00:00Z",
        }]})
        response = TestClient(app).get(f"/api/provenance/records/{ledger[0]['record_id']}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "found")
        self.assertEqual(payload["record"]["record_id"], "ChEMBL:retrieval-1")
        self.assertEqual(payload["record"]["source_id"], "retrieval-1")
        self.assertEqual(payload["record"]["retrieved_at"], "2024-01-01T00:00:00Z")

    def test_unknown_record_id_returns_not_found_without_ledger_fallback(self):
        response = TestClient(app).get("/api/provenance/records/ChEMBL:does-not-exist")
        self.assertEqual(response.status_code, 404)
        payload = response.json()
        self.assertEqual(payload["status"], "not_found")
        self.assertIsNone(payload["record"])
        self.assertEqual(payload["records"], [])

    def test_invalid_record_id_is_rejected(self):
        response = TestClient(app).get("/api/provenance/records/" + "x" * 600)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "invalid_record_id")

    def test_query_requires_at_least_one_exact_filter(self):
        response = TestClient(app).get("/api/provenance/records")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["status"], "invalid_request")

    def test_records_are_retrievable_by_source_and_experiment(self):
        build_evidence_ledger({"records": [{
            "source": "DrugComb", "source_id": "exp-row-1", "experiment_id": "EXP-9",
            "score": 1.0,
        }]})
        by_experiment = TestClient(app).get("/api/provenance/records?experiment_id=EXP-9")
        self.assertEqual(by_experiment.status_code, 200)
        self.assertEqual(by_experiment.json()["count"], 1)
        self.assertEqual(by_experiment.json()["records"][0]["source_id"], "exp-row-1")
        by_source = TestClient(app).get("/api/provenance/records?source=DrugComb&source_id=exp-row-1")
        self.assertEqual(by_source.status_code, 200)
        self.assertEqual(by_source.json()["status"], "found")
        missing = TestClient(app).get("/api/provenance/records?source=DrugComb&source_id=absent")
        self.assertEqual(missing.status_code, 404)

    def test_store_failure_is_reported_as_unavailable(self):
        with patch("backend.main.get_provenance_record", side_effect=RuntimeError("store offline")):
            response = TestClient(app).get("/api/provenance/records/ChEMBL:any")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertIsNone(response.json()["record"])

    def test_restricted_raw_record_stays_hidden_when_retrieved(self):
        ledger = build_evidence_ledger({"records": [{
            "source": "DrugComb", "source_id": "raw-restricted-1",
            "source_record": {"ZIP": 9}, "raw_display_permitted": False,
        }]})
        payload = TestClient(app).get(f"/api/provenance/records/{ledger[0]['record_id']}").json()
        record = payload["record"]
        self.assertIsNone(record["raw_json"])
        self.assertFalse(record["raw_display_permitted"])
        self.assertEqual(record["raw_data_status"], "not_displayed_permission_unconfirmed")


class ProvenanceMetadataTests(unittest.TestCase):
    def test_transformations_are_recorded_when_they_occur(self):
        combination = analyze_combination("A", "B", [{
            "source": "DrugComb", "source_id": "transform-1", "metric": "zip", "score": 1.0,
            "transformations": ["unit_conversion: adapter converted assay concentration from mM to uM"],
        }])
        ledger = build_evidence_ledger({"evidence": combination["evidence"]})
        transformations = ledger[0]["transformations"]
        self.assertTrue(any(item.startswith("unit_conversion:") for item in transformations))
        self.assertTrue(any("metric 'zip' -> 'ZIP'" in item for item in transformations))

    def test_identifier_canonicalisation_is_recorded_only_when_applied(self):
        ledger = build_evidence_ledger({"records": [{"source": "PubChem", "CID": 42}]})
        self.assertEqual(ledger[0]["source_id"], "42")
        self.assertTrue(any("identifier_canonicalisation" in item for item in ledger[0]["transformations"]))
        plain = build_evidence_ledger({"records": [{"source": "PubMed", "pmid": "T-1"}]})
        self.assertFalse(any("identifier_canonicalisation" in item for item in plain[0]["transformations"]))

    def test_http_status_and_licence_are_captured_when_supplied(self):
        ledger = build_evidence_ledger({"records": [{
            "source": "ChEMBL", "source_id": "meta-1", "http_status": 200,
            "license": "CC-BY-SA-4.0", "attribution": "ChEMBL / EMBL-EBI",
        }]})
        item = ledger[0]
        self.assertEqual(item["http_status"], 200)
        self.assertEqual(item["license"], "CC-BY-SA-4.0")
        self.assertEqual(item["attribution"], "ChEMBL / EMBL-EBI")
        self.assertEqual(item["metadata_status"]["http_status"], "PROVIDED")
        self.assertEqual(item["metadata_status"]["license"], "PROVIDED")
        self.assertEqual(item["metadata_status"]["attribution"], "PROVIDED")

    def test_missing_http_status_and_licence_remain_explicitly_missing(self):
        item = build_evidence_ledger({"records": [{"source": "PubMed", "pmid": "meta-2"}]})[0]
        self.assertIsNone(item["http_status"])
        self.assertIsNone(item["license"])
        self.assertEqual(item["metadata_status"]["http_status"], "UNKNOWN")
        self.assertEqual(item["metadata_status"]["license"], "NOT_PROVIDED")
        self.assertEqual(item["metadata_status"]["attribution"], "NOT_PROVIDED")

    def test_cached_retrieval_timestamp_is_preserved_and_marked_cached(self):
        ledger = build_evidence_ledger({"sources": {"PubChem": {
            "status": "ok", "cached": True, "retrieved_at": "2020-01-02T03:04:05Z",
            "http_status": 200, "records": [{"CID": 42}],
        }}})
        item = ledger[0]
        self.assertEqual(item["retrieved_at"], "2020-01-02T03:04:05Z")
        self.assertEqual(item["retrieved_at_origin"], "cached")
        self.assertEqual(item["retrieved_at_status"], "PROVIDED")
        self.assertEqual(item["http_status"], 200)

    def test_unreported_retrieval_time_is_not_presented_as_provider_time(self):
        item = build_evidence_ledger({"records": [{"source": "PubMed", "pmid": "meta-3"}]})[0]
        self.assertEqual(item["retrieved_at_status"], "UNKNOWN")
        self.assertEqual(item["retrieved_at_origin"], "unknown")
        self.assertEqual(item["metadata_status"]["retrieved_at"], "UNKNOWN")


class SafetyUnknownWithoutEvidenceTests(unittest.TestCase):
    def test_ddi_stays_unknown_when_interaction_evidence_was_not_checked(self):
        with patch("backend.services.drugbank_service.interaction_lookup", return_value={
            "status": "unavailable", "source": "DrugBank", "records": [],
            "error": "DrugBank interaction data requires authorized access and credentials; none are configured.",
        }):
            payload = TestClient(app).post("/api/safety/evaluate",
                                           json={"drug_a": "A", "drug_b": "B"}).json()
        self.assertEqual(payload["ddi_risk_level"], "UNKNOWN")
        self.assertEqual(payload["decision"], "REVIEW")
        self.assertEqual(payload["ddi_source_check"]["state"], "NOT_CHECKED")
        self.assertIn("none are configured", payload["ddi_source_check"]["reason"])
        self.assertIsNone(payload["clinical_safety_conclusion"])


if __name__ == "__main__":
    unittest.main()
