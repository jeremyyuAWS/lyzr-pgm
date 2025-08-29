import json
import yaml
import ast
import re
from pathlib import Path
from datetime import datetime

DEFAULT_LLM_CONFIG = {
    "provider_id": "OpenAI",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "top_p": 0.9,
    "response_format": {"type": "json"},
}

def canonicalize_agent_yaml(agent: dict, role_agents: list = None) -> str:
    """
    Convert agent['yaml'] into canonical Lyzr YAML with llm_config.
    Adds managed_agents if this is a Manager.
    """
    try:
        parsed = yaml.safe_load(agent.get("yaml", "")) or {}
    except Exception as e:
        print(f"⚠️ Could not parse agent YAML for {agent.get('name')} → {e}")
        parsed = {"name": agent.get("name", "unnamed_agent")}

    name = parsed.get("name", agent.get("name", "unnamed_agent"))
    is_manager = any(x in name.lower() for x in ["manager", "mgr"])

    canonical = {
        "template_type": "single_task",
        "name": name,
        "description": parsed.get("description", ""),
        "agent_role": parsed.get("agent_role", ""),
        "agent_goal": parsed.get("agent_goal", ""),
        "agent_instructions": parsed.get("agent_instructions", ""),
        "features": parsed.get("features", []),
        "tools": parsed.get("tools", []),
        "tool_usage_description": parsed.get(
            "tool_usage_description",
            "The manager orchestrates subordinate role agents and packages outputs."
            if is_manager else parsed.get("tool_usage_description", "")
        ),
        "response_format": parsed.get("response_format", {"type": "json"}),
        "llm_config": parsed.get("llm_config", DEFAULT_LLM_CONFIG),
    }

    if is_manager:
        # Add canonical features
        canonical["features"].extend([
            {"type": "yaml_syntax_validation", "config": {}, "priority": 0},
            {"type": "canonical_structure_check", "config": {}, "priority": 1},
        ])

        # Add managed_agents
        if role_agents:
            managed = []
            for role in role_agents:
                role_name = role.get("name")
                if not role_name:
                    continue
                managed.append({
                    "file": f"agents/roles/{role_name}.yaml",
                    "usage_description": f"{role_name} supports the manager by handling {role.get('description','role-specific tasks')}."
                })
            canonical["managed_agents"] = managed

    return yaml.safe_dump(canonical, sort_keys=False)


def normalize_inference_output(raw_response: str, out_dir: Path, max_attempts: int = 5):
    """
    Super-robust inference normalizer:
    - Tries multiple parse strategies
    - Falls back to regex extraction
    - Always canonicalizes saved agent YAMLs
    """

    def safe_json(s, label=""):
        try:
            return json.loads(s)
        except Exception as e:
            print(f"   ❌ {label} failed: {e}")
            return None

    def try_parse_once(source: str):
        parsed = safe_json(source, "direct")
        if parsed:
            return parsed

        parsed = safe_json(source.replace("\r", "").replace("\n", "\\n"), "escape-fix")
        if parsed:
            return parsed

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
    for attempt in range(1, max_attempts + 1):
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

    # --- Fallback regex ---
    if not parsed or not isinstance(parsed, dict):
        print("⚠️ Structured parse failed — using regex fallback")
        parsed = {"raw_string": raw_response}

        # workflow_yaml
        wf_match = re.search(r'"workflow_yaml":\s*"([^"]+)"', raw_response, re.DOTALL)
        if wf_match:
            yaml_text = wf_match.group(1).encode("utf-8").decode("unicode_escape")
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
                yaml_text = block.encode("utf-8").decode("unicode_escape")
                try:
                    block_dict = yaml.safe_load(yaml_text)
                    agent_name = block_dict.get("name", f"agent_partial_{idx}")
                except Exception:
                    agent_name = f"agent_partial_{idx}"

                canonical_text = canonicalize_agent_yaml(
                    {"yaml": yaml_text, "name": agent_name}
                )
                fname = out_dir / f"{agent_name}.yaml"
                with open(fname, "w") as f:
                    f.write(canonical_text)

                parsed["agents"].append({"name": agent_name, "yaml": canonical_text})
                print(f"📝 [Fallback] Saved canonical agent YAML → {fname}")

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
        role_agents = [a for a in parsed["agents"] if not any(x in a.get("name", "").lower() for x in ["manager", "mgr"])]
        for agent in parsed.get("agents", []):
            if "yaml" in agent:
                canonical_text = canonicalize_agent_yaml(agent, role_agents)
                fname = out_dir / f"{agent['name']}.yaml"
                with open(fname, "w") as f:
                    f.write(canonical_text)
                print(f"📝 Saved canonical agent YAML → {fname}")
    else:
        print("⚠️ No agents found to save.")

    return parsed
