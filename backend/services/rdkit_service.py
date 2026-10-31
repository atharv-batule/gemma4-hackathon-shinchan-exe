"""RDKit-backed molecular descriptors; computed values are not safety claims."""
from __future__ import annotations
try:
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors
    _AVAILABLE = True
except ImportError:
    Chem = None
    _AVAILABLE = False

def validate_smiles(smiles: str) -> dict:
    if not isinstance(smiles, str) or not smiles.strip():
        return {"status":"invalid_request", "valid":False, "smiles":smiles, "properties":None, "reason":"A non-empty SMILES string is required."}
    if not _AVAILABLE:
        return {"status":"unavailable", "valid":None, "smiles":smiles, "properties":None, "reason":"RDKit is not installed."}
    mol = Chem.MolFromSmiles(smiles.strip())
    if mol is None:
        return {"status":"invalid_structure", "valid":False, "smiles":smiles, "properties":None, "reason":"RDKit could not parse the supplied SMILES."}
    props = {
        "molecular_weight": float(Descriptors.MolWt(mol)),
        "logp": float(Descriptors.MolLogP(mol)),
        "h_bond_donors": int(Lipinski.NumHDonors(mol)),
        "h_bond_acceptors": int(Lipinski.NumHAcceptors(mol)),
        "tpsa": float(rdMolDescriptors.CalcTPSA(mol)),
        "rotatable_bonds": int(Lipinski.NumRotatableBonds(mol)),
    }
    limits = {
        "molecular_weight": ("<=", 500), "logp": ("<=", 5),
        "h_bond_donors": ("<=", 5), "h_bond_acceptors": ("<=", 10),
    }
    violations = [name for name, (_, limit) in limits.items() if props[name] > limit]
    return {
        "status":"ok", "valid":True, "smiles":smiles,
        "canonical_smiles":Chem.MolToSmiles(mol), "properties":props,
        "lipinski": {"passes": len(violations) <= 1, "violation_count": len(violations),
                     "violations": violations,
                     "rule":"Rule-of-five heuristic; not a safety or efficacy assessment."},
        "property_source":"RDKit computed from the supplied SMILES",
        "safety_interpretation":None,
    }
