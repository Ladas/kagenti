#!/usr/bin/env bash
# Deploy k8s-debug-agent via Agent CRD
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/env-detect.sh"
source "$SCRIPT_DIR/../lib/logging.sh"

log_step "78" "Deploying k8s-debug-agent"

# Deploy via Agent CRD
kubectl apply -f "$REPO_ROOT/kagenti/examples/agents/k8s_debug_agent.yaml"

# Wait for deployment to be created
log_info "Waiting for k8s-debug-agent deployment..."
for i in {1..150}; do
    if kubectl get deployment k8s-debug-agent -n kagenti-agents &> /dev/null; then
        break
    fi
    if [ "$i" -eq 150 ]; then
        log_error "Deployment not created after 300s"
        kubectl logs -n kagenti-system deployment/kagenti-controller-manager --tail=100 || true
        kubectl get agents -n kagenti-agents
        kubectl describe agent k8s-debug-agent -n kagenti-agents
        exit 1
    fi
    sleep 2
done

# Wait for deployment to be available
kubectl wait --for=condition=available --timeout=300s deployment/k8s-debug-agent -n kagenti-agents || {
    log_error "Deployment not available"
    kubectl get events -n kagenti-agents --sort-by='.lastTimestamp' | tail -20
    kubectl describe deployment k8s-debug-agent -n kagenti-agents
    kubectl logs -n kagenti-agents -l app=k8s-debug-agent --tail=50 || true
    exit 1
}

# Summary
log_info "Orchestrator agents status:"
kubectl get pods -n kagenti-agents
kubectl get svc -n kagenti-agents

log_success "k8s-debug-agent deployed successfully"
