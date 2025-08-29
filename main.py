import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from src.api.client import LyzrAPIClient

app = FastAPI(title="Lyzr PGM API")

# Allow frontend + Studio
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AgentActionRequest(BaseModel):
    action: str
    api_key: str | None = None
    agent_id: str | None = None
    message: str | None = None
    yaml_input: str | None = None

@app.get("/")
def root():
    return {"ok": True, "message": "Welcome to Lyzr PGM API"}

@app.get("/health")
def health_check():
    return {"ok": True, "message": "FastAPI backend is healthy"}

@app.post("/agent-action/")
def agent_action(req: AgentActionRequest):
    if not req.api_key:
        raise HTTPException(status_code=400, detail="api_key is required")

    client = LyzrAPIClient(api_key=req.api_key)

    try:
        if req.action == "list_agents":
            return {"ok": True, "agents": client.list_agents()}

        elif req.action == "delete_all_agents":
            return {"ok": True, "response": client.delete_all_agents()}

        elif req.action == "delete_agent" and req.agent_id:
            return {"ok": True, "response": client.delete_agent(req.agent_id)}

        elif req.action == "run_inference" and req.agent_id and req.message:
            return {"ok": True, "response": client.run_inference(req.agent_id, req.message)}

        elif req.action == "create_agent_from_yaml" and req.yaml_input:
            return {"ok": True, "response": client.create_agent_from_yaml(req.yaml_input, is_path=False)}

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action or missing params: {req.action}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
