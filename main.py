import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.api.client import LyzrAPIClient
from src.services.agent_manager import AgentManager
from src.services.agent_runner import create_and_run  # wraps run_list_iterate logic

app = FastAPI(title="Lyzr Agent Orchestrator")

# ---------- Request Schema ----------
class AgentActionRequest(BaseModel):
    action: str  # "bulk_create_from_folder", "run_list_iterate", "list_agents", "delete_all_agents"
    folder: str | None = None
    yaml_file: str | None = None
    usecases_file: str | None = None
    save_outputs: bool = False
    push: bool = False


# ---------- Unified API Endpoint ----------
@app.post("/agent-action/")
def agent_action(req: AgentActionRequest):
    client = LyzrAPIClient()
    manager = AgentManager(client)

    try:
        # ----------------------------------------
        # Bulk create managers from a parent folder
        # ----------------------------------------
        if req.action == "bulk_create_from_folder":
            if not req.folder:
                raise HTTPException(400, detail="folder path required")

            parent = Path(req.folder)
            if not parent.exists() or not parent.is_dir():
                raise HTTPException(404, detail=f"Folder not found: {parent}")

            results = []
            for mgr_file in parent.rglob("*.yaml"):
                if "Manager" in mgr_file.stem or "Mgr" in mgr_file.stem:
                    print(f"📤 Creating Manager + Roles from {mgr_file}")
                    try:
                        result = manager.create_manager_with_roles(str(mgr_file))
                        if result:
                            results.append(result)
                    except Exception as e:
                        print(f"❌ Error processing {mgr_file}: {e}")

            return {"ok": True, "created_count": len(results), "created": results}

        # ----------------------------------------
        # Run manager across use cases (like run_list_iterate)
        # ----------------------------------------
        elif req.action == "run_list_iterate":
            if not req.yaml_file or not req.usecases_file:
                raise HTTPException(400, detail="yaml_file and usecases_file required")

            try:
                result = create_and_run(
                    req.yaml_file,
                    req.usecases_file,
                    save_outputs=req.save_outputs,
                    push=req.push
                )
                return {"ok": True, "result": result}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"run_list_iterate failed: {e}")

        # ----------------------------------------
        # List all agents
        # ----------------------------------------
        elif req.action == "list_agents":
            try:
                resp = client._request("GET", "/v3/agents")
                return {"ok": True, "agents": resp.get("data", [])}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"list_agents failed: {e}")

        # ----------------------------------------
        # Delete all agents
        # ----------------------------------------
        elif req.action == "delete_all_agents":
            try:
                resp = client._request("DELETE", "/v3/agents")
                return {"ok": True, "response": resp}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"delete_all_agents failed: {e}")

        else:
            raise HTTPException(400, detail=f"Unknown action: {req.action}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
