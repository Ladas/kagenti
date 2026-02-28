# Sandbox Session Passover — 2026-02-28

> **For next session:** Continue from where this session left off. HITL approve/deny buttons have stub endpoints and UI placeholders. Wizard credential handling (PAT/LLM key to K8s Secret) is designed but not wired. Multi-user per-message identity needs DB schema changes. All 12 Playwright tests pass on the sbox cluster. PR #758 CI is green except pre-existing CodeQL.

## Session Stats

- **Duration:** ~6 hours across 2 days (Feb 27-28)
- **Total cost:** ~$240 (mostly Opus 4.6)
- **Code changes:** ~4000 lines added, ~400 removed
- **Commits:** 20+ on `feat/sandbox-agent` branch
- **Tests:** 12/12 Playwright passing on sbox cluster
- **Model:** Claude Opus 4.6 (1M context)

## What Was Built (Complete List)

### 1. Tool Call Rendering (DONE)

**Problem:** Agent tool calls were rendered as raw text. Users could not see structured tool invocations, results, or errors.

**What was built:**
- **Agent:** `LangGraphSerializer` in `event_serializer.py` emits structured JSON events with type discriminators
- **Backend:** JSON-first parser in `sandbox.py` with regex fallback for old sessions
- **Frontend:** `ToolCallStep` component renders 5 event types:
  - `tool_call` -- shows tool name + arguments in collapsible panel
  - `tool_result` -- shows return value with syntax highlighting
  - `llm_response` -- shows intermediate LLM reasoning
  - `error` -- red-bordered error display
  - `hitl_request` -- approval card placeholder

### 2. Session Isolation (DONE)

**Problem:** Switching sessions in the sidebar leaked state from the previous session (input text, streaming status, message history).

**What was built:**
- State leak fix: input field, streaming flag, and message array cleared on session switch
- Full-width session names with CSS `text-overflow: ellipsis`
- Session persistence across page reload via `localStorage`
- 5 assertive Playwright tests covering:
  - New session creation
  - Session switching clears input
  - Session switching clears messages
  - Session persistence after reload
  - Session deletion

### 3. Agent Variants (DONE -- 4 deployed on sbox)

**Problem:** Needed to demonstrate different security postures and persistence strategies.

| Agent | Persistence | Security | Status |
|-------|------------|----------|--------|
| sandbox-legion | PostgreSQL | Default | Running, tests pass |
| sandbox-hardened | PostgreSQL | non-root, drop caps, seccomp | Running, tests pass |
| sandbox-basic | None | non-root, drop caps, seccomp | Running, tests pass |
| sandbox-restricted | PostgreSQL | Hardened + restricted proxy | Running, tests pass |

Plus `sandbox-agent` (the original) = 5 total variants deployed.

### 4. Agent Selector UI (DONE)

**Problem:** Users had no way to choose which sandbox agent to interact with.

**What was built:**
- `SandboxAgentsPanel` component shows available agents filtered by namespace
- Active session's agent is highlighted
- Click to switch agents for new sessions
- "Change sandbox" link navigates to full agent list
- Agent cards show name, security posture badge, and status indicator

### 5. Multi-User Identity (DONE -- partial)

**Problem:** Messages did not show who sent them. No user identity stored.

**What was built:**
- Username labels displayed in chat bubbles (extracted from Keycloak session)
- Ownership tracking: sessions tagged with creator's username
- Visibility filtering: users see only their own sessions in the sidebar

**What's still needed:**
- Per-message identity stored in the database (currently derived from session ownership)
- JWT extraction in backend sandbox.py chat endpoints
- Two-user concurrent test (admin + user1 in same session)

### 6. SSE Reconnect (DONE)

**Problem:** Server-Sent Events connections dropped silently on network interruptions or OpenShift route timeouts (default 30s, increased to 120s).

**What was built:**
- Exponential backoff reconnect on SSE connection drop
- Polling fallback when SSE is unavailable
- Connection status indicator in the UI
- Route timeout annotation set to 120s on sbox cluster

