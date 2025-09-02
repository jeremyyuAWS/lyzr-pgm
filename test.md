curl https://lyzr-pgm.onrender.com/list-agents/ \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsImtpZCI6ImJzbzhwSFVaV0ZEK1piYkoiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2hlZHprcmZkZnhpY2Jta2VzZXhlLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI5M2IzMDhmMi03ZWZlLTQzY2MtYTM0Mi00YTc0NjNkM2IyYjgiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU2NjI0MjI3LCJpYXQiOjE3NTY2MjA2MjcsImVtYWlsIjoiamVyZW15QGx5enIuYWkiLCJwaG9uZSI6IiIsImFwcF9tZXRhZGF0YSI6eyJwcm92aWRlciI6ImVtYWlsIiwicHJvdmlkZXJzIjpbImVtYWlsIl19LCJ1c2VyX21ldGFkYXRhIjp7ImVtYWlsIjoiamVyZW15QGx5enIuYWkiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwicGhvbmVfdmVyaWZpZWQiOmZhbHNlLCJzdWIiOiI5M2IzMDhmMi03ZWZlLTQzY2MtYTM0Mi00YTc0NjNkM2IyYjgifSwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhYWwiOiJhYWwxIiwiYW1yIjpbeyJtZXRob2QiOiJwYXNzd29yZCIsInRpbWVzdGFtcCI6MTc1NjUwODIzOH1dLCJzZXNzaW9uX2lkIjoiNjgzMzI5NWEtZWI3My00MzBhLWEwZjEtMGQ3NGFiZGQyNDMzIiwiaXNfYW5vbnltb3VzIjpmYWxzZX0.fdlGIAKYaKKuxx6xo8Zowp9vvoLmoxCAkc8qEBMKR2M"

# Get JWT token
const { data: { session } } = await supabase.auth.getSession();
console.log("🔑 New JWT:", session?.access_token);


const { data: { session } } = await supabase.auth.getSession()
console.log(session.access_token)

# 1. Store your JWT token in an environment variable
export MY_TOKEN="eyJhbGciOiJIUzI1NiIsImtpZCI6ImJzbzhwSFVaV0ZEK1piYkoiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2hlZHprcmZkZnhpY2Jta2VzZXhlLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI5M2IzMDhmMi03ZWZlLTQzY2MtYTM0Mi00YTc0NjNkM2IyYjgiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU2NjI3NzI3LCJpYXQiOjE3NTY2MjQxMjcsImVtYWlsIjoiamVyZW15QGx5enIuYWkiLCJwaG9uZSI6IiIsImFwcF9tZXRhZGF0YSI6eyJwcm92aWRlciI6ImVtYWlsIiwicHJvdmlkZXJzIjpbImVtYWlsIl19LCJ1c2VyX21ldGFkYXRhIjp7ImVtYWlsIjoiamVyZW15QGx5enIuYWkiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwicGhvbmVfdmVyaWZpZWQiOmZhbHNlLCJzdWIiOiI5M2IzMDhmMi03ZWZlLTQzY2MtYTM0Mi00YTc0NjNkM2IyYjgifSwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhYWwiOiJhYWwxIiwiYW1yIjpbeyJtZXRob2QiOiJwYXNzd29yZCIsInRpbWVzdGFtcCI6MTc1NjUwODIzOH1dLCJzZXNzaW9uX2lkIjoiNjgzMzI5NWEtZWI3My00MzBhLWEwZjEtMGQ3NGFiZGQyNDMzIiwiaXNfYW5vbnltb3VzIjpmYWxzZX0.FmrDPx5-X2hxSjD_kwuKwt1muY9VSQCGH1z7hGdwzo0"

# 2. Use it in your curl commands
curl -X POST "https://lyzr-pgm.onrender.com/create-agents/" \
  -H "Authorization: Bearer $MY_TOKEN" \
  -F "file=@agents/managers/NEW_COMPOSER_MANAGER_V1.yaml"

curl -X POST "https://lyzr-pgm.onrender.com/run-use-cases/" \
  -H "Authorization: Bearer $MY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"manager_id": "68b3fb9a3134f53810d0af13"}'

1. HR Helpdesk
Employees often ask questions about payroll, benefits, and leave policies. Create an agent system where a Manager oversees query routing and a Role agent provides policy-specific answers.

2. IT Support
Employees frequently need help resetting passwords, troubleshooting VPN issues, and reinstalling approved software. Build an agent setup with a Manager orchestrating requests and a Role agent handling technical support tasks.

3. Finance Risk Monitoring
Financial teams want to detect unusual transactions and generate daily risk summaries. The Manager should coordinate monitoring tasks while a Role agent applies detection rules and reports anomalies.

4. Marketing Campaign Assistant
Marketing teams need help drafting campaign briefs and generating ad copy across channels. The Manager should manage campaign goals, while a Role agent drafts creative assets.

5. Sales Pipeline Tracker
Sales leadership wants an overview of opportunities by stage, with automated extraction from call notes. A Manager agent tracks pipeline health, while a Role agent parses meeting transcripts into deal updates.

6. Healthcare Patient Intake
Clinics need help collecting and validating patient intake forms. A Manager oversees the workflow, while a Role agent validates the data for completeness and flags missing fields.


export JWT_SECRET="eyJhbGciOiJIUzI1NiIsImtpZCI6ImJzbzhwSFVaV0ZEK1piYkoiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL2hlZHprcmZkZnhpY2Jta2VzZXhlLnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiI5M2IzMDhmMi03ZWZlLTQzY2MtYTM0Mi00YTc0NjNkM2IyYjgiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzU2ODU0MTE2LCJpYXQiOjE3NTY4NTA1MTYsImVtYWlsIjoiamVyZW15QGx5enIuYWkiLCJwaG9uZSI6IiIsImFwcF9tZXRhZGF0YSI6eyJwcm92aWRlciI6ImVtYWlsIiwicHJvdmlkZXJzIjpbImVtYWlsIl19LCJ1c2VyX21ldGFkYXRhIjp7ImVtYWlsIjoiamVyZW15QGx5enIuYWkiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwicGhvbmVfdmVyaWZpZWQiOmZhbHNlLCJzdWIiOiI5M2IzMDhmMi03ZWZlLTQzY2MtYTM0Mi00YTc0NjNkM2IyYjgifSwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhYWwiOiJhYWwxIiwiYW1yIjpbeyJtZXRob2QiOiJwYXNzd29yZCIsInRpbWVzdGFtcCI6MTc1Njc3NDk2MH1dLCJzZXNzaW9uX2lkIjoiNGEzNGFkZDMtNzQ5ZS00NTFjLThiN2UtMWRmYzk2YjQwZDM2IiwiaXNfYW5vbnltb3VzIjpmYWxzZX0.6u-8Zn2APCJzGFpconRqywpGoLM0BislWB_nQoLGwh4"

curl -X POST "https://lyzr-pgm.onrender.com/run-inference/" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer SUPABASE_JWT" \
  -d '{
    "agent_id": "68b7695c676823c8a6898e0a",
    "message": "Employees frequently need help resetting passwords, troubleshooting VPN issues, and reinstalling approved software. Build an agent setup with a Manager orchestrating requests and a Role agent handling technical support tasks.",
    "user_id": "jeremy@lyzr.ai",
    "system_prompt_variables": {},
    "filter_variables": {},
    "features": [],
    "assets": []
  }'



### List agents
curl --request GET \
  --url https://agent-prod.studio.lyzr.ai/v3/agents/ \
  --header "x-api-key: $LYZR_API_KEY" \
  --header "Content-Type: application/json"
