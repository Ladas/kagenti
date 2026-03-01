# Multi-Session Sandbox Development Coordination

> **Date:** 2026-03-01
> **Orchestrator:** Session O (this document's owner)
> **Active Sessions:** A, B, C, D, O
> **Test Clusters:** sbox (dev), sbox1 (staging), sbox42 (integration)

## Architecture Reference

See [2026-03-01-sandbox-platform-design.md](2026-03-01-sandbox-platform-design.md) for the full
system design with C4 diagrams.

Previous research (reference only): [2026-02-23-sandbox-agent-research.md](2026-02-23-sandbox-agent-research.md)

---

## Session Definitions

### Session O — Orchestrator (sbox42 cluster)

**Role:** Test coordination, integration testing, conflict resolution
**Cluster:** sbox42 (to be created)
**Responsibilities:**
- Run full E2E test suite after each session pushes
- Detect conflicts between sessions
- Update this passover doc with test results
- Deploy fresh cluster for integration testing

**Does NOT write code** — only reads, tests, and coordinates

**Startup:**
```bash
cd /Users/ladas/Projects/OCTO/kagenti/kagenti
export MANAGED_BY_TAG=kagenti-team
source .env.kagenti-team
export KUBECONFIG=~/clusters/hcp/kagenti-team-sbox42/auth/kubeconfig
export PATH="/opt/homebrew/opt/helm@3/bin:$PATH"
claude

Read docs/plans/2026-03-01-multi-session-passover.md. You are Session O (Orchestrator).
Deploy sbox42 cluster, run full test suite, report results.
Other sessions (A, B, C, D) are working in parallel — check for conflicts.
```

**To create sbox42 cluster:**
```bash
# From main repo with HyperShift credentials:
source .env.kagenti-team
export CLUSTER_SUFFIX=sbox42
.github/scripts/hypershift/create-cluster.sh
# Wait ~10 min for cluster to be ready
# Then deploy Kagenti:
export KUBECONFIG=~/clusters/hcp/kagenti-team-sbox42/auth/kubeconfig
.worktrees/sandbox-agent/.github/scripts/local-setup/hypershift-full-test.sh --include-agent-sandbox
```

---

### Session A — Core Platform (sbox cluster)

**Role:** Fix DB connection, tool call rendering, session management
**Cluster:** sbox (existing)
**File Ownership:**
- `kagenti/backend/app/routers/sandbox.py` — EXCLUSIVE
- `kagenti/ui-v2/src/pages/SandboxPage.tsx` — EXCLUSIVE
- `kagenti/ui-v2/src/components/SessionSidebar.tsx` — EXCLUSIVE
- `kagenti/ui-v2/src/components/SandboxAgentsPanel.tsx` — EXCLUSIVE
- `kagenti/ui-v2/e2e/sandbox-sessions.spec.ts` — EXCLUSIVE
- `kagenti/ui-v2/e2e/sandbox-rendering.spec.ts` — EXCLUSIVE
- `kagenti/ui-v2/e2e/sandbox-variants.spec.ts` — EXCLUSIVE

**Priority Tasks:**
1. P0: Fix Istio + asyncpg DB connection (try psycopg driver or mesh exclusion)
2. P0: Fix agent serializer in image (Dockerfile/pyproject.toml)
3. P1: Tool call rendering during streaming + in loaded history
4. P1: Session name matching content (title propagation)
5. P2: Streaming tool call events -> ToolCallStep messages

**Startup:**
```bash
cd /Users/ladas/Projects/OCTO/kagenti/kagenti
export MANAGED_BY_TAG=kagenti-team
source .env.kagenti-team
export KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig
export PATH="/opt/homebrew/opt/helm@3/bin:$PATH"
claude

Read docs/plans/2026-03-01-multi-session-passover.md. You are Session A (Core Platform).
Fix the Istio+asyncpg DB connection blocker first, then tool call rendering.
Sessions B, C, D are working in parallel — do NOT touch their files.
Use /tdd:hypershift for iteration. 12/12 Playwright tests must stay green.
```

---

### Session B — Source Builds & Agent Image (sbox cluster)

**Role:** Fix Shipwright builds, agent image packaging, deploy scripts
**Cluster:** sbox (shared with A, different namespace resources)
**File Ownership:**
- `.worktrees/agent-examples/` — EXCLUSIVE (all agent code)
- `kagenti/backend/app/routers/sandbox_deploy.py` — EXCLUSIVE
- `kagenti/backend/app/services/kubernetes.py` — EXCLUSIVE
- `.github/scripts/kagenti-operator/35-deploy-agent-sandbox.sh` — EXCLUSIVE
- `deployments/sandbox/` — EXCLUSIVE
- `kagenti/ui-v2/e2e/sandbox-create-walkthrough.spec.ts` — EXCLUSIVE

**Priority Tasks:**
1. P0: Fix event_serializer.py not included in agent image (pyproject.toml or Dockerfile)
2. P0: Fix Shipwright build timeouts/failures
3. P1: Wizard deploy triggers Shipwright Build (not just Deployment)
4. P1: Agent deploy script improvements (faster rebuilds)
5. P2: Source build from git URL (wizard end-to-end)

**Startup:**
```bash
cd /Users/ladas/Projects/OCTO/kagenti/kagenti
export MANAGED_BY_TAG=kagenti-team
source .env.kagenti-team
export KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig
export PATH="/opt/homebrew/opt/helm@3/bin:$PATH"
claude

Read docs/plans/2026-03-01-multi-session-passover.md. You are Session B (Source Builds).
Fix the agent image to include event_serializer.py, then fix Shipwright builds.
Session A owns sandbox.py and SandboxPage.tsx — do NOT touch those files.
```

---

### Session C — HITL & Session Orchestration (sbox1 cluster)

**Role:** Wire HITL approve/deny, implement sub-agent delegation, passover
**Cluster:** sbox1
**File Ownership:**
- `kagenti/ui-v2/src/pages/SandboxesPage.tsx` — EXCLUSIVE
- `kagenti/ui-v2/src/pages/SessionsTablePage.tsx` — EXCLUSIVE
- `kagenti/ui-v2/e2e/sandbox-chat-identity.spec.ts` — EXCLUSIVE
- `kagenti/ui-v2/e2e/session-ownership.spec.ts` — EXCLUSIVE
- `kagenti/tests/e2e/common/test_sandbox_variants.py` — EXCLUSIVE
- `kagenti/tests/e2e/common/test_sandbox_legion.py` — EXCLUSIVE
- `docs/plans/2026-02-27-session-orchestration-design.md` — EXCLUSIVE

**Priority Tasks:**
1. P1: Wire HITL approve/deny to LangGraph graph resume
2. P1: Sessions table with passover chain column
3. P2: Sub-agent delegation (populate parent_context_id)
4. P2: Passover chain API endpoint
5. P3: Automated passover (context_monitor node)

**Startup:**
```bash
cd /Users/ladas/Projects/OCTO/kagenti/kagenti
export MANAGED_BY_TAG=kagenti-team
source .env.kagenti-team
export KUBECONFIG=~/clusters/hcp/kagenti-team-sbox1/auth/kubeconfig
export PATH="/opt/homebrew/opt/helm@3/bin:$PATH"
claude

Read docs/plans/2026-03-01-multi-session-passover.md. You are Session C (HITL & Orchestration).
Wire HITL approve/deny buttons to actually resume the agent graph.
Session A owns sandbox.py — coordinate with A for any backend changes needed.
Deploy and test on sbox1 cluster.
```

---

### Session D — Keycloak & Multi-User (sbox cluster)

**Role:** Keycloak personas, multi-user tests, RBAC verification
**Cluster:** sbox (Keycloak namespace)
**File Ownership:**
- `kagenti/ui-v2/src/contexts/AuthContext.tsx` — EXCLUSIVE
- `kagenti/ui-v2/e2e/agent-chat-identity.spec.ts` — EXCLUSIVE
- `kagenti/auth/` — EXCLUSIVE
- `kagenti/examples/identity/` — EXCLUSIVE
- `charts/kagenti-deps/templates/keycloak-*.yaml` — EXCLUSIVE

**Priority Tasks:**
1. P1: Create dev-user and ns-admin Keycloak test users
2. P1: Multi-user Playwright test (admin + dev-user in same session)
3. P2: Random admin password (not hardcoded admin/admin)
4. P2: Session visibility RBAC verification test
5. P3: SPIRE identity toggle integration

**Startup:**
```bash
cd /Users/ladas/Projects/OCTO/kagenti/kagenti
export MANAGED_BY_TAG=kagenti-team
source .env.kagenti-team
export KUBECONFIG=~/clusters/hcp/kagenti-team-sbox/auth/kubeconfig
export PATH="/opt/homebrew/opt/helm@3/bin:$PATH"
claude

Read docs/plans/2026-03-01-multi-session-passover.md. You are Session D (Keycloak & Multi-User).
Create dev-user in Keycloak, then write multi-user Playwright tests.
Do NOT touch sandbox.py, SandboxPage.tsx, or deploy files — those belong to Sessions A and B.
```

---

## Shared Resources (READ-ONLY for all sessions)

- `CLAUDE.md` — project config
- `docs/plans/2026-03-01-multi-session-passover.md` — THIS DOC (Session O updates)
- `docs/plans/2026-03-01-sandbox-platform-design.md` — design reference
- `kagenti/ui-v2/playwright.config.ts` — test config
- `kagenti/tests/conftest.py` — test fixtures

## Conflict Prevention Rules

1. Each session has EXCLUSIVE file ownership — do NOT edit other sessions' files
2. If you need a change in another session's file, add a TODO comment in this doc
3. All sessions push to `feat/sandbox-agent` branch — pull before push
4. Session O runs integration tests after each push
5. If tests fail after your push, YOU fix it before moving on

---

## Test Commands

```bash
# Session A tests (core):
KAGENTI_UI_URL=https://kagenti-ui-kagenti-system.apps.kagenti-team-sbox.octo-emerging.redhataicoe.com \
  npx playwright test sandbox-sessions.spec.ts sandbox-variants.spec.ts sandbox-rendering.spec.ts

# Session C tests (HITL):
KAGENTI_UI_URL=https://kagenti-ui-kagenti-system.apps.kagenti-team-sbox1.octo-emerging.redhataicoe.com \
  npx playwright test sandbox-chat-identity.spec.ts session-ownership.spec.ts

# Session D tests (multi-user):
KAGENTI_UI_URL=https://kagenti-ui-kagenti-system.apps.kagenti-team-sbox.octo-emerging.redhataicoe.com \
  npx playwright test agent-chat-identity.spec.ts

# Full suite (Session O):
KAGENTI_UI_URL=https://kagenti-ui-kagenti-system.apps.kagenti-team-sbox42.octo-emerging.redhataicoe.com \
  npx playwright test sandbox-*.spec.ts session-*.spec.ts agent-chat-identity.spec.ts
```

---

## Current Test Results (Session O updates this)

| Session | Tests | Passing | Last Run |
|---------|-------|---------|----------|
| A (Core) | 12 | 12/12 | 2026-02-28 |
| B (Builds) | 3 | 0/3 (wizard walkthrough) | Not run |
| C (HITL) | 6 | 3/6 | 2026-02-28 |
| D (Multi-user) | 0 | N/A | Not started |
| O (Integration) | ALL | Pending sbox42 | Not started |

---

## Cross-Session TODOs

> Sessions add requests here when they need changes in another session's files.

| Requester | Target Session | File | Change Needed | Status |
|-----------|---------------|------|---------------|--------|
| — | — | — | — | — |

---

## Priority Order

1. **Session B**: Fix source builds -> deploy serializer -> unblocks tool call rendering
2. **Session A**: Fix Istio+asyncpg DB connection, then tool call step flushing
3. **Session C**: Wire HITL approve/deny to graph.resume()
4. **Session D**: Create Keycloak test users, multi-user Playwright tests
5. **Session O**: Deploy sbox42, run full integration suite