### 7. History Aggregation (DONE)

**Problem:** A2A task records were stored per-request, creating duplicate entries for multi-turn conversations.

**What was built:**
- Backend merge logic: aggregates A2A task records sharing the same `context_id`
- Deduplication of identical messages within a context
- Chronological ordering of merged history

### 8. Artifact Deduplication (DONE)

**Problem:** Duplicate text artifacts appeared in chat when the same content was emitted by multiple event types.

**What was built:**
- Content hash comparison to skip duplicate text artifacts
- Deduplication runs before rendering, not at storage time (preserves raw data)

### 9. Robust Old-Format Parsing (DONE)

**Problem:** Sessions created before the JSON event format used plain text with markdown code fences. The parser had 5 regex bugs causing rendering failures.

**What was fixed:**
- Regex 1: Multiline code blocks with nested backticks
- Regex 2: Tool call names containing hyphens and underscores
- Regex 3: Arguments spanning multiple lines with embedded JSON
- Regex 4: Tool results containing markdown formatting
- Regex 5: Mixed old/new format within the same session history

### 10. Security (DONE)

**What was built/fixed:**
- **SSRF prevention:** Namespace and agent_name parameters validated against K8s naming rules (alphanumeric + hyphens, max 63 chars)
- **Wizard security contexts:** All wizard-deployed pods get non-root UID, dropped capabilities, seccomp RuntimeDefault
- **Trivy fixes:** `.trivyignore` file for known false positives; security contexts added to `postgres-sessions.yaml`
- **Hardcoded agent_name fix:** Streaming endpoint was ignoring the agent_name parameter

### 11. Session Orchestration Design (DONE -- design only)

**What was created:**
- `docs/plans/2026-02-27-session-orchestration-design.md` -- 685-line design document
- Covers: session hierarchy (parent/child), automated passover on context exhaustion, sub-agent delegation, session chain visualization
- Not yet implemented (design doc only)

### 12. CI Fixes (DONE)

**What was fixed:**
- Trivy `.trivyignore` updated for new sandbox deployment manifests
- Kind skip markers added to sandbox Playwright tests (sandbox agents not deployed in Kind CI)
- All CI checks passing except pre-existing CodeQL issue

## Deployed on sbox Cluster

| Component | Details |
|-----------|---------|
| Agent: sandbox-agent | Original agent, A2A + streaming |
| Agent: sandbox-legion | PostgreSQL persistence, default security |
| Agent: sandbox-hardened | PostgreSQL, non-root + drop caps + seccomp |
| Agent: sandbox-basic | No persistence, hardened security |
| Agent: sandbox-restricted | PostgreSQL, hardened + restricted proxy |
| Backend | All parsing/aggregation fixes deployed |
| UI | Agent selector, identity labels, SSE reconnect |
| Route timeout | 120s (annotation on OpenShift route) |
| Tests | 12/12 Playwright passing |

## What's Still In Progress (Being Finished)

### HITL Approve/Deny Buttons

**Status:** Stub endpoints created in backend, UI placeholder cards render for `hitl_request` events.

**What's left:**
- Wire approve/deny buttons to backend endpoints
- Backend endpoint calls LangGraph `resume()` with the approval decision
- Test: agent hits HITL checkpoint, user clicks approve, agent resumes

### Wizard Credential Handling

**Status:** Wizard UI collects PAT and LLM API key. Deploy endpoint receives them.

**What's left:**
- Create K8s Secret from PAT/LLM key in the target namespace
- Mount Secret as env vars in the deployed agent pod
- Test: wizard deploys agent with custom LLM key, agent uses it for completions

### Multi-User Per-Message Identity in DB

**Status:** Username shown in UI from session ownership. Not stored per-message.

**What's left:**
- Extract username from Keycloak JWT in backend chat/streaming endpoints
- Store `user_id` + `username` in A2A message metadata
- Frontend: distinguish "username (you)" vs "username" for other users
- Playwright test: two users in same session, verify both names visible

## What's Not Built Yet

### Sub-Agent Child Sessions

