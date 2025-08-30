// src/services/api.ts
export interface AgentActionRequest {
  agent_id: string;
  message: string;
}

export async function runInference(body: AgentActionRequest) {
  const token = (await supabase.auth.getSession()).data.session?.access_token;
  const resp = await fetch(`${API_BASE_URL}/agent-action/`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  });
  return resp.json();
}
