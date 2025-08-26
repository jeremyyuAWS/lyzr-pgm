# Lyzr Agent Manager

This repo contains utilities and scripts for **creating, managing, running, and linking Lyzr agents** (both Role agents and Manager agents) from YAML definitions.

It ensures consistent payload formatting for the Lyzr API and provides automation for creating and linking manager agents with their subordinate role agents.

---

## 📦 Project Structure

```
.
├── agents/                 # YAML definitions for agents
│   ├── managers/           # Manager agent YAMLs
│   └── roles/              # Role agent YAMLs
├── scripts/                # CLI scripts
│   ├── create_agent.py      # Create a single agent from YAML
│   ├── create_manager.py    # Create manager agent with role(s) from YAML
│   ├── run_agent.py         # Run inference on an agent by ID
│   ├── parse_json_to_yaml.py# Parse manager JSON → role YAMLs
│   ├── list_agents.py       # List all existing agents
│   ├── delete_agents.py     # Delete all agents (with dry-run mode)
│   ├── runme.py             # Run batch actions defined in UPDATEME.yaml
├── src/
│   ├── api/
│   │   └── client.py        # Lyzr API client (httpx wrapper)
│   ├── services/
│   │   └── agent_manager.py # Manager creation + linking roles
│   └── utils/
│       └── payload_normalizer.py
└── UPDATEME.yaml            # Config for which agents/workflows to create
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

or via batch runner (`UPDATEME.yaml`):

```bash
python -m scripts.runme
```

---

### 🔹 Run / Test Agents

**Run an agent by ID**

```bash
python -m scripts.run_agent 68ac92f41425de516e43e6e2 "Start KYC process"
```

---

### 🔹 Parse / Generate YAMLs

**Parse Manager JSON into Role YAMLs**

```bash
python -m scripts.parse_json_to_yaml manager_response.json --output_dir agents/roles
```

---

### 🔹 List / Delete Agents

**List all agents**

```bash
python -m scripts.list_agents
```

**Delete all agents (preview only)**

```bash
python -m scripts.delete_agents --dry-run
```

**Delete all agents (confirmed)**

```bash
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
    "features": [
      {"type": "yaml_syntax_validation", "config": {}, "priority": 0}
    ],
    "tools": [],
    "response_format": {"type": "json"}
  }'
```

---

## 🧰 Development Notes

* Agent names are automatically stamped with **agent\_id + local date + timezone** for traceability.
* `payload_normalizer.py` ensures YAML definitions always match the API schema.
* Debug logs print **payloads, responses, and retry logic** if `LYZR_DEBUG=1`.

---

## 👥 Contributing

* Add new Role YAMLs under `agents/roles/`
* Add new Manager YAMLs under `agents/managers/` and reference role YAMLs in `managed_agents`
* Update `UPDATEME.yaml` to control batch execution
