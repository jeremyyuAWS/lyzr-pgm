import yaml, os, json
from pathlib import Path
import httpx
from src.utils.normalize_response import normalize_response

USE_CASES_DIR = Path("agents/use_cases")

def run_use_cases_with_manager(manager_id: str, api_key: str):
    base_url = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    results = []

    for uc_file in USE_CASES_DIR.glob("use_cases_*.yaml"):
        with open(uc_file, "r") as f:
            use_cases = yaml.safe_load(f).get("use_cases", [])

        for case in use_cases:
            uc_name = case["name"]
            print(f"📥 Running use case: {uc_name}")
            payload = {
                "agent_id": manager_id,
                "user_id": "bolt-orchestrator",
                "session_id": f"{manager_id}-{os.urandom(4).hex()}",
                "message": case["description"],
            }
            try:
                resp = httpx.post(f"{base_url}/v3/inference/chat/", headers=headers, json=payload, timeout=90)
                resp.raise_for_status()
                normalized = normalize_response(json.dumps(resp.json()))

                # save YAML output
                out_dir = Path(f"outputs/{uc_name}")
                out_dir.mkdir(parents=True, exist_ok=True)
                with open(out_dir / f"{uc_name}.json", "w") as f:
                    json.dump(normalized, f, indent=2)

                results.append({"use_case": uc_name, "status": "ok", "output_file": str(out_dir / f"{uc_name}.json")})
            except Exception as e:
                results.append({"use_case": uc_name, "status": "error", "error": str(e)})

    return results
