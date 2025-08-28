import json
from pathlib import Path

def save_output(parsed: dict, raw: str, base="output", domain="default"):
    out_dir = Path(base) / domain
    out_dir.mkdir(parents=True, exist_ok=True)

    if parsed:
        with open(out_dir / "workflow.json", "w") as f:
            json.dump(parsed, f, indent=2)
    else:
        with open(out_dir / "error.log", "a") as f:
            f.write(raw + "\n\n")
