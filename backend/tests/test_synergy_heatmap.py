import unittest

from backend.engines.synergy_heatmap import METRICS, build_synergy_heatmap


class SynergyHeatmapTests(unittest.TestCase):
    def test_empty_and_unavailable_are_distinct_from_additive(self):
        empty = build_synergy_heatmap([], source_status="ok")
        unavailable = build_synergy_heatmap([], source_status="unavailable")
        self.assertEqual(empty["status"], "empty")
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(empty["cells"], [])
        self.assertIn("does not mean additive", empty["legend"]["NO_DATA"])

    def test_cells_cover_all_four_metrics_and_preserve_observed_score(self):
        records = [
            {"cell_line": "A549", "metric": metric, "score": score, "source_id": f"id-{index}",
             "study": "Study 1", "assay": "dose matrix", "concentration_a": 1,
             "concentration_b": 2, "concentration_unit": "uM"}
            for index, (metric, score) in enumerate(zip(METRICS, (1.1, 2.2, 3.3, 4.4)))
        ]
        result = build_synergy_heatmap(records)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["metrics"], ["ZIP", "Bliss", "Loewe", "HSA"])
        self.assertEqual(len(result["cells"]), 4)
        self.assertEqual([cell["scores"][0]["score"] for cell in result["cells"]], [1.1, 2.2, 3.3, 4.4])
        self.assertTrue(all(cell["observation_count"] == 1 for cell in result["cells"]))

    def test_missing_cell_line_is_not_discarded_or_filled_in(self):
        result = build_synergy_heatmap([{"metric": "ZIP", "score": 2.0}])
        self.assertEqual(result["cell_lines"], [None])
        self.assertIsNone(result["cells"][0]["cell_line"])
        self.assertFalse(result["cells"][0]["context_metadata_complete"])
        self.assertIn("cannot be assessed", result["cells"][0]["warning"])

    def test_explicit_opposing_interpretations_in_same_complete_context_warn(self):
        context = {"cell_line": "A549", "metric": "ZIP", "study": "S1", "assay": "matrix",
                   "concentration_a": 1, "concentration_b": 2, "concentration_unit": "uM"}
        result = build_synergy_heatmap([
            {**context, "score": 4, "source_id": "r1", "reported_interpretation": "synergistic"},
            {**context, "score": -1, "source_id": "r2", "reported_interpretation": "antagonistic"},
        ])
        cell = result["cells"][0]
        self.assertTrue(cell["context_dependent"])
        self.assertIn("Conflicting source-reported interpretations", cell["warning"])
        self.assertEqual(cell["observation_count"], 2)
        self.assertEqual({item["source_id"] for item in cell["scores"]}, {"r1", "r2"})

    def test_disagreement_across_distinct_contexts_is_not_pooled(self):
        common = {"cell_line": "A549", "metric": "ZIP", "assay": "matrix", "concentration_a": 1,
                  "concentration_b": 2, "concentration_unit": "uM"}
        result = build_synergy_heatmap([
            {**common, "study": "S1", "reported_interpretation": "synergistic", "score": 4},
            {**common, "study": "S2", "reported_interpretation": "antagonistic", "score": -1},
        ])
        cell = result["cells"][0]
        self.assertTrue(cell["context_dependent"])
        self.assertIn("distinct experimental contexts", cell["warning"])
        self.assertEqual(len(cell["contexts"]), 2)
        self.assertEqual(len(cell["scores"]), 2)

    def test_numeric_difference_without_source_interpretation_is_not_a_contradiction(self):
        base = {"cell_line": "A549", "metric": "ZIP", "study": "S1", "assay": "matrix",
                "concentration_a": 1, "concentration_b": 2, "concentration_unit": "uM"}
        cell = build_synergy_heatmap([{**base, "score": 99}, {**base, "score": -50}])["cells"][0]
        self.assertFalse(cell["context_dependent"])
        self.assertIsNone(cell["warning"])
        self.assertEqual(len(cell["scores"]), 2)

    def test_heatmap_status_values_available_empty_unavailable(self):
        available_res = build_synergy_heatmap([{"cell_line": "MCF7", "metric": "ZIP", "score": 3.0}], source_status="available")
        self.assertEqual(available_res["status"], "available")
        empty_res = build_synergy_heatmap([], source_status="available")
        self.assertEqual(empty_res["status"], "empty")
        unavailable_res = build_synergy_heatmap([], source_status="unavailable")
        self.assertEqual(unavailable_res["status"], "unavailable")

    def test_diverging_metrics_and_multiple_experiments_per_cell(self):
        records = [
            {"cell_line": "A549", "metric": "ZIP", "score": 12.0, "reported_interpretation": "synergistic"},
            {"cell_line": "A549", "metric": "Bliss", "score": -5.0, "reported_interpretation": "antagonistic"},
            {"cell_line": "A549", "metric": "Loewe", "score": 0.0, "reported_interpretation": "neutral"},
            # HSA missing for A549 -> must be NO_DATA
        ]
        result = build_synergy_heatmap(records, source_status="available")
        hsa_cell = next(c for c in result["cells"] if c["cell_line"] == "A549" and c["metric"] == "HSA")
        self.assertEqual(hsa_cell["state"], "NO_DATA")
        self.assertEqual(hsa_cell["observation_count"], 0)


if __name__ == "__main__":
    unittest.main()
