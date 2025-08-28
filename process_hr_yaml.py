# process_hr_yaml.py
import json
import yaml
import re
from pathlib import Path
from src.utils.save_utils import save_structured_yaml


def extract_response(raw):
    """Extract and clean response string safely."""
    response_str = raw.get("data", {}).get("response", "")
    if not response_str:
        raise ValueError("No response in raw.json")

    # Try direct JSON parse
    try:
        return json.loads(response_str)
    except json.JSONDecodeError:
        pass

    # Try unescaping control characters
    try:
        cleaned = response_str.encode().decode("unicode_escape")
        return json.loads(cleaned)
    except Exception:
        pass

    # Fallback: strip wrapping braces and quotes if it's inline JSON-as-string
    try:
        # Remove surrounding quotes if present
        if response_str.startswith('"') and response_str.endswith('"'):
            response_str = response_str[1:-1]

        # Replace escaped quotes/newlines
        response_str = response_str.replace('\\"', '"').replace("\\n", "\n")

        # If it's JSON-like
        if response_str.strip().startswith("{"):
            return json.loads(response_str)
    except Exception:
        pass

    # Last fallback: just return as dict with raw YAML text
    return {"workflow_yaml": response_str}


def main():
    in_path = Path("output/workflows/use_cases_hr/raw.json")
    out_path = Path("output/workflows/use_cases_hr/agent.yaml")

    if not in_path.exists():
        print(f"❌ {in_path} not found")
        return

    try:
        raw = json.loads(in_path.read_text())
        response_obj = extract_response(raw)
        text = response_obj.get("workflow_yaml", "")
    except Exception as e:
        print(f"⚠️ Failed to extract embedded YAML: {e}")
        return

    if not text:
        print("❌ No YAML found in raw.json")
        return

    try:
        parsed = yaml.safe_load(text)
        if not isinstance(parsed, dict):
            raise ValueError("Top-level YAML is not a dict")

        save_structured_yaml(parsed, out_path)
        print(f"✅ Saved structured YAML → {out_path}")

    except Exception as e:
        print(f"⚠️ YAML parse failed: {e}")
        print("Dumping raw YAML instead.")
        out_path.write_text(text)


if __name__ == "__main__":
    main()
