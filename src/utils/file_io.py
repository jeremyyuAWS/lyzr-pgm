import json
import yaml
from pathlib import Path


def save_yaml_file(path: Path, yaml_str: str):
    """
    Try to safely dump YAML. If parsing fails, fall back to raw text.
    """
    try:
        parsed = yaml.safe_load(yaml_str)
        with open(path, "w") as f:
            yaml.dump(
                parsed,
                f,
                sort_keys=False,
                default_flow_style=False,
                indent=2,
                width=80,
            )
    except Exception:
        with open(path, "w") as f:
            f.write(yaml_str)


def save_output(result: dict, usecase_name: str, out_root: str = "output", category: str = "workflows"):
    """
    Save parsed YAML, JSON, errors, and raw output into a consistent folder structure.
    Example: output/workflows/<usecase_name>/... or output/managers/<usecase_name>/...
    """
    domain_dir = Path(out_root) / category / usecase_name
    domain_dir.mkdir(parents=True, exist_ok=True)

    if not result.get("ok", False):
        print(f"❌ Manager failed: {result.get('error')}")
        (domain_dir / "error.log").write_text(result.get("error") or "Unknown error")
        # always save raw for debugging
        (domain_dir / "raw.json").write_text(json.dumps(result.get("raw", {}), indent=2))
        return

    parsed = result.get("parsed")

    # Save parsed JSON
    (domain_dir / "parsed.json").write_text(json.dumps(parsed, indent=2))

    # Save YAML if available
    if isinstance(parsed, dict) and "workflow_yaml" in parsed:
        yaml_file = domain_dir / f"{usecase_name}.yaml"
        save_yaml_file(yaml_file, parsed["workflow_yaml"])
        print(f"✅ Saved YAML to {yaml_file}")

    # Always save raw response too
    (domain_dir / "raw.json").write_text(json.dumps(result.get("raw", {}), indent=2))
