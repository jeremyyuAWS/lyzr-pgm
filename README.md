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
│   ├── create_agent.py           # Create a single agent from YAML
│   ├── create_manager.py         # Create manager agent with role(s) from YAML
│   ├── create_manager_from_yaml.py# ✅ Create manager directly from generated output YAML
│   ├── run_agent.py              # Run inference on an agent by ID
│   ├── run_list_iterate.py       # Run a manager across list of use cases
│   ├── parse_json_to_yaml.py     # Parse manager JSON → role YAMLs
│   ├── list_agents.py            # List all existing agents
│   ├── delete_agents.py          # Delete all agents (with dry-run mode)
│   ├── runme.py                  # Batch runner (uses UPDATEME.yaml)
```

---

## ⚙️ Setup

1. **Clone repo & install dependencies**

   ```bash
   git clone https://github.com/jeremyyuAWS/lyzr-pgm
   cd lyzr-pgm
   pip install -r requirements.txt
   ```

2. **Configure API key**
   Add your Lyzr API key to `.env`:

   ```bash
   echo 'LYZR_API_KEY=sk-default-xxxxxxx' >> .env
   ```

   Optional: turn on debug logging

   ```bash
   echo 'LYZR_DEBUG=1' >> .env
   ```

---

## 🚀 Usage

### 🔹 Create Agents

**Create a single Role agent**

```bash
python -m scripts.create_agent agents/roles/YAML_COMPOSER_ROLE.yaml --debug
```

**Create a Manager agent with its Roles (auto-linked)**

```bash
python -m scripts.create_manager agents/managers/kyc_manager.yaml --debug
```

---

### 🔹 Create Manager From Generated YAML (Best for Iteration)

Often when you run an inference (via `run_list_iterate` or `parse_json_to_yaml`) you’ll get an **output YAML** that already contains the manager definition.
To create that manager directly:

```bash
python -m scripts.create_manager_from_yaml output/YAML_COMPOSER_MANAGER_v1/hr_helpdesk_agent/HR_Helpdesk_Manager_v1.yaml
```

**With debug + user override:**

```bash
LYZR_DEBUG=1 LYZR_USER_ID="jeremyyu@lyzr.ai" \
python -m scripts.create_manager_from_yaml output/YAML_COMPOSER_MANAGER_v1/hr_helpdesk_agent/HR_Helpdesk_Manager_v1.yaml
```

This is the **fastest way to validate new YAML definitions** since it bypasses re-running the whole workflow.

---

### 🔹 Run / Test Agents

**Run an agent by ID**

```bash
python -m scripts.run_agent 68ac92f41425de516e43e6e2 "Start KYC process"
```

---

### 🔹 Run Manager Across Use Cases (Recommended)

**Example:**

```bash
python -m scripts.run_list_iterate agents/managers/YAML_COMPOSER_MANAGER_v1.yaml agents/use_cases_hr.yaml
```

That will:

1. Create the manager + roles
2. Iterate over use cases in `use_cases_hr.yaml`
3. Retry failed cases automatically
4. Save outputs to `output/<manager>/<usecase>/`

#### Controlling JSON Output

* **No JSON saved (default):**

  ```bash
  python -m scripts.run_list_iterate agents/managers/YAML_COMPOSER_MANAGER_v1.yaml agents/use_cases_hr.yaml
  ```

* **Save JSON (CLI flag):**

  ```bash
  python -m scripts.run_list_iterate agents/managers/YAML_COMPOSER_MANAGER_v1.yaml agents/use_cases_hr.yaml --save
  ```

* **Save JSON (env var):**

  ```bash
  SAVE_OUTPUTS=1 python -m scripts.run_list_iterate agents/managers/YAML_COMPOSER_MANAGER_v1.yaml agents/use_cases_hr.yaml
  ```

---

### 🔹 Parse / Generate YAMLs

```bash
python -m scripts.parse_json_to_yaml manager_response.json --output_dir agents/roles
```

---

### 🔹 List / Delete Agents

```bash
python -m scripts.list_agents
python -m scripts.delete_agents --dry-run
python -m scripts.delete_agents
```

---

### 🔹 Debug with Raw cURL

```bash
curl --request POST \
  --url https://agent-prod.studio.lyzr.ai/v3/agents/ \
  --header "Content-Type: application/json" \
  --header "x-api-key: $LYZR_API_KEY" \
  --data '{
    "name": "TestAgent",
    "description": "Quick test agent",
    "system_prompt": "You are a test agent",
    "provider_id": "OpenAI",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "top_p": 0.9,
    "features": [],
    "tools": [],
    "response_format": {"type": "json"}
  }'
```

---

## 🧰 Development Notes

* Agent names are stamped with **agent\_id + local date + timezone**.
* `payload_normalizer.py` enforces API schema.
* `run_list_iterate.py` is the best way to test multiple use cases.
* Use `create_manager_from_yaml` to **instantiate a manager directly from generated YAML output**.
