import json
import yaml
import ast
import re
import shutil
from pathlib import Path
from datetime import datetime

DEFAULT_LLM_CONFIG = {
    "provider_id": "OpenAI",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "top_p": 0.9,
    "response_format": {"type": "json"},
}

def canonicalize_agent_yaml(agent: dict) -> dict:
    """Return canonical agent dict (not string yet)."""
    try:
        parsed = yaml.safe_load(agent.get("yaml", "")) or {}
    except Exception:
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
            if is_manager else ""
        ),
        "response_format": parsed.get("response_format", {"type": "json"}),
        "llm_config": parsed.get("llm_config", DEFAULT_LLM_CONFIG),
    }
    return canonical


def normalize_inference_output(raw_response: str, out_dir: Path, max_attempts: int = 5):
    """
    Robust normalizer with canonical YAML saving.
    - Saves workflow + agent YAMLs to <usecase> folder
    - Also copies role YAMLs into agents/roles/
    - Updates Manager YAMLs with managed_agents pointing to canonical paths
    """

    def safe_json(s):
        try:
            return json.loads(s)
        except Exception:
            return None

    # --- Parsing loop ---
    parsed = None
    for _ in range(max_attempts):
        if isinstance(raw_response, str):
            parsed = safe_json(raw_response)
            if not parsed:
                fixed = raw_response.replace("\r", "").replace("\n", "\\n")
                parsed = safe_json(fixed)
        if isinstance(parsed, dict):
            if "response" in parsed and isinstance(parsed["response"], str):
                parsed = safe_json(parsed["response"]) or parsed
            break

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # --- Fallback regex if parse failed ---
    if not parsed or not isinstance(parsed, dict):
        print("⚠️ Structured parse failed — using regex fallback")
        parsed = {"raw_string": raw_response}
        # workflow
        wf_match = re.search(r'"workflow_yaml":\s*"([^"]+)"', raw_response, re.DOTALL)
        if wf_match:
            parsed["workflow_yaml"] = wf_match.group(1).encode("utf-8").decode("unicode_escape")
        # agents
        agent_matches = re.findall(r'"yaml":\s*"([^"]+)"', raw_response, re.DOTALL)
        if agent_matches:
            parsed["agents"] = [{"yaml": b.encode("utf-8").decode("unicode_escape")} for b in agent_matches]

    # --- Save workflow.yaml ---
    if "workflow_yaml" in parsed:
        wf_file = out_dir / f"workflow_{ts}.yaml"
        with open(wf_file, "w") as f:
            f.write(parsed["workflow_yaml"])
        print(f"📝 Saved workflow YAML → {wf_file}")

    # --- Save agents ---
    saved_agents = []
    if "agents" in parsed:
        for agent in parsed["agents"]:
            canon = canonicalize_agent_yaml(agent)
            fname = out_dir / f"{canon['name']}.yaml"
            with open(fname, "w") as f:
                yaml.safe_dump(canon, f, sort_keys=False)
            print(f"📝 Saved canonical agent YAML → {fname}")
            saved_agents.append(canon)

            # Also copy Role YAMLs to canonical repo under agents/roles/
            if not any(x in canon["name"].lower() for x in ["manager", "mgr"]):
                roles_dir = Path("agents/roles")
                roles_dir.mkdir(parents=True, exist_ok=True)
                repo_path = roles_dir / f"{canon['name']}.yaml"
                shutil.copy(fname, repo_path)
                print(f"📂 Copied role agent YAML → {repo_path}")

    # --- Post-process: Update Manager(s) with managed_agents ---
    managers = [a for a in saved_agents if "manager" in a["name"].lower() or "mgr" in a["name"].lower()]
    roles = [a for a in saved_agents if a not in managers]

    if managers and roles:
        for mgr in managers:
            mgr_path = out_dir / f"{mgr['name']}.yaml"
            try:
                with open(mgr_path) as f:
                    mgr_yaml = yaml.safe_load(f)

                mgr_yaml["managed_agents"] = [
                    {
                        "file": f"agents/roles/{role['name']}.yaml",
                        "usage_description": role.get("description", f"{role['name']} supports the manager.")
                    }
                    for role in roles
                ]

                with open(mgr_path, "w") as f:
                    yaml.safe_dump(mgr_yaml, f, sort_keys=False)
                print(f"🔗 Updated Manager {mgr['name']} with {len(roles)} managed_agents (canonical paths)")
            except Exception as e:
                print(f"⚠️ Could not update manager {mgr['name']}: {e}")

    return parsed
