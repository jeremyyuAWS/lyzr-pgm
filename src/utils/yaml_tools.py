import yaml

def validate_yaml_schema(yaml_def: str) -> dict:
    try:
        parsed = yaml.safe_load(yaml_def)
        # basic check for required keys
        required = ["name", "agent_role", "agent_goal"]
        for key in required:
            if key not in parsed:
                return {"ok": False, "error": f"Missing key: {key}"}
        return {"ok": True, "yaml": parsed}
    except Exception as e:
        return {"ok": False, "error": str(e)}
