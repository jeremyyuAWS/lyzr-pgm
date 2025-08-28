import yaml
from pathlib import Path

def save_structured_yaml(data: dict, out_path: Path):
    """Save YAML with blank lines between top-level keys for readability."""
    try:
        raw_dump = yaml.safe_dump(
            data,
            sort_keys=False,
            default_flow_style=False
        )

        # Insert blank lines before each top-level key
        formatted_lines = []
        for i, line in enumerate(raw_dump.splitlines()):
            if line and not line.startswith(" ") and i > 0:
                formatted_lines.append("")
            formatted_lines.append(line)
        formatted = "\n".join(formatted_lines)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write(formatted)

        print(f"✅ Saved structured YAML → {out_path}")
    except Exception as e:
        print(f"⚠️ Failed to save structured YAML: {e}")
