import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend.main import app

class DiseaseToCombinationWorkflow(unittest.TestCase):
    def test_source_evidence_flows_from_target_ranking_to_experimental_pair(self):
        with patch('backend.services.opentargets_service.disease_targets',new_callable=AsyncMock,return_value={"status":"ok","source":"Open Targets","records":[{"gene_symbol":"GENE1","target_id":"ENSG000001","score":0.62,"source":"Open Targets","source_id":"EFO_X:ENSG000001","url":"https://platform.opentargets.org/disease/EFO_X/associations"}]}), patch('backend.services.chembl_service.drug_targets_for_genes',new_callable=AsyncMock,return_value={"status":"ok","source":"ChEMBL","records":[{"gene_symbol":"GENE1","drug_name":"Compound A","drug_id":"CHEMBL_A","activity_type":"IC50","activity_value":"25","units":"nM","assay_id":"CHEMBL_ASSAY","source":"ChEMBL","source_id":"1001","url":"https://www.ebi.ac.uk/chembl/compound_report_card/CHEMBL_A"}]}), patch('backend.services.pubmed_service.search',new_callable=AsyncMock,return_value={"status":"ok","source":"PubMed","records":[{"pmid":"12345","title":"Reported study"}]}):
            client=TestClient(app)
            discovery=client.post('/api/discovery/combined',json={"disease":"Example condition"})
        self.assertEqual(discovery.status_code,200)
        payload=discovery.json()
        self.assertEqual(payload['status'],'ok')
        candidate=payload['data']['candidates'][0]
        self.assertEqual(candidate['drug_id'],'CHEMBL_A')
        self.assertEqual(candidate['evidence'][0]['source_id'],'1001')
        record={"source":"DrugComb","source_id":"block-7","drug_a":"Compound A","drug_b":"Compound B","metric":"ZIP","score":7.5,"cell_line":"Cell X","concentration_a":0.2,"concentration_b":0.1,"concentration_unit":"uM","ratio":None,"study":"Study 2024"}
        with patch('backend.services.drugcomb_service.search_combinations',new_callable=AsyncMock,return_value={"status":"ok","records":[record]}):
            pair=client.post('/api/combinations/analyze',json={"drug_a":"Compound A","drug_b":"Compound B"}).json()
        self.assertEqual(pair['status'],'evidence_found')
        self.assertEqual(pair['evidence'][0]['cell_line'],'Cell X')
        self.assertEqual(pair['evidence'][0]['source_id'],'block-7')
        self.assertEqual(pair['ratio_analysis']['observations'][0]['derived_ratio']['a_to_b'],2)
        self.assertIsNone(pair['ratio_analysis']['clinical_dosing_guidance'])

if __name__=='__main__': unittest.main()
