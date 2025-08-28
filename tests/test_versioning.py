import os
import sys

# Make sure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.utils.versioning import next_version_name

# Fake client that mimics list_agents()
class FakeClient:
    def __init__(self, existing_names):
        self.existing_names = existing_names

    def get(self, path):
        # Only supports /v3/agents/
        if path == "/v3/agents/":
            return {
                "ok": True,
                "data": [{"name": n, "_id": f"id_{i}"} for i, n in enumerate(self.existing_names)]
            }
        return {"ok": False, "data": []}

def test_versioning():
    client = FakeClient([
        "ARCHITECT_MANAGER_v1.1",
        "ARCHITECT_MANAGER_v1.2",
        "ARCHITECT_MANAGER_v1.3",
    ])

    base_name = "ARCHITECT_MANAGER_v1"
    new_name = next_version_name(base_name, client)
    print(f"Next version for {base_name}: {new_name}")  # should be ARCHITECT_MANAGER_v1.4

if __name__ == "__main__":
    test_versioning()
