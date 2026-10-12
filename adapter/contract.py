import json
from pathlib import Path
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contracts"

class ContractError(Exception):
    """Raised when a contract can't be loaded or is malformed."""

def load_contract(name_or_path, directory=CONTRACT_DIR):
    path = Path(name_or_path)
    if path.suffix != ".json":
        path = Path(directory) / f"{name_or_path}.json"
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ContractError(f"No contract file found at {path}")
    except json.JSONDecodeError as exc:
        raise ContractError(f"{path} is not valid JSON: {exc}")

    for key in ("name", "description", "schema"):
        if key not in contract:
            raise ContractError(f"{path} is missing the '{key}' key")
    try:
        Draft202012Validator.check_schema(contract["schema"])
    except SchemaError as exc:
        raise ContractError(f"{path} has an invalid schema: {exc.message}")
    return contract
