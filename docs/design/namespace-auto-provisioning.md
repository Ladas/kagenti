# Namespace Auto-Provisioning Design Document

**Issue:** [kagenti/kagenti#614 - Section 1.3](https://github.com/kagenti/kagenti/issues/614)
**Status:** Draft
**Priority:** P0
**Author:** Generated from codebase analysis
**Date:** 2026-02-07

---

## Table of Contents

- [Problem Statement](#problem-statement)
- [Current State](#current-state)
- [Related Issues and Work Tracking](#related-issues-and-work-tracking)
- [Requirements](#requirements)
- [Proposed Design](#proposed-design)
- [Implementation Details](#implementation-details)
- [Files That Need to Change](#files-that-need-to-change)
- [Phased Rollout](#phased-rollout)
- [Open Questions](#open-questions)

---

## Problem Statement

Creating a new team namespace in Kagenti currently requires:

1. Editing `charts/kagenti/values.yaml` to add the namespace name to `agentNamespaces`
2. Re-running the Helm installer or Ansible playbook
3. Waiting for the Keycloak OAuth secret job to complete
4. Verifying all 6 secrets, ConfigMaps, SPIRE config, and RBAC were correctly provisioned

This process is manual, error-prone, and blocks new team onboarding. Users report hitting errors like:

- `configmap "environments" not found` (missing ConfigMap in new namespace)
- Missing registry secrets preventing image pulls
- OAuth secrets not created because the Helm Job ran before the namespace existed

A platform admin should be able to onboard a new team without re-running the full installer.

---

## Current State

### How Namespaces Are Provisioned Today

The entire namespace provisioning pipeline is **declarative and Helm-driven**, with no runtime controller watching for new namespaces.

#### 1. Namespace List in values.yaml

**File:** `charts/kagenti/values.yaml:43-45`
```yaml
agentNamespaces:
- team1
- team2
```

This list is also mirrored in environment-specific configs:
- `deployments/envs/dev_values.yaml:54-55` (via `components.agentNamespaces.enabled: true`)
- `deployments/envs/ocp_values.yaml:91-93`

#### 2. Namespace Creation + Resources (Helm Template)

**File:** `charts/kagenti/templates/agent-namespaces.yaml` (223 lines)

For **each** entry in `agentNamespaces`, the template creates:

| Resource | Count per NS | Purpose |
|----------|-------------|---------|
| Namespace | 1 | With labels: `kagenti-enabled=true`, `istio-discovery=enabled`, `istio.io/dataplane-mode=ambient`, `istio.io/use-waypoint=waypoint`, `shared-gateway-access=true` |
| `github-token-secret` | 1 | GitHub API credentials (Opaque) |
| `github-shipwright-secret` | 1 | Shipwright build auth (kubernetes.io/basic-auth) |
| `ghcr-secret` | 1 | GHCR registry pull (kubernetes.io/dockerconfigjson) |
| `openai-secret` | 1 | OpenAI API key (Opaque) |
| `slack-secret` | 1 | Slack bot tokens (Opaque) |
| `quay-registry-secret` | 1 | Quay.io registry push (kubernetes.io/dockerconfigjson) |
| `environments` ConfigMap | 1 | 8 environment presets (ollama, openai, mcp-weather, mcp-slack, slack-researcher-config, slack-researcher-auth-config, mcp-slack-config, mcp-slack-auth-config) |
| `pipeline-privileged-scc` RoleBinding | 1 (OCP only) | Grants privileged SCC for buildah builds |

#### 3. SPIRE/SPIFFE Configuration

**File:** `charts/kagenti/templates/spiffe-namespaces-config.yaml` (24 lines)

Creates `spiffe-helper-config` ConfigMap in each agent namespace containing SPIRE agent socket path, SVID file paths, and JWT audience (`kagenti`). Only created when `spire.enabled=true`.

#### 4. Keycloak OAuth Secret Job

**File:** `charts/kagenti/templates/agent-oauth-secret-job.yaml` (121 lines)

A Kubernetes Job that:
- Reads Keycloak admin credentials from the `keycloak` namespace
- Creates/updates OAuth client secrets in each agent namespace
- Creates a `kagenti-cross-namespace-secret-manager` ClusterRole with read access to Keycloak secrets and write access to target namespaces
- Creates RoleBindings in each agent namespace (line 52-70: iterates `agentNamespaces`)
- Passes agent namespaces as comma-separated `AGENT_NAMESPACES` env var (line 109)

#### 5. MCP Gateway Namespace Labeler

**File:** `charts/kagenti/templates/mcp-gateway-ns-labeler.yaml` (103 lines)

A separate Job that labels namespaces with Istio discovery labels and `shared-gateway-access`. Does NOT iterate agent namespaces (only labels `gateway-system` and the release namespace).

#### 6. Backend Namespace Discovery

**File:** `kagenti/backend/app/routers/namespaces.py:16-31`
**File:** `kagenti/backend/app/services/kubernetes.py:81-96`

The backend discovers enabled namespaces dynamically via the Kubernetes API:
```python
# Uses label selector: kagenti-enabled=true
def list_enabled_namespaces(self) -> List[str]:
    selector = f"{ENABLED_NAMESPACE_LABEL_KEY}={ENABLED_NAMESPACE_LABEL_VALUE}"
    return self.list_namespaces(label_selector=selector)
```

This means the backend UI **already supports dynamic namespace discovery** -- if a namespace has the right label, it appears in the UI. The gap is that no controller provisions the required resources (secrets, ConfigMaps, RBAC).

### Current Architecture Diagram

```
                      Install Time                              Runtime
                     ┌────────────┐                        ┌────────────────┐
                     │            │                        │                │
values.yaml ────────►│  Helm      │──── Namespace ────────►│  Backend API   │
  agentNamespaces    │  Template  │     + Resources         │  (label query) │
  - team1            │            │                        │                │
  - team2            │            │                        │  GET /namespaces│
                     └─────┬──────┘                        │  ?enabled=true │
                           │                               └────────────────┘
                           │
                           ▼
                     ┌────────────┐
                     │  Keycloak  │
                     │  OAuth Job │─── Creates secrets
                     │            │    in each NS
                     └────────────┘
```

---

## Related Issues and Work Tracking

### Directly Related Open Issues

| Issue | Title | Relevance |
|-------|-------|-----------|
| [#614 sec 1.3](https://github.com/kagenti/kagenti/issues/614) | Namespace Auto-Provisioning (Feature) | **This feature** -- part of the trial run feedback epic |
| [#400](https://github.com/kagenti/kagenti/issues/400) | Namespace-based user access and identity provider integration for agent keys | **Strongly related** -- users need per-namespace key management without shared secrets |
| [#439](https://github.com/kagenti/kagenti/issues/439) | Namespace-Based Token Usage Quotas for AI Agents | **Depends on this** -- quotas require dynamic namespace provisioning to set per-NS limits |
| [#440](https://github.com/kagenti/kagenti/issues/440) | Kagenti Playground: Multi-Team Deployment on OpenShift AI | **Epic that subsumes this** -- multi-team deployment needs self-service namespace creation |
| [#397](https://github.com/kagenti/kagenti/issues/397) | Refactor Keycloak secrets handling | **Prerequisite work** -- secret handling needs refactoring before auto-provisioning |
| [#380](https://github.com/kagenti/kagenti/issues/380) | Workload Identity Abstraction | **Related** -- namespace provisioning must support both SPIRE and ServiceAccount identity |

### Related Epics

| Epic | Title | How This Feature Fits |
|------|-------|----------------------|
| [#523](https://github.com/kagenti/kagenti/issues/523) | Compositional Agent Platform Architecture | Phase 4 introduces composition CRDs (TokenExchange, AgentCard, AgentTrace); namespace auto-provisioning would be the base layer that ensures these CRDs can be applied per-namespace |
| [#623](https://github.com/kagenti/kagenti/issues/623) | Identify Emerging Agentic Deployment Patterns | Multi-tenant execution is listed as a key deployment pattern dimension |
| [#612](https://github.com/kagenti/kagenti/issues/612) | Agent Attestation Framework | Per-namespace SPIFFE identity provisioning is a dependency |
| [#309](https://github.com/kagenti/kagenti/issues/309) | Full Coverage E2E Testing | Needs tests for dynamic namespace provisioning flows |
| [#614 sec 1.1](https://github.com/kagenti/kagenti/issues/614) | Developer Onboarding Documentation | Namespace setup guide depends on how provisioning works |

### Related Merged PRs

| PR | Title | Relevance |
|----|-------|-----------|
| [#617](https://github.com/kagenti/kagenti/pull/617) | Create authbridge configmaps in user namespaces | Pattern for cross-namespace resource creation |
| [#574](https://github.com/kagenti/kagenti/pull/574) | Document how to connect to tools in different namespaces | Cross-namespace connectivity |
| [#275](https://github.com/kagenti/kagenti/pull/275) | Show only enabled namespaces in UI | Uses `kagenti-enabled=true` label for UI filtering |
| [#396](https://github.com/kagenti/kagenti/pull/396) | Add agent-oauth-secret job | Current OAuth secret provisioning per namespace |
| [#531](https://github.com/kagenti/kagenti/pull/531) | Design proposal for compositional architecture | The webhook-based injection model could trigger namespace provisioning |
| [#615](https://github.com/kagenti/kagenti/pull/615) | Developer onboarding documentation | Phase 1 docs covering namespace provisioning steps |

### Related Closed Issues

| Issue | Title | Learning |
|-------|-------|----------|
| [#159](https://github.com/kagenti/kagenti/issues/159) | Duplicated Keycloak credentials across namespaces | Each namespace currently gets identical copies of shared secrets |
| [#167](https://github.com/kagenti/kagenti/issues/167) | Update secrets in agent namespaces when re-running installer | Secrets need to be updatable, not just creatable |
| [#134](https://github.com/kagenti/kagenti/issues/134) | Show only enabled namespaces in UI | Backend already uses label-based discovery |
| [#148](https://github.com/kagenti/kagenti/issues/148) | Connection between agent and tool in different namespaces | Cross-namespace networking requires proper Istio labels |
| [#299-#301](https://github.com/kagenti/kagenti/issues/299) | Multi-tenant agent-to-tool demos (3 approaches) | Patterns for multi-tenant namespace isolation |

---

## Requirements

### Functional Requirements

1. **Self-Service Namespace Creation:** Admin users can create new team namespaces without re-running the installer
2. **Automatic Resource Provisioning:** When a new namespace is labeled `kagenti-enabled=true`, all required resources are created automatically:
   - Istio Ambient labels
   - Secrets (registry, API keys)
   - `environments` ConfigMap
   - SPIRE configuration (when enabled)
   - Keycloak OAuth client + secret
   - RBAC for backend cross-namespace access
3. **Idempotency:** Running provisioning multiple times produces the same result
4. **Secret Inheritance:** New namespaces inherit platform-wide secrets from a central source (not hardcoded in values.yaml)
5. **Customizable Secrets:** Teams can override inherited secrets with their own

### Non-Functional Requirements

1. **Eventual Consistency:** Resources may take a few seconds to appear (controller reconciliation)
2. **Observability:** Provisioning status should be visible (events, conditions)
3. **Security:** Only cluster admins can create namespaces; provisioning runs with minimal RBAC

### Non-Goals (Out of Scope)

1. **UI namespace creation wizard** -- this is a backend/operator feature
2. **Per-user namespaces** -- tracked in [#400](https://github.com/kagenti/kagenti/issues/400)
3. **Token usage quotas** -- tracked in [#439](https://github.com/kagenti/kagenti/issues/439)
4. **Per-namespace Keycloak realms** -- tracked in [#306](https://github.com/kagenti/kagenti/issues/306)

---

## Proposed Design

### Option A: Namespace Controller in Kagenti Operator (Recommended)

Add a new controller to the Kagenti operator that watches for namespaces labeled `kagenti-enabled=true` and reconciles the required resources.

```
                     Admin creates Namespace              Controller reconciles
                    ┌────────────────────┐              ┌────────────────────────┐
                    │                    │              │                        │
kubectl create ns ──│  Namespace         │──────watch──►│  Namespace Controller  │
  + labels:         │  kagenti-enabled:  │              │  (in kagenti-operator) │
  kagenti-enabled:  │    "true"          │              │                        │
    "true"          │                    │              │  Reconciles:           │
                    └────────────────────┘              │  - Secrets             │
                                                       │  - ConfigMaps          │
                                                       │  - SPIRE config        │
                                                       │  - RoleBindings        │
                                                       │  - Keycloak client     │
                                                       └────────────────────────┘
```

**How it works:**

1. Admin creates a namespace with label `kagenti-enabled=true`:
   ```bash
   kubectl create namespace my-team
   kubectl label namespace my-team kagenti-enabled=true
   ```

2. The Namespace Controller (in `kagenti-operator`) watches for namespaces with this label

3. On detection, the controller:
   a. Copies platform secrets from a `kagenti-system/kagenti-namespace-template` ConfigMap/Secret bundle
   b. Creates the `environments` ConfigMap from a template
   c. Creates SPIRE helper config (if SPIRE enabled)
   d. Creates RoleBindings for backend cross-namespace access
   e. Labels the namespace with Istio Ambient labels
   f. Triggers Keycloak client creation (via Job or direct API call)

4. Controller sets status annotations on the namespace:
   ```yaml
   annotations:
     kagenti.io/provisioning-status: "complete"
     kagenti.io/provisioned-at: "2026-02-07T12:00:00Z"
   ```

**Pros:**
- Fully Kubernetes-native (watch + reconcile pattern)
- Works with GitOps workflows (just add namespace YAML to Git)
- Existing operator codebase (Go) to extend
- Aligns with the compositional architecture direction (#523, PR #531)

**Cons:**
- Requires Go development in the operator
- Central secret management needs careful design

### Option B: Webhook-Based Provisioning

Extend the existing mutating webhook (`platformWebhook`) to intercept namespace creation events.

**Pros:**
- Synchronous -- resources exist immediately after namespace creation
- Reuses existing webhook infrastructure

**Cons:**
- Webhooks are not designed for long-running operations (Keycloak client creation)
- Failure handling is complex (partial provisioning)
- Webhooks have strict timeout limits

### Option C: CLI/Script Tool

Create a `kubectl kagenti create-namespace` plugin or standalone script.

```bash
kubectl kagenti create-namespace my-team \
  --copy-secrets-from team1 \
  --enable-istio \
  --enable-spire
```

**Pros:**
- Simple to implement
- Explicit control

**Cons:**
- Not Kubernetes-native (no reconciliation loop)
- No self-healing if resources are deleted
- Doesn't work with GitOps

### Recommendation

**Option A (Controller)** is recommended because:

1. It aligns with the compositional architecture direction (#523) where the operator manages per-namespace CRDs
2. It provides self-healing (if secrets are deleted, they are re-created)
3. It works with GitOps (just commit a namespace YAML)
4. The kagenti-operator already has the infrastructure for controllers

Option C can be implemented as a quick-win for Phase 1 while the controller is being built.

---

## Implementation Details

### Central Secret Template

Create a "template" namespace or ConfigMap in `kagenti-system` that holds the default secrets and configurations to copy into new namespaces:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kagenti-namespace-template
  namespace: kagenti-system
data:
  # Which secrets to copy (references to secret names in kagenti-system)
  secret-sources: |
    - name: github-token-secret
      sourceSecret: kagenti-platform-github-secret
    - name: ghcr-secret
      sourceSecret: kagenti-platform-ghcr-secret
    - name: openai-secret
      sourceSecret: kagenti-platform-openai-secret
    - name: quay-registry-secret
      sourceSecret: kagenti-platform-quay-secret
    - name: slack-secret
      sourceSecret: kagenti-platform-slack-secret
    - name: github-shipwright-secret
      sourceSecret: kagenti-platform-github-shipwright-secret

  # environments ConfigMap template
  environments-template: |
    ollama: |
      [{"name": "LLM_API_BASE", "value": "http://host.docker.internal:11434/v1"}, ...]
    openai: |
      [{"name": "OPENAI_API_KEY", "valueFrom": {"secretKeyRef": {"name": "openai-secret", "key": "apikey"}}}, ...]
```

### Namespace Labels (Target State)

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: my-team
  labels:
    # Required - triggers provisioning
    kagenti-enabled: "true"
    # Auto-applied by controller
    istio-discovery: enabled
    istio.io/dataplane-mode: ambient
    istio.io/use-waypoint: waypoint
    shared-gateway-access: "true"
  annotations:
    # Set by controller
    kagenti.io/provisioning-status: "complete"  # pending | in-progress | complete | error
    kagenti.io/provisioned-at: "2026-02-07T12:00:00Z"
    kagenti.io/provisioned-by: "kagenti-operator/v0.3.0"
```

### Controller Reconciliation Logic

```
func (r *NamespaceReconciler) Reconcile(ctx, req) (Result, error):
    1. Get namespace
    2. Check label kagenti-enabled=true
    3. If namespace is being deleted -> clean up Keycloak client, return
    4. Ensure Istio labels are set
    5. Copy platform secrets from kagenti-system templates
    6. Create/update environments ConfigMap
    7. Create SPIRE helper config (if spire enabled)
    8. Create RoleBinding for backend access
    9. Trigger Keycloak client registration
    10. Update status annotation
    11. Emit Kubernetes Event
```

### Keycloak Integration

The controller can either:

**Option 1:** Call Keycloak Admin API directly (needs admin credentials mounted)
**Option 2:** Create a Job (reuse existing `agent-oauth-secret` image) that handles Keycloak registration for the single new namespace
**Option 3:** Use the existing `agent-oauth-secret-job` but make it namespace-aware (run for specific namespace only)

Option 2 is recommended as it reuses existing code and keeps Keycloak credentials out of the operator.

### Interaction with Compositional Architecture (#523)

The compositional architecture (PR #531) introduces:
- **Mutating webhook** that injects identity sidecars on labeled workloads
- **Pillar CRDs:** TokenExchange, AgentTrace, AgentCard

Namespace auto-provisioning fits as the **foundation layer** beneath these:

```
Layer 0: Namespace Auto-Provisioning (this feature)
         - Creates namespace with labels, secrets, RBAC
         - Ensures Keycloak client exists

Layer 1: Webhook Identity Injection (#523 Phase 2)
         - Injects SPIFFE/AuthBridge sidecars on labeled workloads
         - Works in any provisioned namespace

Layer 2: Pillar CRDs (#523 Phase 4)
         - TokenExchange, AgentCard, AgentTrace
         - Applied per-workload within provisioned namespaces
```

---

## Files That Need to Change

### Operator Changes (Go)

| File | Change |
|------|--------|
| `NEW: controllers/namespace_controller.go` | New controller watching namespaces with `kagenti-enabled=true` label |
| `main.go` (operator) | Register the new controller |
| `config/rbac/` (operator) | Add RBAC for cross-namespace secret/configmap management |

**Note:** The operator lives in a separate repository. The Helm charts and installer live in the main kagenti repo.

### Helm Chart Changes

| File | Change |
|------|--------|
| `charts/kagenti/templates/agent-namespaces.yaml` | Keep for bootstrap (initial namespaces), but mark as "initial setup only" |
| `NEW: charts/kagenti/templates/namespace-template-configmap.yaml` | Central template for namespace provisioning |
| `charts/kagenti/templates/agent-oauth-secret-job.yaml` | Refactor to support single-namespace mode (env var `TARGET_NAMESPACE`) |
| `charts/kagenti/values.yaml:43-45` | Keep `agentNamespaces` for initial bootstrap, document that controller handles ongoing provisioning |

### Backend Changes (Python)

| File | Change |
|------|--------|
| `kagenti/backend/app/routers/namespaces.py` | No change needed -- already uses label-based discovery |
| `kagenti/backend/app/services/kubernetes.py` | No change needed -- `list_enabled_namespaces()` already works dynamically |

### Documentation Changes

| File | Change |
|------|--------|
| `docs/install.md` | Add section on namespace provisioning |
| `NEW: docs/namespace-provisioning.md` | Full guide for adding new namespaces |
| `docs/components.md` | Update architecture diagram to show controller |

### Ansible/Installer Changes

| File | Change |
|------|--------|
| `deployments/envs/dev_values.yaml` | No change (keeps initial namespaces) |
| `deployments/envs/ocp_values.yaml` | No change |
| `deployments/ansible/default_values.yaml` | Add `namespaceAutoProvisioning.enabled: true` |

---

## Phased Rollout

### Phase 1: Quick-Win Script (Short Term)

Create a shell script that automates the manual steps:

```bash
#!/bin/bash
# scripts/create-namespace.sh
NAMESPACE=$1

kubectl create namespace $NAMESPACE
kubectl label namespace $NAMESPACE \
  kagenti-enabled=true \
  istio-discovery=enabled \
  istio.io/dataplane-mode=ambient \
  istio.io/use-waypoint=waypoint \
  shared-gateway-access=true

# Copy secrets from existing team namespace
for secret in github-token-secret github-shipwright-secret ghcr-secret openai-secret slack-secret quay-registry-secret; do
  kubectl get secret $secret -n team1 -o yaml | \
    sed "s/namespace: team1/namespace: $NAMESPACE/" | \
    kubectl apply -f -
done

# Copy environments ConfigMap
kubectl get configmap environments -n team1 -o yaml | \
  sed "s/namespace: team1/namespace: $NAMESPACE/" | \
  kubectl apply -f -

# Copy SPIRE config (if exists)
kubectl get configmap spiffe-helper-config -n team1 -o yaml 2>/dev/null | \
  sed "s/namespace: team1/namespace: $NAMESPACE/" | \
  kubectl apply -f -

# Run OAuth secret job for new namespace
kubectl create job --from=job/kagenti-agent-oauth-secret-job \
  "oauth-setup-$NAMESPACE" -n kagenti-system \
  -- --namespace=$NAMESPACE
```

**Deliverables:**
- [ ] `scripts/create-namespace.sh`
- [ ] Documentation in `docs/namespace-provisioning.md`
- [ ] Update `docs/install.md` with reference

### Phase 2: Namespace Controller (Medium Term)

Add the controller to `kagenti-operator`:

**Deliverables:**
- [ ] `controllers/namespace_controller.go` in operator repo
- [ ] RBAC configuration for cross-namespace access
- [ ] Helm chart template for namespace template ConfigMap
- [ ] E2E tests for namespace provisioning
- [ ] Update `agent-oauth-secret-job` to support single-namespace mode

### Phase 3: Central Secret Management (Long Term)

Replace per-namespace secret copies with a central secret store:

**Deliverables:**
- [ ] Central secret template in `kagenti-system`
- [ ] Controller watches for secret updates and propagates to namespaces
- [ ] Team-specific secret overrides via annotations
- [ ] Integration with external secret managers (Vault, AWS Secrets Manager)

---

## Open Questions

1. **Secret scope:** Should all namespaces share the same OpenAI/GitHub/Slack secrets, or should teams bring their own? (Relates to #400)

2. **Keycloak realm:** Should each namespace get its own Keycloak realm, or share the `demo`/`master` realm with namespace-scoped clients? (Relates to #306)

3. **Namespace deletion:** Should deleting a namespace clean up the Keycloak client? Or should the client persist for audit?

4. **RBAC for namespace creation:** Who can label a namespace with `kagenti-enabled=true`? Should the controller require additional approval (e.g., a `KagentiNamespace` CRD)?

5. **Operator repository:** The kagenti-operator lives in a separate repo. How do we coordinate the Helm chart changes (this repo) with the operator changes?

6. **Migration:** How do we migrate existing `team1`/`team2` namespaces from Helm-managed to controller-managed without disruption?

---

## Appendix: Resource Inventory per Namespace

Complete list of resources created per agent namespace by the current Helm template:

```
Namespace: my-team
├── Namespace (with 5 labels)
├── Secrets (6)
│   ├── github-token-secret (Opaque: user, token)
│   ├── github-shipwright-secret (basic-auth: username, password)
│   ├── ghcr-secret (dockerconfigjson)
│   ├── openai-secret (Opaque: apikey)
│   ├── slack-secret (Opaque: bot-token, admin-bot-token)
│   └── quay-registry-secret (dockerconfigjson)
├── ConfigMaps (2)
│   ├── environments (8 presets: ollama, openai, mcp-weather, mcp-slack, ...)
│   └── spiffe-helper-config (SPIRE agent config) [if SPIRE enabled]
├── RBAC (via Helm Job)
│   └── RoleBinding: kagenti-<ns>-writer-binding (cross-NS secret access)
├── Keycloak (via Job)
│   └── Secret: kagenti-keycloak-client-secret (OAuth client credentials)
└── OpenShift-only
    └── RoleBinding: pipeline-privileged-scc (buildah SCC)
```
