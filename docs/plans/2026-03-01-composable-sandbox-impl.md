# Composable Sandbox Security — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire the composable sandbox security layers (Landlock, TOFU, repo_manager, triggers) into the agent platform with full test coverage.

**Architecture:** Copy standalone modules from worktree to `deployments/sandbox/`, add unit tests for each, then wire into backend. Each section must pass all tests before moving to the next.

**Tech Stack:** Python 3.11, pytest, unittest.mock, FastAPI, kubernetes-sigs/agent-sandbox CRDs

---

### Task 1: Copy sandbox modules + create test infrastructure

**Files:**
- Copy from `.worktrees/sandbox-agent/deployments/sandbox/` to `deployments/sandbox/`:
  - `nono_launcher.py` (rename from `nono-launcher.py` for importability)
  - `tofu.py`
  - `repo_manager.py`
  - `triggers.py`
  - `sources.json`
  - `sandbox_profile.py` (NEW — composable name/manifest builder)
- Create: `deployments/sandbox/__init__.py`
- Create: `deployments/sandbox/tests/__init__.py`
- Create: `deployments/sandbox/tests/conftest.py`

**Step 1:** Create directory structure and copy files
**Step 2:** Create `__init__.py` files and test conftest
**Step 3:** Verify imports work: `python -c "from deployments.sandbox.tofu import TofuVerifier"`
**Step 4:** Commit

---

### Task 2: Unit tests for sandbox_profile.py (composable name builder)

**Files:**
- Create: `deployments/sandbox/sandbox_profile.py`
- Create: `deployments/sandbox/tests/test_sandbox_profile.py`

**Tests:**
1. `test_name_no_layers` — base agent with no layers → `sandbox-legion`
2. `test_name_secctx_only` — secctx toggle → `sandbox-legion-secctx`
3. `test_name_full_stack` — all layers → `sandbox-legion-secctx-landlock-proxy-gvisor`
4. `test_name_custom_combo` — proxy without secctx → `sandbox-legion-proxy` (with warning)
5. `test_name_custom_base` — different base agent → `my-agent-secctx-landlock`
6. `test_manifest_secctx` — generates correct SecurityContext in pod spec
7. `test_manifest_proxy_sidecar` — generates Squid sidecar container when proxy enabled
8. `test_manifest_landlock_entrypoint` — wraps entrypoint with nono-launcher when landlock enabled
9. `test_manifest_proxy_env` — sets HTTP_PROXY/HTTPS_PROXY env vars when proxy enabled
10. `test_warnings_proxy_without_secctx` — returns warning for unusual combo
11. `test_sandboxclaim_manifest` — generates SandboxClaim instead of Deployment when toggled

**Implementation:** `SandboxProfile` class with:
- `__init__(base_agent, secctx, landlock, proxy, gvisor, managed_lifecycle, ttl_hours, namespace)`
- `name() -> str` — composable name
- `warnings() -> list[str]` — unusual combo warnings
- `build_manifest() -> dict` — K8s Deployment or SandboxClaim YAML
- `build_service() -> dict` — K8s Service YAML

**Step 1:** Write all tests (expect FAIL)
**Step 2:** Run tests to verify they fail
**Step 3:** Implement SandboxProfile
**Step 4:** Run tests to verify they pass
**Step 5:** Commit

---

### Task 3: Unit tests for nono_launcher.py

**Files:**
- Test: `deployments/sandbox/tests/test_nono_launcher.py`

**Tests:**
1. `test_apply_sandbox_without_nono_py` — returns False when nono_py not installed
2. `test_apply_sandbox_with_nono_py` — mocks nono_py, verifies paths added
3. `test_workspace_env_override` — respects WORKSPACE_DIR env var
4. `test_main_with_command` — verifies os.execvp called with argv[1:]
5. `test_main_without_command` — verifies default sleep command

**Step 1:** Write tests
**Step 2:** Run, verify pass
**Step 3:** Commit

---

### Task 4: Unit tests for tofu.py

**Files:**
- Test: `deployments/sandbox/tests/test_tofu.py`

**Tests:**
1. `test_hash_file_exists` — computes SHA-256 correctly
2. `test_hash_file_missing` — returns None for missing file
3. `test_compute_hashes` — hashes all TRACKED_FILES
4. `test_verify_first_run` — stores hashes on first run (mock kubectl)
5. `test_verify_match` — returns (True, "verified") when hashes match
6. `test_verify_mismatch` — returns (False, "FAILED: CHANGED") when file modified
7. `test_verify_deleted_file` — detects file deletion
8. `test_verify_new_file` — detects newly added file

**Step 1:** Write tests
**Step 2:** Run, verify pass
**Step 3:** Commit

---

### Task 5: Unit tests for repo_manager.py

**Files:**
- Test: `deployments/sandbox/tests/test_repo_manager.py`

**Tests:**
1. `test_allowed_by_pattern` — matches glob patterns in allowed_remotes
2. `test_denied_by_pattern` — deny overrides allow
3. `test_permissive_mode` — no policy = allow all
4. `test_not_in_allowed` — blocked when no pattern matches
5. `test_clone_blocked` — raises PermissionError for denied repo
6. `test_clone_max_repos` — raises RuntimeError at limit
7. `test_clone_success` — mocks git clone, returns path
8. `test_repo_name_derivation` — strips .git, extracts last segment

**Step 1:** Write tests
**Step 2:** Run, verify pass
**Step 3:** Commit

---

### Task 6: Unit tests for triggers.py

**Files:**
- Test: `deployments/sandbox/tests/test_triggers.py`

**Tests:**
1. `test_cron_claim_structure` — correct apiVersion, kind, labels
2. `test_webhook_claim_labels` — trigger-type=webhook, trigger-repo, etc.
3. `test_alert_claim_labels` — trigger-type=alert, severity
4. `test_ttl_calculation` — shutdownTime = now + ttl_hours
5. `test_kubectl_failure` — raises RuntimeError on non-zero exit

**Step 1:** Write tests
**Step 2:** Run, verify pass
**Step 3:** Commit

---

### Task 7: Wire trigger router into FastAPI backend

**Files:**
- Create: `kagenti/backend/app/routers/sandbox_trigger.py`
- Modify: `kagenti/backend/app/main.py` (add router)
- Create: `kagenti/backend/tests/test_sandbox_trigger.py`

**Tests:**
1. `test_cron_trigger_endpoint` — POST /api/v1/sandbox/trigger with type=cron
2. `test_webhook_trigger_endpoint` — POST with type=webhook
3. `test_alert_trigger_endpoint` — POST with type=alert
4. `test_unknown_trigger_type` — returns 400
5. `test_missing_required_field` — returns 422

**Step 1:** Write tests
**Step 2:** Run, verify fail
**Step 3:** Implement router
**Step 4:** Register in main.py
**Step 5:** Run, verify pass
**Step 6:** Commit
