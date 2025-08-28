# /src/utils/output_saver.py
import os, json, yaml
from datetime import datetime
from src.utils.response_parser import classify_and_normalize

def save_output(base_dir: str, name: str, raw_response: dict):
    """Save raw response and attempt structured salvage into YAML files."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(base_dir, f"{name}_{ts}")
    os.makedirs(outdir, exist_ok=True)

    # Always save raw JSON
    with open(os.path.join(outdir, "raw.json"), "w") as f:
        json.dump(raw_response, f, indent=2, ensure_ascii=False)

    # Try parsing into workflow + agents
    status, payload, diag = classify_and_normalize(raw_response)

    if status == "success":
        # Save workflow.yaml
        wf_file = os.path.join(outdir, "workflow.yaml")
        with open(wf_file, "w") as f:
            yaml.safe_dump(payload["workflow_yaml"], f, sort_keys=False)

        # Save each agent
        for i, agent in enumerate(payload.get("agents", []), 1):
            fname = f"agent_{i}_{agent.get('name','unnamed')}.yaml"
            with open(os.path.join(outdir, fname), "w") as f:
                yaml.safe_dump(agent, f, sort_keys=False)

        print(f"📂 Structured salvage written to {outdir}")
    else:
        # Instead of noisy ❌, just print once
        print(f"⚠️ Saved raw response only to {outdir} (no structured parse)")
