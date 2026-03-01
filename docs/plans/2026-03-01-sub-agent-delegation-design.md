# Sub-Agent Delegation Design

> **Date:** 2026-03-01
> **Session:** C (HITL & Integrations)
> **Status:** Design complete, implementation pending

## Goal

Implement the `delegate` tool so a parent sandbox agent can spawn child agents
via SandboxClaim CRDs, with `parent_context_id` tracking through A2A metadata.
Bridge the Integrations Hub triggers (cron, webhook, alert) to this mechanism.

## Architecture

```
Integrations Hub          Sandbox Agent System
─────────────────         ─────────────────────

Integration CRD           Parent Agent (LangGraph)
  ├─ webhooks ──┐         │
  ├─ schedules ─┤─────►   delegate(task, config)
  └─ alerts ────┘            │
                             ├─ Generate child context_id
                             ├─ Build A2A message with metadata:
                             │    parent_context_id: <parent>
                             │    session_type: "child"
                             │    trigger_source: "webhook|cron|alert"
                             │
                             ├─ Create SandboxClaim CRD ──► K8s
                             │                              │
                             │                    Agent Pod spawns
                             │                              │
                             └─ Send A2A message ───────► Child Agent
                                                           │
                                Poll / stream results ◄────┘
```

## What's Already Built

| Component | Status | Location |
|-----------|--------|----------|
| `explore` tool (in-process) | Working | `subagents.py:make_explore_tool()` |
| `delegate` tool | Placeholder | `subagents.py:make_delegate_tool()` |
| Frontend `parent_context_id` | Reads but never set | `SessionSidebar.tsx` |
| SandboxClaim creation | In triggers.py | `deployments/sandbox/triggers.py` |
| Integration CRD | Deployed | `charts/kagenti/templates/integration-crd.yaml` |
| Integrations API | Deployed | `backend/app/routers/integrations.py` |
| Session orchestration design | 685-line doc | `docs/plans/2026-02-27-session-orchestration-design.md` |

## Implementation Plan

### Phase 1: Populate parent_context_id (P2 — no cluster needed)

**Files to modify:**
- `sandbox_agent/src/sandbox_agent/subagents.py` — implement `delegate` tool
- `kagenti/backend/app/routers/sandbox.py` — passover chain API endpoint

**delegate tool implementation:**

```python
def make_delegate_tool(
    parent_context_id: str,
    namespace: str,
    kube_client: Optional[Any] = None,
) -> Any:
    @tool
    async def delegate(
        task: str,
        variant: str = "sandbox-legion",
        timeout_minutes: int = 30,
    ) -> str:
        """Spawn a child sandbox agent for a delegated task.

        Use for tasks that need isolation, different permissions, or
        long-running work that shouldn't block the current session.
        """
        child_context_id = f"child-{uuid.uuid4().hex[:12]}"

        # 1. Create SandboxClaim
        claim = {
            "apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
            "kind": "SandboxClaim",
            "metadata": {
                "name": child_context_id,
                "namespace": namespace,
                "labels": {
                    "kagenti.io/parent-context": parent_context_id,
                    "kagenti.io/session-type": "child",
                },
            },
            "spec": {
                "sandboxTemplateRef": {"name": variant},
                "lifecycle": {
                    "shutdownPolicy": "Delete",
                    "shutdownTime": (
                        datetime.now(timezone.utc)
                        + timedelta(minutes=timeout_minutes)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            },
        }

        if kube_client:
            kube_client.create_namespaced_custom_object(
                group="extensions.agents.x-k8s.io",
                version="v1alpha1",
                namespace=namespace,
                plural="sandboxclaims",
                body=claim,
            )
        else:
            # Fallback: kubectl apply
            subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=json.dumps(claim),
                capture_output=True, text=True,
            )

        # 2. Send A2A message with parent_context_id metadata
        a2a_message = {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": task}],
            },
            "metadata": {
                "parent_context_id": parent_context_id,
                "session_type": "child",
                "child_context_id": child_context_id,
            },
        }

        # 3. Wait for pod to be ready, then send message
        # (polling with backoff — pod takes 30-60s to start)
        agent_url = f"http://{variant}.{namespace}.svc.cluster.local:8000"
        # ... send A2A message, poll for result ...

        return f"Delegated to child session {child_context_id}"

    return delegate
```

