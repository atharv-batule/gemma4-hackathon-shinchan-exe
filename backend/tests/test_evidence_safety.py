import unittest
from unittest.mock import patch
from backend.engines.combination_engine import analyze_combination
from backend.engines.safety_engine import evaluate_safety
from backend.engines.target_analysis import rank_candidates
from backend.services.rdkit_service import validate_smiles
import backend.services.rdkit_service as rdkit_service

class EvidenceSafetyTests(unittest.TestCase):
    def test_missing_combination_is_not_negative_result(self):
        r=analyze_combination("A","B",{"status":"unavailable","records":[]})
        self.assertEqual(r["status"],"unavailable")
        self.assertIsNone(r["synergy_conclusion"])
    def test_no_ddi_data_is_unknown_review(self):
        r=evaluate_safety("A","B")
        self.assertEqual(r["ddi_risk_level"],"UNKNOWN")
        self.assertEqual(r["decision"],"REVIEW")
    def test_no_candidate_without_drug_evidence(self):
        self.assertEqual(rank_candidates([{"gene_symbol":"TP53","drug_target_records":[]}]),[])
    def test_rdkit_unavailable_values_are_explicit(self):
        r=validate_smiles("CCO")
        if r["status"] == "unavailable": self.assertIsNone(r["properties"])
    def test_blank_smiles_is_rejected_without_rdkit(self):
        with patch.object(rdkit_service,"_AVAILABLE",False):
            r=validate_smiles("   ")
        self.assertEqual(r["status"],"invalid_request")
        self.assertFalse(r["valid"])
        self.assertIsNone(r["properties"])
    def test_rdkit_missing_never_returns_synthetic_properties(self):
        with patch.object(rdkit_service,"_AVAILABLE",False):
            r=validate_smiles("CCO")
        self.assertEqual(r["status"],"unavailable")
        self.assertIsNone(r["valid"])
        self.assertIsNone(r["properties"])

if __name__ == "__main__": unittest.main()
