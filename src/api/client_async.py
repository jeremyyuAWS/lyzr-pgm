    async def link_agents(
        self,
        manager_id: str,
        role_id: str = None,
        role_name: str = None,
        rename_manager: bool = False,
    ):
        """
        Link a role agent to a manager agent by updating the manager's managed_agents list.
        Always PUT full payload back so no fields are lost.
        """
        # Fetch full manager state
        mgr_resp = await self.get(f"/v3/agents/{manager_id}")
        if not mgr_resp.get("ok"):
            return {"ok": False, "error": f"Failed to fetch manager: {mgr_resp}"}

        manager_data = mgr_resp["data"]
        manager_base_name = manager_data.get("name", "MANAGER")

        # Ensure list
        existing_roles = manager_data.get("managed_agents") or []

        if not rename_manager and role_id:
            # Append new role if not already present
            if not any(r.get("id") == role_id for r in existing_roles):
                existing_roles.append({
                    "id": role_id,
                    "name": role_name or role_id,
                    "usage_description": f"Manager delegates tasks to '{role_name or role_id}'."
                })

        # Compute name
        manager_renamed = manager_base_name
        if rename_manager:
            manager_renamed = _rich_manager_name(manager_base_name, manager_id)

        # Build full update payload (preserve everything)
        update_payload = {**manager_data, "name": manager_renamed, "managed_agents": existing_roles}

        upd_resp = await self.update_agent(manager_id, update_payload)

        if upd_resp.get("ok"):
            return {
                "ok": True,
                "linked": bool(role_id),
                "renamed": manager_renamed if rename_manager else None,
                "manager": upd_resp.get("data"),
                "roles": existing_roles,
                "timestamp": _timestamp_str() if rename_manager else None,
            }
        return {"ok": False, "linked": False, "error": upd_resp.get("error")}


    async def create_manager_with_roles(self, manager_def: dict):
        """
        Create a manager agent and its managed role agents.
        Always PUT full payload back so no fields are lost.
        """
        if not isinstance(manager_def, dict):
            return {"ok": False, "error": "Manager definition must be dict"}

        created_roles = []

        # --- Create roles first ---
        for entry in manager_def.get("managed_agents", []):
            try:
                role_payload = normalize_payload(entry)
                role_payload = self._validate_agent_payload(role_payload)
                role_resp = await self.create_agent(role_payload)
                if role_resp.get("ok"):
                    role_data = role_resp["data"]
                    created_roles.append(role_data)
            except Exception as e:
                self._log(f"❌ Failed to create role: {e}")

        # --- Create manager ---
        try:
            manager_payload = normalize_payload(manager_def)
            manager_payload = self._validate_agent_payload(manager_payload)

            mgr_resp = await self.create_agent(manager_payload)
            if not mgr_resp.get("ok"):
                return {"ok": False, "error": mgr_resp.get("error"), "roles": created_roles}

            manager = mgr_resp["data"]

            # --- Link roles if any ---
            if created_roles:
                # Fetch manager fresh
                mgr_fetched = await self.get(f"/v3/agents/{manager.get('id')}")
                if not mgr_fetched.get("ok"):
                    return {"ok": False, "error": f"Failed to fetch created manager: {mgr_fetched}"}

                manager_data = mgr_fetched["data"]

                # Attach roles fully
                manager_data["managed_agents"] = (manager_data.get("managed_agents") or []) + created_roles

                # PUT full payload
                upd_resp = await self.update_agent(manager["id"], manager_data)
                if upd_resp.get("ok"):
                    manager = upd_resp["data"]

            return {"ok": True, "manager": manager, "roles": created_roles}

        except Exception as e:
            return {"ok": False, "error": f"Manager creation failed: {e}", "roles": created_roles}