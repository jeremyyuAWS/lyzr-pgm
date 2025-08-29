# Lyzr Agent Manager

This repo contains utilities and scripts for **creating, managing, running, and linking Lyzr agents** (both Role agents and Manager agents) from YAML definitions.

It ensures consistent payload formatting for the Lyzr API and provides automation for creating and linking manager agents with their subordinate role agents.

---

## 📦 Project Structure

```
.
├── agents/                 
│   ├── managers/           # Manager agent YAMLs
│   └── roles/              # Role agent YAMLs
├── scripts/                
│   ├── create_agent.py            # Create a single agent from YAML
│   ├── create_manager.py          # Create manager agent with role(s) from YAML
│   ├── create_manager_from_yaml.py# ✅ Create manager directly from generated output YAML
│   ├── create_from_output.py      # ⭐⭐ Recursively create Managers + Workflows from output folder
│   ├── run_agent.py               # Run inference on an agent by ID
│   ├── run_list_iterate.py        # ⭐⭐ Run a manager across list of use cases
│   ├── parse_json_to_yaml.py      # Parse manager JSON → role YAMLs
│   ├── list_agents.py             # List all existing agents
│   ├── delete_agents.py           # Delete all agents (with dry-run mode)
│   ├── runme.py                   # Batch runner (uses UPDATEME.yaml)
```

---

## 🚀 Usage

### 🔹 Create Agents

...

---

### 🔭 Create From Output (Managers + Workflows in Bulk)

If you have an **output folder** containing multiple subfolders (each with a `*Manager*.yaml` and `workflow_*.yaml`), you can auto-create them all:

```bash
python -m scripts.create_from_output output/YAML_COMPOSER_MANAGER_v1 --debug
```

This will:

1. Recursively scan all subfolders under `output/YAML_COMPOSER_MANAGER_v1/`
2. For each subfolder:

   * Create the Manager agent (and its Roles) from `*Manager*.yaml`
   * Create the Workflow from the latest `workflow_*.yaml`
3. Print results (✅ success, ❌ failure) in sequence

Example output:

```
📂 Processing subfolder: output/YAML_COMPOSER_MANAGER_v1/hr_helpdesk_agent
🚀 Creating Manager + Roles from HR_Helpdesk_Manager_v1.yaml
✅ Manager created: HR_Helpdesk_Manager_v1 (id=68b...e4)
🚀 Creating Workflow from workflow_20250828_202636.yaml
✅ Workflow created: HR Helpdesk Flow (id=215...c7)
```
