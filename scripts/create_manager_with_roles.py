def create_manager_with_roles(client: LyzrAPIClient, manager_yaml: Union[Path, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Create role agents first, then manager, then:
      - rename both with PST timestamp and id suffix,
      - attach roles to manager (managed_agents + usage_description),
      - set robust system_prompt & examples via PUT (creation may ignore these fields).
    """
    # Load YAML if a path was received
    if isinstance(manager_yaml, Path):
        with open(manager_yaml, "r") as f:
            manager_yaml = yaml.safe_load(f)

    if not isinstance(manager_yaml, dict):
        raise ValueError("manager_yaml must be a dict or Path")

    manager_def = manager_yaml.get("manager")
    if not manager_def:
        raise ValueError("YAML must contain a top-level 'manager' key")

    # ----- Create roles first -----
    created_roles: List[Dict[str, Any]] = []
    for role in manager_def.get("managed_agents", []):
        if "yaml" not in role:
            print(f"⚠️ Skipping role {role.get('name')} (no inline YAML)")
            continue

        # 🔑 Fix: decode escaped YAML string
        raw_yaml = role["yaml"]
        if isinstance(raw_yaml, str):
            raw_yaml = raw_yaml.replace("\\n", "\n").replace("\\t", "  ")

        try:
            role_yaml = yaml.safe_load(raw_yaml)
        except Exception as e:
            print(f"❌ Failed to parse role YAML for {role.get('name')}: {e}")
            continue

        role_name = role_yaml.get("name", "ROLE")

        # inject examples & prepare prompt
        role_yaml["examples"] = canonical_role_examples(role_name)

        print(f"🎭 Creating role agent: {role_name}")
        role_resp = create_agent_from_yaml(client, role_yaml)
        if not role_resp.get("ok"):
            print(f"❌ Failed to create role {role_name}")
            print(role_resp)
            continue

        role_id = (role_resp.get("data") or {}).get("agent_id")
        if not role_id:
            print(f"❌ Role {role_name} created but missing agent_id in response")
            continue

        # Rename + set system_prompt + examples (PUT)
        role_renamed = _rich_role_name(role_name, role_id)
        role_updates = {
            "name": role_renamed,
            "system_prompt": _compose_system_prompt(role_yaml),
            "examples": role_yaml["examples"],
            # also backfill these where supported
            "agent_role": role_yaml.get("agent_role", ""),
            "agent_goal": role_yaml.get("agent_goal", ""),
            "agent_instructions": role_yaml.get("agent_instructions", ""),
        }
        upd = update_agent(client, role_id, role_updates)
        if not upd.get("ok"):
            print(f"⚠️ PUT update failed for role {role_name}: {upd}")

        created_roles.append({
            "id": role_id,
            "name": role_renamed,  # store the final name
            "base_name": role_name,
            "description": role_yaml.get("description", ""),
            "agent_role": role_yaml.get("agent_role", ""),
            "agent_goal": role_yaml.get("agent_goal", ""),
            "agent_instructions": role_yaml.get("agent_instructions", ""),
        })

    # ----- Create manager -----
    manager_base_name = manager_def.get("name", "MANAGER")
    # Build enhanced instructions to include supervision lines
    mgr_instr_with_supervision = _manager_supervision_instructions(manager_def, created_roles)

    # Also set examples (manager + roles)
    mgr_examples = canonical_manager_examples(manager_base_name, [r["base_name"] for r in created_roles])
    manager_def["examples"] = mgr_examples

    print(f"👑 Creating manager agent: {manager_base_name}")
    mgr_resp = create_agent_from_yaml(client, manager_def)
    if not mgr_resp.get("ok"):
        print("❌ Manager creation failed")
        print(mgr_resp)
        return {}

    manager_id = (mgr_resp.get("data") or {}).get("agent_id")
    if not manager_id:
        print("❌ Manager created but missing agent_id in response")
        return {}

    # Rename + attach roles + set prompts/examples
    manager_renamed = _rich_manager_name(manager_base_name, manager_id)

    # Manager managed_agents payload with usage descriptors
    managed_agents_payload = [
        {
            "id": r["id"],
            "name": r["name"],
            "usage_description": f"Manager delegates YAML-subtasks to '{r['name']}'."
        }
        for r in created_roles
    ]

    manager_updates = {
        "name": manager_renamed,
        "system_prompt": _compose_system_prompt({
            "agent_role": manager_def.get("agent_role", ""),
            "agent_goal": manager_def.get("agent_goal", ""),
            "agent_instructions": mgr_instr_with_supervision,
        }),
        "examples": mgr_examples,
        # best-effort backfill
        "agent_role": manager_def.get("agent_role", ""),
        "agent_goal": manager_def.get("agent_goal", ""),
        "agent_instructions": mgr_instr_with_supervision,
        # association
        "managed_agents": managed_agents_payload,
        # keep existing model config in case PUT requires full object in your deployment
        "description": manager_def.get("description", ""),
        "features": manager_def.get("features", []),
        "tools": manager_def.get("tools", []),
        "llm_credential_id": manager_def.get("llm_credential_id", "lyzr_openai"),
        "provider_id": manager_def.get("provider_id", "OpenAI"),
        "model": manager_def.get("model", "gpt-4o-mini"),
        "top_p": manager_def.get("top_p", 0.9),
        "temperature": manager_def.get("temperature", 0.3),
        "response_format": manager_def.get("response_format", {"type": "json"}),
    }
    mgr_upd = update_agent(client, manager_id, manager_updates)
    if not mgr_upd.get("ok"):
        print(f"⚠️ PUT update failed for manager {manager_base_name}: {mgr_upd}")

    return {
        "agent_id": manager_id,
        "name": manager_renamed,
        "roles": created_roles,
        "timestamp": _timestamp_str(),
    }
