import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend.main import app

class EndpointSmokeTests(unittest.TestCase):
    def setUp(self): self.client=TestClient(app)
    def test_health(self): self.assertEqual(self.client.get('/health').status_code,200)
    @patch('backend.services.opentargets_service.search_diseases',new_callable=AsyncMock,return_value={'status':'ok','source':'Open Targets','query':'condition','records':[{'disease_id':'EFO_0000408','disease_name':'condition','entity':'disease','url':'https://platform.opentargets.org/disease/EFO_0000408'}]})
    def test_disease_search(self,search):
        response=self.client.get('/api/diseases/search?q=condition')
        self.assertEqual(response.status_code,200)
        payload=response.json()
        self.assertEqual(payload['source'],'Open Targets')
        self.assertEqual(payload['records'][0]['disease_id'],'EFO_0000408')
        self.assertIn('pipeline_latency_ms',payload)
        search.assert_awaited_once_with('condition')
    @patch('backend.services.pubchem_service.search_drug',new_callable=AsyncMock,return_value={'status':'ok','records':[]})
    @patch('backend.services.chembl_service.search_drug',new_callable=AsyncMock,return_value={'status':'ok','records':[]})
    def test_drug_search(self,*_): self.assertEqual(self.client.get('/api/drugs/search?q=drug').status_code,200)
    @patch('backend.services.opentargets_service.disease_targets',new_callable=AsyncMock,return_value={'status':'ok','records':[]})
    @patch('backend.services.chembl_service.drug_targets_for_genes',new_callable=AsyncMock,return_value={'status':'ok','records':[]})
    @patch('backend.services.pubmed_service.search',new_callable=AsyncMock,return_value={'status':'ok','records':[]})
    def test_repurposing(self,*_): self.assertIn('data',self.client.post('/api/repurposing/analyze',json={'disease':'condition'}).json())
    @patch('backend.services.drugcomb_service.search_combinations',new_callable=AsyncMock,return_value={'status':'unavailable','records':[]})
    def test_combinations(self,_): self.assertEqual(self.client.post('/api/combinations/analyze',json={'drug_a':'A','drug_b':'B'}).json()['status'],'unavailable')
    def test_safety_unknown(self): self.assertEqual(self.client.post('/api/safety/evaluate',json={'drug_a':'A','drug_b':'B'}).json()['ddi_risk_level'],'UNKNOWN')
    def test_molecular_endpoint(self): self.assertEqual(self.client.post('/api/molecular/validate',json={'smiles':'CCO'}).status_code,200)
    @patch('backend.services.opentargets_service.disease_targets',new_callable=AsyncMock,return_value={'status':'ok','records':[]})
    @patch('backend.services.chembl_service.drug_targets_for_genes',new_callable=AsyncMock,return_value={'status':'ok','records':[]})
    @patch('backend.services.pubmed_service.search',new_callable=AsyncMock,return_value={'status':'ok','records':[]})
    def test_combined_workflow(self,*_): self.assertIn('pipeline_latency_ms',self.client.post('/api/discovery/combined',json={'disease':'condition'}).json())
    @patch('backend.ai.gemma_service.explain_evidence',return_value={'status':'unavailable','data':None,'reason':'not configured'})
    def test_gemma_explanation(self,_): self.assertEqual(self.client.post('/api/ai/explain',json={'evidence':{}}).status_code,200)
    def test_evidence_endpoint(self): self.assertEqual(self.client.get('/api/evidence/abc').status_code,200)
    def test_knowledge_graph_endpoint(self): self.assertEqual(self.client.get('/api/knowledge-graph/disease').status_code,200)
    def test_report_endpoint(self): self.assertEqual(self.client.get('/api/research/report/abc').status_code,200)

if __name__=='__main__': unittest.main()

