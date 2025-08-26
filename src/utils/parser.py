import yaml
import json
from pathlib import Path

def json_to_yaml(data: dict, output_file: str = None):
    """Convert JSON dict → YAML string (optionally save to file)."""
    yaml_str = yaml.safe_dump(data, sort_keys=False)
    if output_file:
        Path(output_file).write_text(yaml_str, encoding="utf-8")
    return yaml_str

def yaml_to_json(yaml_file: str) -> dict:
    """Convert YAML file → JSON dict."""
    with open(yaml_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def normalize_response(raw_text: str) -> dict:
    """
    Attempt to parse LLM responses as JSON first.
    If it's YAML, auto-convert to JSON.
    """
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            return yaml.safe_load(raw_text)
        except Exception as e:
            raise ValueError(f"Failed to parse response: {e}")
