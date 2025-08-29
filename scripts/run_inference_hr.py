import os
import sys
import json
import yaml
from pathlib import Path

from scripts.run_inference import run_inference  # reuse your existing function

# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------

def load_usecase(path: str) -> str:
    """Flatten a use case YAML into a single string message for inference."""
    with open(path, "r") as f:
        uc = yaml.safe_load(f)

    # Build human-readable message
    message = []
    if "use_case" in uc:
        message.append(f"Use Case:\n{uc['use_case']}")
    if "requirements" in uc:
        message.append(f"\nRequirements:\n{json.dumps(uc['requirements'], indent=2)}")
    if "constraints" in uc:
        message.append(f"\nConstraints:\n{json.dumps(uc['constraints'], indent=2)}")
    if "acceptance_criteria" in uc:
        message.append(f"\nAcceptance Criteria:\n{json.dumps(uc['acceptance_criteria'], indent=2)}")

    return "\n".join(message).strip()

# ------------------------------------------------------------------------------
# Main
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.run_inference_hr <agent_id> <usecase_file>")
        sys.exit(1)

    agent_id = sys.argv[1]          # e.g. 68b09132fb41ab28...
    usecase_file = sys.argv[2]      # e.g. agents/use_cases_hr.yaml

    if not Path(usecase_file).exists():
        print(f"❌ Use case file not found: {usecase_file}")
        sys.exit(1)

    # Build message text from YAML
    message = load_usecase(usecase_file)

    # Call your existing run_inference
    run_inference(agent_id, message)
