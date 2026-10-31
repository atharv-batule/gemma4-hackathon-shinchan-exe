from backend.services.rdkit_service import validate_smiles as _validate_smiles

def validate(smiles: str) -> dict:
    return _validate_smiles(smiles)

def validate_smiles_structure(smiles: str) -> dict:
    return _validate_smiles(smiles)

def validate_smiles(smiles: str) -> dict:
    return _validate_smiles(smiles)
