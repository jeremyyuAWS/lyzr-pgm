import yaml
import os

CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "../../config/llm_config.yaml"
)

def load_llm_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def get_default_params():
    cfg = load_llm_config()
    return {
        "provider_id": cfg.get("default_provider_id", "OpenAI"),
        "model": cfg.get("default_model", "gpt-4o-mini"),
        "top_p": cfg.get("default_top_p", 0.9),
        "temperature": cfg.get("default_temperature", 0.7),
        "llm_credential_id": cfg.get("default_llm_credential_id", "lyzr_openai"),
        "version": cfg.get("default_version", "3"),
    }
