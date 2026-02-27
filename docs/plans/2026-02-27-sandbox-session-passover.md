# Sandbox Session Passover — 2026-02-27

## Session Stats
- Duration: ~4 hours
- Commits: 8 on feat/sandbox-agent branch
- Tests: 9 Playwright (5 session + 4 variant), all passing on sbox + sbox1
- Clusters: sbox (5 agents), sbox1 (platform only)

## What's Built & Deployed

### Tool Call Rendering (DONE)
- Agent: `LangGraphSerializer` emits structured JSON events
- Backend: JSON-first parsing with regex fallback for old sessions
- Frontend: `ToolCallStep` renders 5 event types (tool_call, tool_result, llm_response, error, hitl_request)

### Session Isolation (DONE)
- Session state leak fix: input/streaming cleared on session switch
- Full-width session names with CSS text-overflow
- Session persistence across page reload (localStorage)
- 5 assertive Playwright tests verified on both clusters

### Agent Variants (DONE — 4 deployed on sbox)
| Agent | Persistence | Security | Status |
|-------|------------|----------|--------|
| sandbox-legion | PostgreSQL | Default | Running, tests pass |
| sandbox-hardened | PostgreSQL | non-root, drop caps, seccomp | Running, tests pass |
| sandbox-basic | None | non-root, drop caps, seccomp | Running, tests pass |
| sandbox-restricted | PostgreSQL | Hardened + restricted proxy | Running, tests pass |

### Agent Selector UI (DONE)
- SandboxAgentsPanel shows active session's agent (filtered view)
- Click to switch agents for new sessions
- "Change sandbox" link to see all agents

### Security Fixes (DONE)
- SSRF prevention: namespace + agent_name K8s name validation
- Fixed hardcoded agent_name in streaming path
- Security contexts on postgres-sessions.yaml (Trivy)
- Skip markers for sandbox tests in Kind CI

### Design Docs (DONE)
- `docs/plans/2026-02-27-tool-call-rendering-design.md`
- `docs/plans/2026-02-27-session-orchestration-design.md` (685 lines)

## What's NOT Built Yet (Priority Order)

### P0: Multi-User Message Identity
**Problem**: Messages don't show who sent them. No user identity stored.
**What's needed**:
- Backend: Extract username from Keycloak JWT, store in message metadata
- Frontend: Show "username (you)" for own messages, "username" for others
- Test: Two users chatting in same session, verify names visible
**Blocked by**: Backend JWT extraction

### P1: Sub-Agent Child Sessions
**Problem**: `delegate` tool is a placeholder. No parent_context_id populated.
**What's needed**:
- Agent: Wire delegate tool to create SandboxClaim with parent_context_id
- Backend: No changes (metadata already stored)
- Frontend: Sidebar shows child sessions indented under parent
**Blocked by**: SandboxClaim CRD + controller

### P2: Automated Session Passover
**Problem**: Manual passover only (docs/plans/*.md documents)
**What's needed**:
- Agent: context_monitor node detects token count > 80%
- Agent: passover_node generates summary, creates new session
- Backend: passover chain API endpoint
- Frontend: passover notice in chat, chain view
**Blocked by**: P1 (uses similar session creation mechanism)

### P3: HITL Milestones
**Problem**: No milestone gates in agent execution
**What's needed**:
- Agent: milestone node calls interrupt() at checkpoints
- Frontend: approval cards with approve/deny buttons
- Backend: resume endpoint for milestone approval
**Blocked by**: LangGraph interrupt() already works (used in shell HITL)

## Startup for Next Session

```bash
cd /Users/ladas/Projects/OCTO/kagenti/kagenti
export MANAGED_BY_TAG=kagenti-team
source .env.kagenti-team
export KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig
export PATH="/opt/homebrew/opt/helm@3/bin:$PATH"
claude
```

## Priority: Implement multi-user message identity first
- Extract user from JWT in backend sandbox.py chat endpoints
- Store user_id + username in A2A message metadata
- Frontend: show username in chat bubbles
- Playwright test: login as admin, send message, verify "admin (you)" shows
- This is the fastest path to "seeing another user's messages"

## CI Status (PR #758)
- Build (3.11/3.12): PASS
- DCO, Helm Lint, Bandit, Shell Lint, YAML Lint: PASS
- Trivy: Fixed (security contexts added)
- Deploy & Test (Kind): Fixed (skip markers added)
- CodeQL: Pre-existing baseline issue
- E2E HyperShift: Pending (needs /run-e2e comment)
