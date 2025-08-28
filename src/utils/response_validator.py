import json, yaml, time
from typing import Any, Tuple

def is_valid_response(resp: str | dict) -> Tuple[bool, dict | None, str | None]:
    try:
        if isinstance(resp, str):
            data = json.loads(resp)
        else:
            data = resp

        if not all(k in data for k in ("workflow_name", "workflow_yaml", "agents")):
            return False, None, "Missing required keys"

        yaml.safe_load(data["workflow_yaml"])  # validate workflow_yaml

        for agent in data.get("agents", []):
            yaml.safe_load(agent.get("yaml", ""))  # validate each agent yaml

        return True, data, None
    except Exception as e:
        return False, None, str(e)

def run_with_retries(request_fn, max_retries=5, backoff=3):
    for attempt in range(1, max_retries + 1):
        resp = request_fn()
        ok, parsed, err = is_valid_response(resp)

        if ok:
            print(f"✅ Success on attempt {attempt}")
            return parsed

        print(f"❌ Attempt {attempt} failed: {err}")
        if attempt < max_retries:
            time.sleep(backoff * attempt)
            print("🔄 Retrying...")

    raise RuntimeError(f"Failed after {max_retries} retries")
