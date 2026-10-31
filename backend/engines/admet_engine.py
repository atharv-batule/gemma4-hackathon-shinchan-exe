"""No ADMET predictions are inferred without a configured validated model/data source."""
def assess_admet(smiles: str) -> dict:
    return {"status":"unavailable", "smiles":smiles, "measured_data":None, "predictions":None, "reason":"No measured ADMET source or validated prediction model is configured."}
