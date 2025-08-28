# /src/utils/yaml_utils.py
import yaml
from pathlib import Path
import re

class BlockStyleDumper(yaml.SafeDumper):
    """Force block style for lists & dicts; prevent inline flow style."""
    def increase_indent(self, flow=False, indentless=False):
        return super(BlockStyleDumper, self).increase_indent(flow, False)

def _repr_list_block(dumper, data):
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=False)

def _repr_dict_block(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data, flow_style=False)

BlockStyleDumper.add_representer(list, _repr_list_block)
BlockStyleDumper.add_representer(dict, _repr_dict_block)

def save_yaml_file(path: Path, yaml_str: str) -> None:
    """
    Save a YAML string with pretty block formatting.
    Falls back to raw string if parsing fails.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        parsed = yaml.safe_load(yaml_str)
        with open(path, "w") as f:
            yaml.dump(
                parsed,
                f,
                Dumper=BlockStyleDumper,
                sort_keys=False,
                default_flow_style=False,
                indent=2,
                width=80,
            )
    except Exception:
        with open(path, "w") as f:
            f.write(yaml_str)

_safe = re.compile(r"[^A-Za-z0-9._-]+")

def safe_name(s: str, default: str = "unnamed") -> str:
    if not s:
        return default
    s = s.strip().replace(" ", "_")
    s = _safe.sub("_", s)
    return s or default
