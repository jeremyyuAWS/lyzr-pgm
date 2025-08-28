# src/utils/response_validator.py
import json
import yaml

def is_valid_response(raw):
    """
    Try to validate and parse the response.
    Returns (ok: bool, parsed: dict|None, error: str|None)
    """
    if raw is None:
        return False, None, "Empty response"

    # If already a dict
    if isinstance(raw, dict):
        # Must contain minimal expected keys
        if any(k in raw for k in ["workflow_name", "workflow_yaml", "agents", "description"]):
            return True, raw, None
        return False, None, "Dict response missing expected keys"

    # If string, try JSON first
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return True, parsed, None
        except Exception:
            pass
        try:
            parsed = yaml.safe_load(raw)
            if isinstance(parsed, dict):
                return True, parsed, None
        except Exception:
            pass
        return False, None, "Unrecognized string format"

    return False, None, f"Unsupported type: {type(raw)}"
