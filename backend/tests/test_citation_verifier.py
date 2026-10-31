import unittest

from backend.ai.citation_verifier import (
    ID_ONLY,
    MISMATCH,
    UNVERIFIABLE,
    VERIFIED,
    NumericTolerance,
    verify_claims,
)


class ClaimCitationVerifierTests(unittest.TestCase):
    def setUp(self):
        self.ledger = [{
            "record_id": "ledger-1",
            "source": "DrugComb",
            "source_id": "block-17",
            "url": "https://example.invalid/block-17",
            "retrieved_at": "2026-10-31T10:00:00Z",
            "raw_json": {
                "drug_a": "Drug A", "drug_b": "Drug B", "ZIP": 7.2,
                "metric": "ZIP", "cell_line": "A549", "conc_row": 0.5,
                "conc_col": 1.0, "unit": "uM", "study": "Study X",
                "assay": "dose matrix",
            },
        }]

    def _claim(self, *, source="DrugComb", record_id="ledger-1", tag="sourced", details=None):
        citation = None if source is None else {"source": source, "record_id": record_id}
        return {"claim_text": "Drug A and Drug B had a reported ZIP score.",
                "citation": citation, "claim_tag": tag, "details": details or {}}

    def test_all_structured_fields_and_numeric_tolerance_verify(self):
        claim = self._claim(details={
            "drug_names": ["Drug A", "Drug B"], "metric": "zip",
            "cell_line": "a549", "units": "UM", "experimental_context": "dose matrix",
            "values": {"ZIP": 7.2005, "conc_row": 0.5},
        })
        result = verify_claims([claim], self.ledger,
                               tolerance=NumericTolerance(absolute=0.001, relative=0))
        self.assertEqual(result["results"][0]["status"], VERIFIED)

    def test_numeric_conflict_is_mismatch(self):
        claim = self._claim(details={"metric": "ZIP", "values": {"ZIP": 9.0}})
        result = verify_claims([claim], self.ledger)
        self.assertEqual(result["results"][0]["status"], MISMATCH)

    def test_conflicting_pair_unit_and_cell_line_are_mismatch(self):
        claim = self._claim(details={"drug_names": ["Drug C"], "units": "mg", "cell_line": "MCF7"})
        result = verify_claims([claim], self.ledger)
        self.assertEqual(result["results"][0]["status"], MISMATCH)

    def test_id_only_when_record_exists_but_details_are_absent_or_unavailable(self):
        no_detail_claim = self._claim()
        unavailable_detail_claim = self._claim(details={"toxicity": "none"})
        results = verify_claims([no_detail_claim, unavailable_detail_claim], self.ledger)["results"]
        self.assertEqual([row["status"] for row in results], [ID_ONLY, ID_ONLY])

    def test_missing_record_is_unverifiable_with_reason(self):
        result = verify_claims([self._claim(record_id="unknown")], self.ledger)
        self.assertEqual(result["results"][0]["status"], UNVERIFIABLE)
        self.assertEqual(result["results"][0]["reason_code"], "record_id_not_in_ledger")

    def test_existing_id_with_wrong_source_is_unverifiable_with_reason(self):
        result = verify_claims([self._claim(source="PubMed")], self.ledger)
        self.assertEqual(result["results"][0]["status"], UNVERIFIABLE)
        self.assertEqual(result["results"][0]["reason_code"], "citation_source_mismatch")

    def test_uncited_sourced_claim_is_flagged(self):
        claim = self._claim(source=None)
        result = verify_claims([claim], self.ledger)["results"][0]
        self.assertEqual(result["status"], UNVERIFIABLE)
        self.assertTrue(result["uncited_claim"])
        self.assertEqual(result["reason_code"], "citation_missing")

    def test_inferred_and_unknown_claims_are_not_flagged_as_uncited(self):
        result = verify_claims([
            self._claim(source=None, tag="inferred"),
            self._claim(source=None, tag="unknown"),
        ], self.ledger)["results"]
        self.assertEqual([row["status"] for row in result], [UNVERIFIABLE, UNVERIFIABLE])
        self.assertFalse(any(row["uncited_claim"] for row in result))

    def test_fake_pmid_fixture_is_rejected_when_absent_from_ledger(self):
        # Deliberately fake test fixture; it is not a PubMed record or citation.
        claim = self._claim(source="PubMed", record_id="PMID:FAKE-TEST-0001")
        result = verify_claims([claim], self.ledger)["results"][0]
        self.assertEqual(result["status"], UNVERIFIABLE)
        self.assertEqual(result["reason_code"], "record_id_not_in_ledger")

    def test_details_are_checked_against_normalized_record_when_raw_not_permitted(self):
        ledger_record = {"record_id": "ledger-2", "source": "DrugComb",
                         "raw_json": None,
                         "normalized_record": {"drug_a": "Drug A", "drug_b": "Drug B",
                                               "metric": "ZIP", "ZIP": 7.2, "cell_line": "A549",
                                               "unit": "uM", "study": "Study X", "assay": "dose matrix"}}
        claim = self._claim(record_id="ledger-2", details={
            "drug_names": ["Drug A", "Drug B"], "metric": "ZIP",
            "cell_line": "A549", "units": "uM", "values": {"ZIP": 7.2},
        })
        result = verify_claims([claim], [ledger_record])["results"][0]
        self.assertEqual(result["status"], VERIFIED)


if __name__ == "__main__":
    unittest.main()
