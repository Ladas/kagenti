# Multi-Session Sandbox Development Coordination

> **Date:** 2026-03-01
> **Orchestrator:** Session O (this document's owner)
> **Active Sessions:** A, B, C, D, O
> **Test Clusters:** sbox (dev), sbox1 (staging), sbox42 (integration — deploying)

## ALERT: OpenAI Budget EXCEEDED

**Confirmed:** `insufficient_quota` — HTTP 429 on chat completions. Key is valid (models endpoint returns 200) but all chat/completion calls fail with:
```json
{"error": {"message": "You exceeded your current quota", "type": "insufficient_quota", "code": "insufficient_quota"}}
```

**Impact:** sandbox-legion, sandbox-hardened, sandbox-restricted ALL fail. sandbox-basic (local qwen2.5:3b) unaffected.

**Action:** Check billing at https://platform.openai.com/account/billing/overview

**TODO for Session B:** Agent must handle 429 `insufficient_quota` gracefully — return clear error message + auto-retry with backoff for transient 429s. Do NOT crash the SSE stream.

## Orchestrator Status

**Clusters:**
- sbox: Active, 9/9 core tests passing
- sbox42: Being deployed by Session O (another session)
- sandbox42: Being created by this orchestrator session (in progress)

**sbox core tests:** 9/9 passing (verified after all session pushes)
**No file conflicts detected** between sessions

### Session Activity (latest)
| Session | Last Commit | What |
|---------|------------|------|
| A | `bb2f73e6` | flush tool call events during streaming |
| B | No commits visible | may be working locally |
| C | `907fac72` + 6 more | Integration CRD + UI pages (7 commits) |
| D | `c34f4c29` | demo realm users + show-services --reveal |

## Architecture Reference

See [2026-03-01-sandbox-platform-design.md](2026-03-01-sandbox-platform-design.md) for the full
system design with C4 diagrams.

Previous research (reference only): [2026-02-23-sandbox-agent-research.md](2026-02-23-sandbox-agent-research.md)

---

## Session Definitions

### Session O — Orchestrator (sbox42 cluster)

**Role:** Test coordination, integration testing, conflict resolution
**Cluster:** sbox42 (creating — ETA ~10 min)
**Claude Session:** Session O active as of 2026-03-01
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
1. ~~P0: Fix Istio + asyncpg DB connection~~ ✅ DONE — ssl=False, retry, eviction (5f7596d6)
2. P0: Fix agent serializer in image (Dockerfile/pyproject.toml) — Session B
3. ~~P1: Tool call rendering during streaming + in loaded history~~ ✅ DONE — parseGraphEvent regex fallback + immediate flush (bb2f73e6)
4. ~~P1: Session name matching content~~ ✅ DONE — metadata merge across task rows (cf026bb9)
5. ~~P2: Streaming tool call events -> ToolCallStep messages~~ ✅ DONE (merged with #3)

**All Session A P0/P1 tasks complete.** Backend deployed to sbox. Awaiting Session O integration test.

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
1. ~~P0: Fix event_serializer.py not included in agent image~~ ✅ VERIFIED — serializer IS in image, import works, produces correct JSON
2. ~~P0: Fix Shipwright build timeouts/failures~~ ✅ RESOLVED — transient Red Hat registry 500s; backend-37 + ui-39 completed
3. ~~P0: Fix Istio+asyncpg DB connection in agents~~ ✅ FIXED — switched `asyncpg` to `psycopg` driver (2e2590b, 6d5aee22)
4. P1: Wizard deploy triggers Shipwright Build (not just Deployment)
5. P1: Create deployment manifests for hardened/basic/restricted variants
6. P2: Source build from git URL (wizard end-to-end)

**Session Active:** YES (started 2026-03-01T12:04Z)

**Commits:**
```
2e2590b fix(sandbox): switch TaskStore from asyncpg to psycopg driver  (agent-examples repo)
6d5aee22 fix(deploy): switch sandbox-legion TaskStore URL from asyncpg to psycopg  (kagenti repo)
```

**Status / Findings:**
- ✅ Serializer IS in all agent images. Produces `{"type": "tool_call", ...}` format correctly.
- ✅ Backend build 37 + UI build 39 completed, rollout done — latest code deployed.
- ✅ DB connection fixed: `postgresql+asyncpg://` → `postgresql+psycopg://`. Istio ztunnel corrupts asyncpg binary protocol; psycopg text protocol works fine. All 4 persistent variants patched.
- ✅ sandbox-legion confirmed healthy with PostgreSQL — no more `ConnectionDoesNotExistError`.

**Correction for Session A:** The serializer IS deployed. Tool call rendering issue is frontend streaming, not agent image. The asyncpg fix is the driver scheme in `TASK_STORE_DB_URL`, not ssl or connection args.

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

**Additional File Ownership (Integrations Hub):**
- `kagenti/ui-v2/src/pages/IntegrationsPage.tsx` — EXCLUSIVE
- `kagenti/ui-v2/e2e/integrations.spec.ts` — EXCLUSIVE
- `kagenti/backend/app/routers/integrations.py` — EXCLUSIVE
- `charts/kagenti/templates/integration-crd.yaml` — EXCLUSIVE

**Priority Tasks:**
1. P1: Wire HITL approve/deny to LangGraph graph resume (BLOCKED — needs Session A DB fix)
2. P1: Sessions table with passover chain column
3. P1: Integrations Hub UI tests (TDD — Playwright)
4. P2: Sub-agent delegation design + populate parent_context_id
5. P2: Passover chain API endpoint
6. P3: Automated passover (context_monitor node)

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
| C (HITL+Integrations) | 6+24 | 3/6 + 24/24 integrations | 2026-03-01 — integrations hub 24/24 Playwright tests passing, HITL blocked on A |
| D (Multi-user) | 0 | N/A | Not started |
| O (Integration) | ALL | BLOCKED | 2026-03-01 13:35 — sbox42 cluster UP, Kagenti installed, weather agents deployed. **BLOCKED** by `postgres-sessions-0` pod `CreateContainerConfigError`: `postgres:16-alpine` runs as root but OpenShift requires `runAsNonRoot`. Sandbox agents never deployed. No tests run yet. |

---

## Cross-Session TODOs

> Sessions add requests here when they need changes in another session's files.

| Requester | Target Session | File | Change Needed | Status |
|-----------|---------------|------|---------------|--------|
| O (conflict scan) | ALL | `api.ts`, `App.tsx`, `main.py` | **UNOWNED** — these shared files will cause merge conflicts. Assign ownership or use merge-order rules. | NEW — Session C added integrations to all 3 files (cherry-picked + conflict resolved into sandbox-agent) |
| O (conflict scan) | A, B | `SandboxCreatePage.tsx` | **UNOWNED** — sits at Session A/B boundary. Assign to one session. | NEW |
| A | O | `deployments/sandbox/postgres-sessions.yaml` | Re-apply on sbox42: image fixed from `postgres:16-alpine` to `bitnami/postgresql:16` (non-root) in 886a3cf4. Run: `kubectl apply -f .worktrees/sandbox-agent/deployments/sandbox/postgres-sessions.yaml` then `kubectl rollout restart sts/postgres-sessions -n team1` | READY |
| O (conflict scan) | B | `kubernetes.py` | Multi-author (Smola + Dettori). Session A HITL work touched this B-exclusive file in commit ae3e26fa. | WATCH |
| O (conflict scan) | D | `kagenti/auth/` | 3 authors (Dettori, Rubambiza, Smola). Session D should coordinate before modifying. | WATCH |
| O (sbox42 deploy) | B | `postgres-sessions.yaml` | ~~**P0 BLOCKER**: postgres:16-alpine runs as root~~ ✅ FIXED — switched to `bitnami/postgresql:16` (UID 1001). Commit `2417c723`. | DONE |
| B | A | `sandbox.py` | FYI: asyncpg fix is `TASK_STORE_DB_URL` driver scheme (`postgresql+psycopg://`), not ssl or retry. Checkpointer already uses psycopg via `AsyncPostgresSaver`. | INFO |

---

## Priority Order

1. ~~**Session B**: Fix source builds -> deploy serializer~~ ✅ ALL P0s DONE
2. **Session A**: Tool call rendering (streaming flush), session name propagation
3. **Session C**: Wire HITL approve/deny to graph.resume()
4. **Session D**: Create Keycloak test users, multi-user Playwright tests
5. **Session O**: Pull latest (`2417c723`), re-deploy sbox42 with bitnami postgres, run integration suite
6. **Session B**: Create deployment manifests for hardened/basic/restricted variants
