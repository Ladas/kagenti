#!/usr/bin/env bash
# Deploy k8s-readonly-server via MCPServer CRD (Toolhive)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/env-detect.sh"
source "$SCRIPT_DIR/../lib/logging.sh"

log_step "76" "Deploying k8s-readonly-server"

# Path to agentic-control-plane repo for RBAC manifests
ORCHESTRATOR_REPO="${ORCHESTRATOR_REPO:-$(dirname "$REPO_ROOT")/agentic-control-plane}"

if [ ! -d "$ORCHESTRATOR_REPO" ]; then
    log_error "agentic-control-plane repo not found at: $ORCHESTRATOR_REPO"
    log_info "Please clone it: git clone git@github.com:Ladas/agentic-control-plane.git"
    exit 1
fi

# Apply RBAC from agentic-control-plane (required for K8s read access)
log_info "Applying k8s-readonly-server RBAC..."
kubectl apply -f "$ORCHESTRATOR_REPO/deploy/k8s-readonly-server/01-serviceaccount.yaml"
kubectl apply -f "$ORCHESTRATOR_REPO/deploy/k8s-readonly-server/02-clusterrole.yaml"
kubectl apply -f "$ORCHESTRATOR_REPO/deploy/k8s-readonly-server/03-clusterrolebinding.yaml"

# Deploy via MCPServer CRD
log_info "Deploying k8s-readonly-server via MCPServer CRD..."
kubectl apply -f "$REPO_ROOT/kagenti/examples/mcpservers/k8s_readonly_server.yaml"

# Wait for StatefulSet to be created
log_info "Waiting for StatefulSet to be created..."
for i in {1..30}; do
    if kubectl get statefulset k8s-readonly-server -n kagenti-agents &> /dev/null; then
        log_info "StatefulSet created"
        break
    fi
    if [ "$i" -eq 30 ]; then
        log_error "StatefulSet not created after 60s"
        kubectl get mcpservers -n kagenti-agents
        kubectl describe mcpserver k8s-readonly-server -n kagenti-agents
        exit 1
    fi
    sleep 2
done

# NOTE: MCPServer (Toolhive) operator creates ServiceAccount with suffix "-sa"
# So we use the ClusterRoleBinding that binds to "k8s-readonly-server-sa"
# No need to patch the StatefulSet - just ensure the ClusterRoleBinding is correct
log_info "Verifying k8s-readonly-server-sa ServiceAccount exists..."
kubectl get sa k8s-readonly-server-sa -n kagenti-agents || true

# Delete existing pod to force recreation with new ServiceAccount
kubectl delete pod -n kagenti-agents -l app=k8s-readonly-server --wait=false 2>/dev/null || true

# Wait for pod to be ready
log_info "Waiting for k8s-readonly-server pod to be ready..."
kubectl wait --for=condition=ready --timeout=300s pod -n kagenti-agents -l app=k8s-readonly-server || {
    log_error "Pod not ready"
    kubectl get pods -n kagenti-agents -l app=k8s-readonly-server
    kubectl logs -n kagenti-agents -l app=k8s-readonly-server --tail=50 || true
    exit 1
}

log_success "k8s-readonly-server deployed"
