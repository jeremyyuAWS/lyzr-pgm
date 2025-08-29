import json
import yaml
import ast
import re
from pathlib import Path
from datetime import datetime

def normalize_inference_output(raw_response: str, out_dir: Path, max_attempts: int = 5):
    """
    Super-robust inference normalizer:
    - Retries fresh parse attempts with multiple strategies
    - Unwraps nested response keys
    - Falls back to regex-extracting workflow_yaml/agent YAMLs if structured parse fails
    - Always saves partials if found
    """

    def safe_json(s, label=""):
        try:
            return json.loads(s)
        except Exception as e:
            print(f"   ❌ {label} failed: {e}")
            return None

    def try_parse_once(source: str):
        # 1. Direct JSON
        parsed = safe_json(source, "direct")
        if parsed: return parsed

        # 2. Escape-fix
        parsed = safe_json(source.replace("\r", "").replace("\n", "\\n"), "escape-fix")
        if parsed: return parsed

        # 3. literal_eval
        try:
            parsed = ast.literal_eval(source)
            if isinstance(parsed, dict):
                print("   ✅ literal_eval succeeded")
                return parsed
        except Exception as e:
            print(f"   ❌ literal_eval failed: {e}")

        return None

    def unwrap(candidate):
        if not isinstance(candidate, dict):
            return candidate
        for key in ["response", "input", "output", "yaml_schema", "workflow_definition"]:
            if key in candidate:
                inner = candidate[key]
                if isinstance(inner, str):
                    return try_parse_once(inner) or inner
                elif isinstance(inner, dict):
                    return inner
        return candidate

    parsed = None
    for attempt in range(1, max_attempts+1):
        print(f"🔄 Parse attempt {attempt}…")
        candidate = try_parse_once(raw_response)
        if not candidate:
            continue

        unwraps = 0
        while isinstance(candidate, dict) and unwraps < 5:
            before = candidate
            candidate = unwrap(candidate)
            if candidate is before:
                break
            unwraps += 1

        if isinstance(candidate, dict):
            parsed = candidate
            break

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not parsed or not isinstance(parsed, dict):
        print("⚠️ Structured parse failed — using regex fallback")
        parsed = {"raw_string": raw_response}

        # workflow_yaml
        wf_match = re.search(r'"workflow_yaml":\s*"([^"]+)"', raw_response, re.DOTALL)
        if wf_match:
            yaml_text = wf_match.group(1).encode('utf-8').decode('unicode_escape')
            parsed["workflow_yaml"] = yaml_text
            wf_file = out_dir / f"workflow_{ts}.yaml"
            with open(wf_file, "w") as f:
                f.write(yaml_text)
            print(f"📝 [Fallback] Saved workflow YAML → {wf_file}")

        # agent YAMLs
        agent_matches = re.findall(r'"yaml":\s*"([^"]+)"', raw_response, re.DOTALL)
        if agent_matches:
            parsed["agents"] = []
            for idx, block in enumerate(agent_matches, 1):
                yaml_text = block.encode('utf-8').decode('unicode_escape')
                fname = out_dir / f"agent_partial_{idx}_{ts}.yaml"
                with open(fname, "w") as f:
                    f.write(yaml_text)
                parsed["agents"].append({"yaml": yaml_text})
                print(f"📝 [Fallback] Saved agent YAML → {fname}")

        return parsed

    # --- Normal path ---
    print(f"📑 Final normalized keys: {list(parsed.keys())}")

    if "workflow_yaml" in parsed:
        wf_file = out_dir / f"workflow_{ts}.yaml"
        with open(wf_file, "w") as f:
            f.write(parsed["workflow_yaml"])
        print(f"📝 Saved workflow YAML → {wf_file}")
    else:
        print("⚠️ No workflow_yaml to save.")

    if "agents" in parsed:
        for agent in parsed.get("agents", []):
            if "yaml" in agent:
                agent_file = out_dir / f"{agent['name']}_{ts}.yaml"
                with open(agent_file, "w") as f:
                    f.write(agent["yaml"])
                print(f"   → Saved agent YAML → {agent_file}")
    else:
        print("⚠️ No agents found to save.")

    return parsed
