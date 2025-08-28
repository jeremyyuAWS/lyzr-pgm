# src/utils/save_output.py
from pathlib import Path
import yaml

def save_yaml_file(path, content):
    """Save string or dict as YAML file with pretty formatting."""
    with open(path, "w") as f:
        if isinstance(content, str):
            # Already a YAML string block
            f.write(content.strip() + "\n")
        else:
            # Dict → dump as YAML
            yaml.safe_dump(content, f, sort_keys=False)

def save_output(data, usecase_name: str, out_root="output"):
    domain = usecase_name.split("_")[-1] if "_" in usecase_name else usecase_name
    workflow_name = data["core"].get("workflow_name", "unnamed_workflow")
    base_dir = Path(out_root) / domain / workflow_name
    base_dir.mkdir(parents=True, exist_ok=True)

    # Save workflow_yaml
    if "workflow_yaml" in data["core"]:
        wf_file = base_dir / f"{workflow_name}.yaml"
        save_yaml_file(wf_file, data["core"]["workflow_yaml"])
        print(f"📝 Saved workflow → {wf_file}")

    # Save agent yamls
    for agent in data["core"].get("agents", []):
        agent_file = base_dir / f"{agent['name']}.yaml"
        save_yaml_file(agent_file, agent["yaml"])
        print(f"📝 Saved agent → {agent_file}")

    # Save extras
    if data.get("extra"):
        extra_file = base_dir / "extra.log"
        with open(extra_file, "w") as f:
            yaml.dump(data["extra"], f, sort_keys=False)
        print(f"🗒️ Extra info saved to → {extra_file}")
