import os
import sys
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("LYZR_BASE_URL", "https://agent-prod.studio.lyzr.ai")
API_KEY = os.getenv("LYZR_API_KEY")

def run_inference(agent_id: str, message: str, session_id: str = None):
    if not session_id:
        session_id = f"{agent_id}-session1"

    payload = {
        "user_id": "demo-user",
        "agent_id": agent_id,
        "session_id": session_id,
        "message": message,
        "system_prompt_variables": {},
        "filter_variables": {}
    }

    headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}

    # 👇 Add timeout of 60s (can adjust if needed)
    r = httpx.post(
        f"{BASE_URL}/v3/inference/chat/",
        headers=headers,
        json=payload,
        timeout=60.0
    )
    r.raise_for_status()
    data = r.json()

    # Try parsing nested JSON if present
    try:
        parsed_inner = json.loads(data.get("response"))
        print("✅ Agent Response:")
        print(json.dumps(parsed_inner, indent=2))
    except Exception:
        print("Raw response:", data)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m scripts.run_inference <agent_id> <message>")
        sys.exit(1)

    agent_id = sys.argv[1]
    message = " ".join(sys.argv[2:])
    run_inference(agent_id, message)
