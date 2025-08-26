import argparse
import json
from src.api.client import LyzrAPIClient

def main():
    parser = argparse.ArgumentParser(description="Run an Agent by ID")
    parser.add_argument("agent_id", help="ID of the agent to run")
    parser.add_argument("message", help="Message to send to the agent")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    client = LyzrAPIClient(debug=args.debug)
    payload = {
        "user_id": "demo-user",
        "session_id": "demo-session",
        "message": args.message,
        "model": "gpt-4o-mini"
    }

    resp = client.request("POST", f"/v3/agents/{args.agent_id}/execute", json_body=payload)
    print("✅ Agent Response:")
    print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    main()
