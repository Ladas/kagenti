#!/usr/bin/env bash
# Deploy a2a-bridge via MCPServer CRD (Toolhive)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/env-detect.sh"
source "$SCRIPT_DIR/../lib/logging.sh"

log_step "80" "Deploying a2a-bridge"

# Path to agentic-control-plane repo for RBAC manifests
ORCHESTRATOR_REPO="${ORCHESTRATOR_REPO:-$(dirname "$REPO_ROOT")/agentic-control-plane}"

if [ ! -d "$ORCHESTRATOR_REPO" ]; then
    log_error "agentic-control-plane repo not found at: $ORCHESTRATOR_REPO"
    log_info "Please clone it: git clone git@github.com:Ladas/agentic-control-plane.git"
    exit 1
fi

# Apply RBAC from agentic-control-plane (required for AgentCard read access)
log_info "Applying a2a-bridge RBAC..."
kubectl apply -f "$ORCHESTRATOR_REPO/deploy/a2a-bridge/02-rbac.yaml"

# Deploy via MCPServer CRD
log_info "Deploying a2a-bridge via MCPServer CRD..."
kubectl apply -f "$REPO_ROOT/kagenti/examples/mcpservers/a2a_bridge.yaml"

# Wait for StatefulSet to be created
log_info "Waiting for StatefulSet to be created..."
for i in {1..30}; do
    if kubectl get statefulset a2a-bridge -n kagenti-agents &> /dev/null; then
        log_info "StatefulSet created"
        break
    fi
    if [ "$i" -eq 30 ]; then
        log_error "StatefulSet not created after 60s"
        kubectl get mcpservers -n kagenti-agents
        kubectl describe mcpserver a2a-bridge -n kagenti-agents
        exit 1
    fi
    sleep 2
done

# Patch StatefulSet to use our ServiceAccount (for AgentCard API access)
log_info "Patching StatefulSet with a2a-bridge ServiceAccount..."
kubectl patch statefulset a2a-bridge -n kagenti-agents \
    -p '{"spec":{"template":{"spec":{"serviceAccountName":"a2a-bridge"}}}}'

# Delete existing pod to force recreation with new ServiceAccount
kubectl delete pod -n kagenti-agents -l app=a2a-bridge --wait=false 2>/dev/null || true

# Wait for pod to be ready
log_info "Waiting for a2a-bridge pod to be ready..."
kubectl wait --for=condition=ready --timeout=300s pod -n kagenti-agents -l app=a2a-bridge || {
    log_error "Pod not ready"
    kubectl get pods -n kagenti-agents -l app=a2a-bridge
    kubectl logs -n kagenti-agents -l app=a2a-bridge --tail=50 || true
    exit 1
}

log_success "a2a-bridge deployed"
