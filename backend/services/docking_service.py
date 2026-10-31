"""Docking is an optional extension and is intentionally not simulated."""
def dock(*args, **kwargs) -> dict:
    return {"status":"unavailable", "score":None, "reason":"Docking backend and validated protein/ligand inputs are not configured."}
