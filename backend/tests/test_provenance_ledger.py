import hashlib
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.provenance_ledger import (
    build_evidence_ledger,
    make_source_check,
    source_checks_snapshot,
)


class ProvenanceLedgerTests(unittest.TestCase):
    def test_ledger_hash_and_source_identity_are_deterministic(self):
        raw = {"activity_id": 15, "value": 3.2}
        record = {
            "source": "ChEMBL",
            "source_id": "15",
            "url": "https://example.org/15",
            "source_record": raw,
            "raw_display_permitted": True,
            "retrieved_at": "2025-01-02T03:04:05Z",
        }
        ledger = build_evidence_ledger({"evidence": [record]})
        expected_hash = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(len(ledger), 1)
        item = ledger[0]
        self.assertEqual(item["record_id"], "ChEMBL:15")
        self.assertEqual(item["content_hash"], f"sha256:{expected_hash}")
        self.assertEqual(item["retrieved_at"], "2025-01-02T03:04:05Z")
        self.assertEqual(item["raw_json"], raw)
        self.assertTrue(item["raw_display_permitted"])
        self.assertIsNone(item["http_status"])
        self.assertIsNone(item["license"])

    def test_raw_payload_is_not_exposed_without_explicit_display_permission(self):
        ledger = build_evidence_ledger({"records": [{
            "source": "DrugComb", "source_id": "b1", "source_record": {"ZIP": 9},
        }]})
        self.assertIsNone(ledger[0]["raw_json"])
        self.assertFalse(ledger[0]["raw_display_permitted"])
        self.assertEqual(ledger[0]["raw_data_status"], "not_displayed_permission_unconfirmed")
        self.assertNotIn("source_record", ledger[0]["normalized_record"])

    def test_no_source_payload_or_metadata_is_fabricated(self):
        ledger = build_evidence_ledger({"records": [{"source": "PubMed", "pmid": "123"}]})
        self.assertEqual(len(ledger), 1)
        self.assertIsNone(ledger[0]["raw_json"])
        self.assertIsNone(ledger[0]["http_status"])
        self.assertIsNone(ledger[0]["license"])
        self.assertTrue(ledger[0]["retrieved_at"])
        self.assertTrue(ledger[0]["content_hash"].startswith("sha256:"))

    def test_cached_envelope_retrieval_time_is_inherited_without_replacement(self):
        ledger = build_evidence_ledger({"sources": {"PubChem": {
            "status": "ok", "retrieved_at": "2020-01-02T03:04:05Z",
            "records": [{"CID": 42, "MolecularFormula": "C2H6O"}],
        }}})
        self.assertEqual(ledger[0]["retrieved_at"], "2020-01-02T03:04:05Z")
        self.assertEqual(ledger[0]["source"], "PubChem")

    def test_identical_records_are_deduplicated_and_conflicts_remain_distinct(self):
        result = build_evidence_ledger({"records": [
            {"source": "ChEMBL", "source_id": "A1", "activity_value": 10},
            {"source": "ChEMBL", "source_id": "A1", "activity_value": 10},
            {"source": "ChEMBL", "source_id": "A1", "activity_value": 20},
        ]})
        self.assertEqual(len(result), 2)
        self.assertNotEqual(result[0]["record_id"], result[1]["record_id"])

    def test_source_check_distinguishes_found_empty_failure_and_skip(self):
        found = make_source_check("ChEMBL", {"status": "ok", "records": [{"source_id": 1}]})
        empty = make_source_check("Open Targets", {"status": "ok", "records": []})
        unavailable = make_source_check("PubChem", {"status": "unavailable", "error": "connection timed out", "records": []})
        no_match = make_source_check("PubChem", {"status": "not_found", "query": "not a compound", "records": []})
        skipped = make_source_check("DrugComb", {"status": "not_run", "reason": "No resolved candidate."})
        self.assertEqual(found["state"], "CHECKED_FOUND")
        self.assertEqual(found["record_count"], 1)
        self.assertEqual(empty["state"], "CHECKED_EMPTY")
        self.assertEqual(unavailable["state"], "NOT_CHECKED")
        self.assertEqual(unavailable["reason"], "connection timed out")
        self.assertEqual(no_match["state"], "CHECKED_EMPTY")
        self.assertEqual(skipped["state"], "SKIPPED")
        self.assertIn("No resolved candidate", skipped["reason"])

    def test_partial_with_rows_exposes_failure_detail_as_found(self):
        check = make_source_check("ChEMBL", {"status": "partial", "records": [{"id": 1}], "errors": ["timeout on target 2"]})
        self.assertEqual(check["state"], "CHECKED_FOUND")
        self.assertIn("timeout on target 2", check["reason"])


