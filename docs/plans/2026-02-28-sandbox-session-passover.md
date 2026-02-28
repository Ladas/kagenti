# Sandbox Session Passover — 2026-02-28 (Final)

## Session Stats
- Duration: ~8 hours across Feb 27-28
- Cost: ~$250 (Opus 4.6)
- Code: ~4500 lines added, ~450 removed, 25+ commits
- Tests: 12/12 Playwright + 4/4 variant tests passing
- Agent rebuild: Pending (Shipwright build for new serializer)

## Critical Blocker: Agent Serializer Not Deployed

The LangGraphSerializer (`event_serializer.py`) is committed and pushed to `agent-examples` repo but the Shipwright build keeps failing:
- `sandbox-agent-rebuild-wscqc`: BuildRunTimeout
- `sandbox-agent-rebuild-tcgm5`: TaskRunImagePullFailed (Red Hat Registry 500)
- `sandbox-agent-rebuild-f88j9`: Currently running

**Impact**: Without the serializer deployed, the agent still emits old-format Python repr, tool calls are partially parsed by regex, and the full LLM thinking + tool call chain is not visible.

**Fix**: Wait for build to succeed, then restart all sandbox deployments.

## What's Working (Verified with Tests)

| Feature | Tests | Status |
|---------|-------|--------|
| Multi-turn conversations (6 messages) | 1 test | PASS |
| Session isolation (A/B don't leak) | 3 tests | PASS |
| Session persistence (localStorage) | 1 test | PASS |
| Agent variant switching (4 variants) | 4 tests | PASS |
| Username identity ("admin (you)") | 1 test | PASS |
| Session switching shows correct history | 1 test | PASS |
| HITL event rendering (mocked SSE) | 1 test | PASS |

## What's Built But Needs Agent Rebuild

| Feature | Code Location | Blocked By |
|---------|---------------|------------|
| Structured JSON events | agent-examples/event_serializer.py | Agent build |
| LLM thinking with tool calls | agent-examples/event_serializer.py | Agent build |
| Pool recycle (DB connection fix) | agent-examples/agent.py | Agent build |
| Streaming tool call display | ui-v2/src/pages/SandboxPage.tsx | Agent build |

## What's Built And Deployed

| Feature | Location |
|---------|----------|
| JSON-first backend parser | sandbox.py:_parse_graph_event |
| Old-format regex (5 bugs fixed) | sandbox.py:_parse_graph_event |
| History aggregation across A2A tasks | sandbox.py:get_session_history |
| Artifact deduplication | sandbox.py:get_session_history |
| HITL approve/deny buttons (stub) | sandbox.py + SandboxPage.tsx |
| Wizard security contexts | sandbox_deploy.py |
| Wizard credential handling | sandbox_deploy.py + kubernetes.py |
| Multi-user per-message identity | sandbox.py + SandboxPage.tsx |
| Agent selector panel | SandboxAgentsPanel.tsx |
| SSE reconnect with backoff | SandboxPage.tsx |
| Route timeout 120s | kagenti-api + kagenti-ui routes |
| Session orchestration design | docs/plans/2026-02-27-session-orchestration-design.md |

## Sub-Plans for Next Sessions

### Sub-Plan 1: Agent Serializer Deploy + Verify (30 min)
**Goal**: Get the LangGraphSerializer deployed and verified with tests.
```bash
# 1. Wait for/retry the Shipwright build
KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig kubectl -n team1 get buildrun --sort-by=.metadata.creationTimestamp | tail -3

# 2. If failed, retry:
KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig kubectl -n team1 create -f - <<EOF
apiVersion: shipwright.io/v1beta1
kind: BuildRun
metadata:
  generateName: sandbox-agent-rebuild-
  namespace: team1
spec:
  build:
    name: sandbox-agent
  timeout: 20m
EOF

# 3. After success, restart all agents:
KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig kubectl -n team1 rollout restart deployment/sandbox-agent deployment/sandbox-legion deployment/sandbox-hardened deployment/sandbox-basic deployment/sandbox-restricted

# 4. Verify serializer is in image:
KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig kubectl -n team1 exec deploy/sandbox-legion -c agent -- ls /app/src/sandbox_agent/event_serializer.py

# 5. Run rendering test:
cd .worktrees/sandbox-agent/kagenti/ui-v2
KAGENTI_UI_URL=https://kagenti-ui-kagenti-system.apps.kagenti-team-sbox.octo-emerging.redhataicoe.com npx playwright test sandbox-rendering.spec.ts --workers=1
```

### Sub-Plan 2: Tool Call Rendering Polish (1 hour)
**Goal**: Tool calls render as expandable blocks during live streaming and in loaded history.
- Fix: streaming handler collects JSON events from `data.event.message`
- Fix: history endpoint returns parsed tool call data
- Test: sandbox-rendering.spec.ts 4 tests should all pass
- Iterate until all 4 rendering tests pass

### Sub-Plan 3: HITL Integration (2 hours)
**Goal**: Wire approve/deny buttons to actually resume the LangGraph graph.
- Agent: resume endpoint that calls `graph.astream()` with approval response
- Backend: approve/deny endpoints forward to agent
- Frontend: buttons already exist with callbacks
- Test: send dangerous command, verify approval card appears, click approve, verify command executes

### Sub-Plan 4: Sub-Agent Delegation (3 hours)
**Goal**: Main agent can spawn child sessions via delegate tool.
- Agent: wire `make_delegate_tool()` to create SandboxClaim with parent_context_id
- Backend: no changes needed (metadata stored automatically)
- Frontend: sidebar shows child sessions indented under parent
- Test: trigger delegation, verify child session appears under parent

### Sub-Plan 5: Automated Passover (3 hours)
**Goal**: Agent detects context rot and creates passover session.
- Agent: context_monitor node checks token count after each tool cycle
- Agent: passover_node generates summary and creates new session
- Backend: passover chain API endpoint
- Frontend: passover notice in chat, chain visualization

### Sub-Plan 6: Multi-User E2E Test (1 hour)
**Goal**: Two different Keycloak users chat in the same session.
- Create dev-user in Keycloak with operator role
- Playwright test: admin sends message, verify "admin (you)" label
- Playwright test: dev-user sends message to same session, verify "dev-user" label
- Verify visibility toggle (private/namespace)

## Clusters
| Cluster | Status | Kubeconfig |
|---------|--------|-----------|
| kagenti-team-sbox | Active, all fixes deployed | ~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig |
| kagenti-team-sbox1 | Active, needs redeploy | Kubeconfig may be expired |

## Startup
```bash
cd /Users/ladas/Projects/OCTO/kagenti/kagenti
export MANAGED_BY_TAG=kagenti-team
source .env.kagenti-team
export KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig
export PATH="/opt/homebrew/opt/helm@3/bin:$PATH"
claude
```

Read `docs/plans/2026-02-28-sandbox-session-passover.md`. Start with Sub-Plan 1 (agent serializer deploy). Then Sub-Plan 2 (tool call rendering). Use /tdd:hypershift for iteration.