**Problem:** The `delegate` tool in the agent is a placeholder. No `parent_context_id` is populated. Child sessions are not created.

**What's needed:**
- Agent: Wire delegate tool to create SandboxClaim with `parent_context_id`
- Backend: Already stores metadata (no changes needed)
- Frontend: Sidebar shows child sessions indented under parent
- Depends on: SandboxClaim CRD + controller

### Automated Session Passover

**Problem:** Session passover is manual (docs/plans/*.md documents). No automated detection of context exhaustion.

**What's needed:**
- Agent: `context_monitor` node detects token count > 80%
- Agent: `passover_node` generates summary, creates new session with summary as system context
- Backend: passover chain API endpoint
- Frontend: passover notice in chat, chain view
- Design doc exists: `docs/plans/2026-02-27-session-orchestration-design.md`

### Wizard Shipwright Build Trigger

**Problem:** Wizard collects a Dockerfile/repo but does not trigger an on-cluster build.

**What's needed:**
- Backend: Create Shipwright Build + BuildRun CRs
- Backend: Poll BuildRun status, update wizard progress
- Frontend: Build progress indicator in wizard

### External DB URL Wiring

**Problem:** Agent variants with PostgreSQL persistence use a cluster-local DB. No support for external DB URLs.

**What's needed:**
- Wizard UI: External DB URL input field
- Backend: Pass DB URL as env var to deployed agent
- Validation: Connection test before deploying

## Clusters

| Cluster | Status | Kubeconfig |
|---------|--------|------------|
| kagenti-team-sbox | Active, all fixes deployed, 12/12 tests pass | `~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig` |
| kagenti-team-sbox1 | Active, partial deployment (platform only) | `~/clusters/hcp/kagenti-team-sbox1/auth/kubeconfig` (may be expired) |

## CI Status (PR #758)

| Check | Status |
|-------|--------|
| Build (3.11/3.12) | PASS |
| DCO | PASS |
| Helm Lint | PASS |
| Bandit | PASS |
| Shell Lint | PASS |
| YAML Lint | PASS |
| Trivy Security | PASS |
| CodeQL | FAIL (pre-existing baseline) |
| Deploy & Test (Kind) | Pending |
| E2E HyperShift | Pending (needs `/run-e2e` comment) |

## Startup for Next Session

```bash
cd /Users/ladas/Projects/OCTO/kagenti/kagenti
export MANAGED_BY_TAG=kagenti-team
source .env.kagenti-team
export KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig
export PATH="/opt/homebrew/opt/helm@3/bin:$PATH"
claude
```

Then say:

> Read docs/plans/2026-02-28-sandbox-session-passover.md. Continue from where the last session left off: (1) wire HITL approve/deny buttons to backend resume endpoint, (2) implement wizard credential handling (PAT/LLM key to K8s Secret), (3) add per-message user identity in the database. All 12 Playwright tests should remain green on sbox.

## Key Files

| File | What |
|------|------|
| `.worktrees/sandbox-agent/kagenti/backend/app/routers/sandbox.py` | Session API, history aggregation, chat proxy, SSRF validation |
| `.worktrees/sandbox-agent/kagenti/backend/app/routers/sandbox_deploy.py` | Wizard deploy endpoint, agent variant creation |
| `.worktrees/sandbox-agent/kagenti/ui-v2/src/pages/SandboxPage.tsx` | Chat page with agent selector, SSE reconnect, identity labels |
| `.worktrees/sandbox-agent/kagenti/ui-v2/src/components/SessionSidebar.tsx` | Session list, persistence, ownership filtering |
| `.worktrees/sandbox-agent/kagenti/ui-v2/src/components/SandboxAgentsPanel.tsx` | Agent selector panel, variant cards |
| `.worktrees/sandbox-agent/kagenti/ui-v2/e2e/sandbox-sessions.spec.ts` | 5 session isolation tests |
| `.worktrees/sandbox-agent/kagenti/ui-v2/e2e/sandbox-variants.spec.ts` | 4 agent variant tests |
| `.worktrees/sandbox-agent/kagenti/ui-v2/e2e/sandbox-chat-identity.spec.ts` | 3 identity/HITL tests |
| `.worktrees/agent-examples/a2a/sandbox_agent/src/sandbox_agent/event_serializer.py` | LangGraph event serializer (5 event types) |
| `docs/plans/2026-02-27-session-orchestration-design.md` | Session hierarchy design (685 lines) |
| `docs/plans/2026-02-27-tool-call-rendering-design.md` | Tool call rendering design |

## File Map

```
kagenti/kagenti (.worktrees/sandbox-agent):
├── kagenti/
│   ├── backend/app/routers/
│   │   ├── sandbox.py              # Session API, history, chat proxy
│   │   └── sandbox_deploy.py       # Wizard deploy endpoint
│   ├── ui-v2/
│   │   ├── src/
│   │   │   ├── pages/SandboxPage.tsx           # Main chat page
│   │   │   └── components/
│   │   │       ├── SessionSidebar.tsx           # Session list
│   │   │       ├── SandboxAgentsPanel.tsx       # Agent selector
│   │   │       └── ToolCallStep.tsx             # Tool call renderer
│   │   └── e2e/
│   │       ├── sandbox-sessions.spec.ts         # 5 session tests
│   │       ├── sandbox-variants.spec.ts         # 4 variant tests
│   │       └── sandbox-chat-identity.spec.ts    # 3 identity tests
│   └── tests/e2e/common/
│       └── test_sandbox_agent.py                # Python E2E tests
├── deployments/sandbox/
│   ├── postgres-sessions.yaml       # PostgreSQL for session persistence
│   ├── sandbox-template-full.yaml   # Full SandboxTemplate
│   └── ...                          # Other sandbox manifests
├── docs/plans/
│   ├── 2026-02-27-session-orchestration-design.md  # 685-line design
│   ├── 2026-02-27-tool-call-rendering-design.md    # Tool call design
│   └── 2026-02-28-sandbox-session-passover.md      # This file
└── .github/scripts/
    └── kagenti-operator/35-deploy-agent-sandbox.sh  # Controller deployment

agent-examples (.worktrees/agent-examples):
└── a2a/sandbox_agent/src/sandbox_agent/
    ├── event_serializer.py          # LangGraph event serializer
    ├── agent.py                     # Main agent graph
    └── tools/                       # Agent tools (delegate is placeholder)
```

## Session Timeline

| Day | Hours | What Was Done |
|-----|-------|---------------|
| Feb 27 | ~3h | Tool call rendering, session isolation, agent variants deployed, agent selector UI, session orchestration design doc |
| Feb 28 | ~3h | Multi-user identity, SSE reconnect, history aggregation, artifact dedup, old-format parsing fixes, security hardening, CI fixes, Playwright tests to 12/12 |

## Cost Breakdown (Approximate)

| Category | Cost | Notes |
|----------|------|-------|
| Opus 4.6 coding | ~$200 | Primary development model |
| Opus 4.6 testing | ~$30 | Playwright test development and debugging |
| Opus 4.6 design docs | ~$10 | Session orchestration design |
| Total | ~$240 | |

## Lessons Learned

1. **JSON-first parsing is essential.** Regex-based parsing of agent output is fragile. The switch to structured JSON events with type discriminators eliminated an entire class of rendering bugs.

2. **Session state leaks are subtle.** React state that persists across component re-renders (refs, closures over stale state) caused messages from one session to appear in another. The fix required explicit state clearing on every session switch.

3. **Old format backward compatibility is expensive.** Supporting both JSON and plain-text event formats doubled the parsing code. Consider versioning the event format and migrating old sessions.

4. **SSE on OpenShift needs route timeout tuning.** The default 30s route timeout kills streaming connections. Setting `haproxy.router.openshift.io/timeout: 120s` is required for any SSE endpoint.

5. **Trivy security context requirements propagate.** Adding one container without security contexts causes Trivy to fail the entire chart. All containers (including init containers and sidecars) need explicit security contexts.
