# backend/schemas/agent_action.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict

class AgentActionRequest(BaseModel):
    file: str = Field(..., description="YAML content or path to the manager/role agent file")
    name: Optional[str] = Field(None, description="Optional agent name")
    description: Optional[str] = Field(None, description="Optional description of the agent or workflow")
    type: Optional[str] = Field("manager", description="Type of agent being created: 'manager' or 'role'")
    metadata: Optional[Dict[str, str]] = Field(default_factory=dict, description="Additional metadata or tags")

    class Config:
        schema_extra = {
            "example": {
                "file": "name: MyAgent\nagent_role: assistant\nagent_goal: Help with tasks\n...",
                "name": "MyAgent",
                "description": "Assistant agent to handle support queries",
                "type": "manager",
                "metadata": {"project": "demo", "version": "v1"}
            }
        }