class ProvenanceRouteTests(unittest.TestCase):
    def test_disease_route_returns_ledger_and_health_exposes_latest_source_check(self):
        source = {"status": "ok", "source": "Open Targets", "query": "condition", "records": [
            {"source": "Open Targets", "source_id": "EFO_X:ENSG1", "gene_symbol": "GENE1", "url": "https://example.org/target", "retrieved_at": "2024-03-04T00:00:00Z"}
        ]}
        with patch("backend.services.opentargets_service.search_diseases", new_callable=AsyncMock, return_value=source):
            response = TestClient(app).get("/api/diseases/search?q=condition")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_checks"]["Open Targets"]["state"], "CHECKED_FOUND")
        self.assertEqual(payload["evidence_ledger"][0]["source_id"], "EFO_X:ENSG1")
        self.assertEqual(payload["evidence_ledger"][0]["retrieved_at"], "2024-03-04T00:00:00Z")
        health = TestClient(app).get("/health").json()
        self.assertEqual(health["source_checks"]["Open Targets"]["state"], "CHECKED_FOUND")

    def test_drug_search_ledger_inherits_provider_names_for_source_rows(self):
        pubchem = {"status": "ok", "records": [{"CID": 42, "MolecularFormula": "C2H6O"}]}
        chembl = {"status": "ok", "records": [{"molecule_chembl_id": "CHEMBL1", "molecule_pref_name": "Example"}]}
        with patch("backend.services.pubchem_service.search_drug", new_callable=AsyncMock, return_value=pubchem), patch(
            "backend.services.chembl_service.search_drug", new_callable=AsyncMock, return_value=chembl
        ):
            response = TestClient(app).get("/api/drugs/search?q=example")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        by_id = {entry["source_id"]: entry for entry in payload["evidence_ledger"]}
        self.assertEqual(by_id["42"]["source"], "PubChem")
        self.assertEqual(by_id["CHEMBL1"]["source"], "ChEMBL")
        self.assertEqual(payload["source_checks"]["PubChem"]["state"], "CHECKED_FOUND")
        self.assertEqual(payload["source_checks"]["ChEMBL"]["state"], "CHECKED_FOUND")

    def test_combo_endpoint_exposes_heatmap_and_safety_source_check_stays_unknown(self):
        with patch("backend.services.drugcomb_service.search_combinations", new_callable=AsyncMock,
                   return_value={"status": "unavailable", "records": [], "error": "contract unavailable"}):
            combo = TestClient(app).post("/api/combinations/analyze", json={"drug_a": "A", "drug_b": "B"})
        self.assertEqual(combo.status_code, 200)
        self.assertEqual(combo.json()["synergy_heatmap"]["status"], "unavailable")
        self.assertEqual(combo.json()["source_checks"]["DrugComb"]["state"], "NOT_CHECKED")
        with patch("backend.services.drugbank_service.interaction_lookup", return_value={
            "status": "unavailable", "source": "DrugBank", "records": [], "error": "not configured"
        }):
            safety = TestClient(app).post("/api/safety/evaluate", json={"drug_a": "A", "drug_b": "B"})
        payload = safety.json()
        self.assertEqual(payload["ddi_risk_level"], "UNKNOWN")
        self.assertEqual(payload["decision"], "REVIEW")
        self.assertEqual(payload["ddi_source_check"]["state"], "NOT_CHECKED")
        self.assertIn("not configured", payload["ddi_source_check"]["reason"])

    def test_claim_verification_route_rejects_unledgered_fake_pmid(self):
        response = TestClient(app).post("/api/ai/verify-claims", json={
            "claims": [{"claim_text": "Fake paper reports an effect.",
                        "citation": {"source": "PubMed", "record_id": "PMID:FAKE-DEMO"},
                        "claim_tag": "sourced", "details": {}}],
            "evidence_ledger": [],
        })
        self.assertEqual(response.status_code, 200)
        claim = response.json()["data"]["results"][0]
        self.assertEqual(claim["status"], "UNVERIFIABLE")
        self.assertEqual(claim["reason_code"], "record_id_not_in_ledger")


if __name__ == "__main__":
    unittest.main()
