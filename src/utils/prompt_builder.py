def build_system_prompt(agent_yaml: dict) -> str:
    """
    Merge agent_role, agent_goal, agent_instructions, and examples into a single system_prompt.
    """
    role = agent_yaml.get("agent_role", "")
    goal = agent_yaml.get("agent_goal", "")
    instr = agent_yaml.get("agent_instructions", "")
    examples = agent_yaml.get("examples", "")

    parts = []
    if role:
        parts.append(f"ROLE:\n{role.strip()}")
    if goal:
        parts.append(f"GOAL:\n{goal.strip()}")
    if instr:
        parts.append(f"INSTRUCTIONS:\n{instr.strip()}")
    if examples:
        parts.append(f"EXAMPLES:\n{examples}")

    return "\n\n".join(parts).strip()
