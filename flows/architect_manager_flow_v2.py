from prefect import flow, task
from src.api.client import LyzrAPIClient
from src.utils.yaml_tools import validate_yaml_schema

client = LyzrAPIClient()

@task
def generate_yaml(agent_description: str) -> str:
    """Use a Lyzr YAML Generator agent to create YAML definition."""
    # call your existing YAML_GEN agent or LLM
    yaml_def = client.call_agent("YAML_GEN_v1", {"message": agent_description})
    return yaml_def["yaml"]

@task
def validate_yaml(yaml_def: str) -> dict:
    """Validate YAML against schema before creation."""
    return validate_yaml_schema(yaml_def)

@task
def create_agent(yaml_def: dict) -> str:
    """Create agent in Lyzr via API and return agent_id."""
    resp = client.create_agent_from_yaml(yaml_def)
    return resp["agent_id"]

@task
def test_agent(agent_id: str) -> bool:
    """Run a sample test call against the new agent."""
    resp = client.call_agent(agent_id, {"message": "Hello"})
    return "Hello" in resp["output"]

@flow
def agent_factory_flow(agent_description: str):
    yaml_def = generate_yaml(agent_description)
    validated = validate_yaml(yaml_def)
    
    if validated["ok"]:
        agent_id = create_agent(validated["yaml"])
        success = test_agent(agent_id)
        
        if success:
            print(f"✅ Agent {agent_id} created and validated!")
        else:
            print(f"⚠️ Agent {agent_id} created but test failed.")
    else:
        print("❌ YAML validation failed")

if __name__ == "__main__":
    agent_factory_flow("Create a chatbot agent that helps HR answer employee benefits questions")
