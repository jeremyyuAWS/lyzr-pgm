import sys
import os
import json
from pathlib import Path
from datetime import datetime

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.utils.normalize_output import normalize_inference_output


def run_inference(client: LyzrAPIClient, agent_id: str, message: str, out_dir: Path):
    """Send a message to the agent, store raw + normalized response."""
    payload = {
        "user_id": os.getenv("LYZR_USER_ID", "demo-user"),
        "system_prompt_variables": {},
        "agent_id": agent_id,
        "session_id": f"{agent_id}-{os.urandom(4).hex()}",
        "message": message,
        "filter_variables": {},
        "features": [],
        "assets": []
    }

    resp = client._request("POST", "/v3/inference/chat/", payload=payload)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Save raw response
    raw_file = out_dir / f"inference_raw_{ts}.json"
    with open(raw_file, "w") as f:
        json.dump(resp, f, indent=2)
    print(f"📦 Raw inference response saved to {raw_file}")

    # 2. Normalize response
    if resp.get("ok") and "data" in resp and "response" in resp["data"]:
        raw_str = resp["data"]["response"]
        norm = normalize_inference_output(raw_str)

        norm_file = out_dir / f"inference_normalized_{ts}.json"
        with open(norm_file, "w") as f:
            json.dump(norm, f, indent=2)
        print(f"✅ Normalized inference output saved to {norm_file}")
    else:
        print("⚠️ No 'response' field found in inference data — skipping normalization.")

    # 3. Save extracted YAMLs if present
    if isinstance(norm, dict):
        if "workflow_yaml" in norm:
            wf_file = out_dir / "workflow.yaml"
            with open(wf_file, "w") as f:
                f.write(norm["workflow_yaml"])
            print(f"📝 Saved workflow.yaml")

        for agent in norm.get("agents", []):
            if "yaml" in agent and "name" in agent:
                fname = out_dir / f"{agent['name']}.yaml"
                with open(fname, "w") as f:
                    f.write(agent["yaml"])
                print(f"📝 Saved {fname.name}")
    return resp


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.create_manager_from_yaml <manager_yaml> [use_case_text]")
        sys.exit(1)

    manager_yaml_path = sys.argv[1]
    use_case_text = sys.argv[2] if len(sys.argv) > 2 else "Test: Generate a schema-compliant YAML definition."

    debug = os.getenv("LYZR_DEBUG", "0") == "1"
    client = LyzrAPIClient(debug=debug, timeout=180)
    manager = AgentManager(client)

    result = manager.create_manager_with_roles(manager_yaml_path)
    if not result:
        print("❌ Manager creation failed.")
        sys.exit(1)

    print(f"\n✅ Manager agent created successfully!")
    print(f"   ID   : {result['agent_id']}")
    print(f"   Name : {result['name']}")

    # Run inference immediately
    out_dir = Path("output") / Path(manager_yaml_path).stem
    run_inference(client, result["agent_id"], use_case_text, out_dir)


if __name__ == "__main__":
    main()
