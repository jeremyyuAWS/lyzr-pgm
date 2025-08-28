# /src/utils/response_parser.py
import json
import yaml
from typing import Any, Dict, Tuple

SUCCESS_KEYS = {"workflow_yaml", "agents"}

def _try_json(s: str):
    try:
        v = json.loads(s)
        return True, v, "json_loads_success"
    except Exception as e:
        return False, None, f"json_loads_error:{type(e).__name__}"

def _try_yaml(s: str):
    try:
        v = yaml.safe_load(s)
        return True, v, "yaml_load_success"
    except Exception as e:
        return False, None, f"yaml_load_error:{type(e).__name__}"

def _looks_success(d: dict) -> bool:
    return all(k in d for k in SUCCESS_KEYS)

def classify_and_normalize(raw: Any) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Returns:
      status: 'success' | 'error'
      payload: success -> {workflow_name, workflow_yaml, agents}
               error   -> {'message': str}
      diag:    diagnostic dict (what we tried, why we decided)
    """
    diag = {"steps": []}

    # Case A: already success-shaped dict
    if isinstance(raw, dict) and _looks_success(raw):
        diag["steps"].append("raw_already_success_dict")
        name = raw.get("workflow_name") or "unnamed_workflow"
        return "success", {
            "workflow_name": name,
            "workflow_yaml": raw["workflow_yaml"],
            "agents": raw.get("agents", []),
        }, diag

    # Case B: common Lyzr shape {"response": "<string>"}
    if isinstance(raw, dict) and "response" in raw:
        s = str(raw["response"]).strip()
        diag["steps"].append("found_response_string")

        ok, val, note = _try_json(s)
        diag["steps"].append(note)
        if ok and isinstance(val, dict) and _looks_success(val):
            name = val.get("workflow_name") or "unnamed_workflow"
            return "success", {
                "workflow_name": name,
                "workflow_yaml": val["workflow_yaml"],
                "agents": val.get("agents", []),
            }, diag

        ok, val, note = _try_yaml(s)
        diag["steps"].append(note)
        if ok and isinstance(val, dict) and _looks_success(val):
            name = val.get("workflow_name") or "unnamed_workflow"
            return "success", {
                "workflow_name": name,
                "workflow_yaml": val["workflow_yaml"],
                "agents": val.get("agents", []),
            }, diag

        # Heuristic salvage: if JSON wrapper with big string fields present, keep as error but include hint
        return "error", {"message": s}, diag

    # Case C: API already handed us a dict, try to interpret
    if isinstance(raw, dict):
        diag["steps"].append("raw_dict_no_response_key")
        if _looks_success(raw):
            name = raw.get("workflow_name") or "unnamed_workflow"
            return "success", {
                "workflow_name": name,
                "workflow_yaml": raw["workflow_yaml"],
                "agents": raw.get("agents", []),
            }, diag
        # Might be an explicit failure shape
        if "error" in raw and isinstance(raw["error"], (str, dict)):
            return "error", {"message": raw["error"]}, diag
        # Unknown dict
        return "error", {"message": json.dumps(raw, ensure_ascii=False)}, diag

    # Case D: string body (rare)
    if isinstance(raw, str):
        s = raw.strip()
        diag["steps"].append("raw_string_body")
        ok, val, note = _try_json(s)
        diag["steps"].append(note)
        if ok and isinstance(val, dict) and _looks_success(val):
            name = val.get("workflow_name") or "unnamed_workflow"
            return "success", {
                "workflow_name": name,
                "workflow_yaml": val["workflow_yaml"],
                "agents": val.get("agents", []),
            }, diag
        ok, val, note = _try_yaml(s)
        diag["steps"].append(note)
        if ok and isinstance(val, dict) and _looks_success(val):
            name = val.get("workflow_name") or "unnamed_workflow"
            return "success", {
                "workflow_name": name,
                "workflow_yaml": val["workflow_yaml"],
                "agents": val.get("agents", []),
            }, diag
