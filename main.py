from fastapi import FastAPI
from pydantic import BaseModel
from src.api.client import LyzrAPIClient

app = FastAPI()

class AgentActionRequest(BaseModel):
    action: str
    api_key: str = None
    agent_id: str = None
    payload: dict = None

@app.post("/agent-action/")
async def agent_action(req: AgentActionRequest):
    client = LyzrAPIClient(api_key=req.api_key)

    if req.action == "list_agents":
        result = client.list_agents()
        return {"ok": True, "agents": result}

    elif req.action == "delete_agent" and req.agent_id:
        result = client.delete_agent(req.agent_id)
        return {"ok": True, "deleted": req.agent_id, "response": result}

    elif req.action == "delete_all_agents":
        result = client.delete_all_agents()
        return {"ok": True, "response": result}

    elif req.action == "create_agent" and req.payload:
        result = client.create_agent(req.payload)
        return {"ok": True, "response": result}

    else:
        return {"ok": False, "error": "Unknown action or missing params"}
