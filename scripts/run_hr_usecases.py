import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
import yaml

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.utils.normalize_output import normalize_inference_output


def run_inference(client: LyzrAPIClient, agent_id: str, usecase: dict, out_root: Path, max_retries: int = 3):
    """Run inference for a single HR use case, retrying if response unusable."""
    usecase_name = usecase.get("name", "unnamed_usecase").replace(" ", "_").lower()
    usecase_text = usecase.get("description", "")
    if not usecase_text:
        print(f"⚠️ Skipping {usecase_name}: no description found")
        return

    print(f"\n📥 Running use case: {usecase_name}")

    out_dir = out_root / usecase_name
    out_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_retries + 1):
        payload = {
            "user_id": os.getenv("LYZR_USER_ID", "demo-user"),
            "system_prompt_variables": {},
            "agent_id": agent_id,
            "session_id": f"{agent_id}-{os.urandom(4).hex()}",
            "message": usecase_text,
            "filter_variables": {},
            "features": [],
            "assets": [],
        }

        resp = client._request("POST", "/v3/inference/chat/", payload=payload)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save raw
        raw_file = out_dir / f"inference_raw_{ts}_attempt{attempt}.json"
        with open(raw_file, "w") as f:
            json.dump(resp, f, indent=2)
        print(f"📦 Raw inference response saved to {raw_file}")

        usable = False
        if resp.get("ok") and "data" in resp and "response" in resp["data"]:
            raw_str = resp["data"]["response"]
            try:
                norm = normalize_inference_output(raw_str, out_dir)
                norm_file = out_dir / f"inference_normalized_{ts}_attempt{attempt}.json"
                with open(norm_file, "w") as f:
                    json.dump(norm, f, indent=2)
                print(f"✅ Normalized inference output saved to {norm_file}")
                usable = True
            except Exception as e:
                print(f"⚠️ Normalization failed on attempt {attempt}: {e}")

        if usable:
            return  # success → stop retrying
        else:
            if attempt < max_retries:
                wait = 2 ** (attempt - 1)
                print(f"⚠️ No usable response for {usecase_name}, retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"❌ Failed to get valid response for {usecase_name} after {max_retries} attempts.")


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.run_hr_usecases <manager_yaml> <usecases_file>")
        sys.exit(1)

    manager_yaml_path = sys.argv[1]
    usecases_file = sys.argv[2]

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)
    manager = AgentManager(client)

    # Create Manager + Roles
    result = manager.create_manager_with_roles(manager_yaml_path)
    if not result:
        print("❌ Manager creation failed.")
        sys.exit(1)

    mgr_id = result["agent_id"]
    print(f"\n✅ Manager agent ready: {result['name']}")

    # Load use cases
    with open(usecases_file, "r") as f:
        usecases = yaml.safe_load(f)

    # Run inference per use case
    out_root = Path("output") / Path(manager_yaml_path).stem
    for uc in usecases.get("use_cases", []):
        run_inference(client, mgr_id, uc, out_root)


if __name__ == "__main__":
    main()