### Phase 2: Passover chain API (P2)

**New endpoint in `sandbox.py`:**

```
GET /api/v1/sandbox/{namespace}/sessions/{context_id}/chain
```

Returns the full session lineage by traversing `parent_context_id` and
`passover_from`/`passover_to` pointers:

```json
{
  "root": "ctx-abc123",
  "chain": [
    {"context_id": "ctx-abc123", "type": "root", "status": "completed"},
    {"context_id": "child-def456", "type": "child", "parent": "ctx-abc123", "status": "running"},
    {"context_id": "ctx-ghi789", "type": "passover", "from": "ctx-abc123", "status": "active"}
  ]
}
```

**Implementation:** Query tasks table where `metadata->parent_context_id = context_id`
or `metadata->passover_from = context_id`.

### Phase 3: Integration triggers → delegate (P2)

**Bridge endpoint:**

```
POST /api/v1/integrations/{namespace}/{name}/webhook
```

When a GitHub webhook fires:
1. Backend receives webhook payload
2. Looks up Integration CRD for the repo
3. Resolves assigned agent(s)
4. Creates A2A message with trigger metadata:
   ```json
   {
     "message": {"role": "user", "parts": [{"text": "PR #42 opened: <title>\n<body>"}]},
     "metadata": {
       "session_type": "trigger",
       "trigger_source": "webhook",
       "trigger_event": "pull_request.opened",
       "trigger_repo": "kagenti/kagenti",
       "trigger_pr": 42
     }
   }
   ```
5. Sends to assigned agent's A2A endpoint

This reuses the existing sandbox agent infrastructure — no new CRDs needed
beyond Integration (already deployed) and SandboxClaim (exists in triggers.py).

### Phase 4: Context monitor / automated passover (P3)

Designed in session-orchestration-design.md. Implementation deferred.

## Data Flow: Webhook → Agent

```
GitHub                  Kagenti Backend           Agent Pod
──────                  ───────────────           ─────────
PR opened
  │
  ├─ POST /webhook ──► integrations.py
                          │
                          ├─ Lookup Integration CRD
                          ├─ Find agent binding
                          ├─ Create SandboxClaim (if no pod running)
                          │     OR
                          ├─ Send A2A message to running agent
                          │
                          └──────────────────────► Agent receives task
                                                    │
                                                    ├─ Runs skill (e.g. tdd:ci)
                                                    ├─ Creates PR comment
                                                    └─ Reports via A2A status

```

## Dependencies

| Dependency | Owner | Status |
|-----------|-------|--------|
| SandboxClaim controller | Not assigned | Needed for pod provisioning |
| Agent pod A2A endpoint | Session B | Working (sandbox-legion deployed) |
| Integration CRD | Session C | Deployed |
| HITL resume | Session A + C | Partially blocked (OpenAI quota) |
| PostgreSQL task store | Session B | Working (psycopg driver) |

## Testing Plan

1. **Unit test**: `delegate` tool creates SandboxClaim with correct metadata
2. **Unit test**: Passover chain API traverses parent/child links
3. **Integration test**: Webhook → Integration → A2A message → agent response
4. **E2E test**: Full flow from GitHub webhook to agent PR comment
5. **Playwright test**: SessionSidebar shows child sessions under parent

## Files Changed

| File | Change | Owner |
|------|--------|-------|
| `subagents.py` | Implement `delegate` tool | Session C (via agent-examples) |
| `sandbox.py` | Add `/chain` endpoint | Session A (request via TODO) |
| `integrations.py` | Add `/webhook` endpoint | Session C |
| `SessionSidebar.tsx` | Show child session tree | Session A (request via TODO) |
