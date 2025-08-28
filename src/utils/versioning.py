# src/utils/versioning.py

import re
from datetime import datetime
import pytz
from tzlocal import get_localzone
from typing import List, Dict, Optional

# detect local timezone once
try:
    LOCAL_TZ = get_localzone()
except Exception:
    LOCAL_TZ = pytz.UTC


def extract_base_name(agent_name: str) -> str:
    """Strip off trailing version suffix (.N) from an agent name."""
    return re.split(r'\.\d+$', agent_name)[0]


def parse_version(agent_name: str, base: str) -> Optional[float]:
    """Parse numeric version suffix if matches the base (e.g., 1.3, 2.12)."""
    pattern = rf"^{re.escape(base)}\.(\d+)$"
    m = re.match(pattern, agent_name)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def get_next_version(existing_agents: List[Dict], base: str) -> float:
    """Find the highest version for the base name and return the next one."""
    versions = []
    for a in existing_agents:
        name = a.get("name", "")
        v = parse_version(name, base)
        if v is not None:
            versions.append(v)
    return max(versions) + 1 if versions else 1.0


def generate_new_name(existing_agents: List[Dict], yaml_name: str, agent_id: str = None) -> str:
    """
    Generate a new agent name based on YAML name + version bump,
    and optionally append `[id | timestamp]`.

    Example:
        yaml_name: ARCHITECT_MANAGER_v1.3
        existing:  v1.1, v1.2, v1.3
        → ARCHITECT_MANAGER_v1.4 [68abc123 | 2025-08-28 02:45 PM PST]
    """
    base = extract_base_name(yaml_name)
    next_v = get_next_version(existing_agents, base)

    versioned = f"{base}.{next_v:.2f}".rstrip("0").rstrip(".")
    if agent_id:
        now_local = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %I:%M %p %Z")
        return f"{versioned} [{agent_id} | {now_local}]"
    return versioned
