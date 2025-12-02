#!/usr/bin/env bash
# Build k8s-readonly-server image via AgentBuild CRD
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/env-detect.sh"
source "$SCRIPT_DIR/../lib/logging.sh"

log_step "75" "Building k8s-readonly-server image"

# Ensure kagenti-agents namespace exists
kubectl create namespace kagenti-agents --dry-run=client -o yaml | kubectl apply -f -

# Copy required secrets to kagenti-agents namespace if they exist in team1
if kubectl get secret github-token-secret -n team1 &> /dev/null; then
    kubectl get secret github-token-secret -n team1 -o yaml | \
        sed 's/namespace: team1/namespace: kagenti-agents/' | \
        kubectl apply -f - 2>/dev/null || true
fi

# Copy ghcr-secret for buildah push to internal registry
if kubectl get secret ghcr-secret -n team1 &> /dev/null; then
    kubectl get secret ghcr-secret -n team1 -o yaml | \
        sed 's/namespace: team1/namespace: kagenti-agents/' | \
        kubectl apply -f - 2>/dev/null || true
fi

kubectl apply -f "$REPO_ROOT/kagenti/examples/mcpservers/k8s_readonly_server_build.yaml"

# Wait for AgentBuild to exist
for i in {1..150}; do
    if kubectl get agentbuild k8s-readonly-server-build -n kagenti-agents &> /dev/null; then
        break
    fi
    if [ "$i" -eq 150 ]; then
        log_error "AgentBuild not created after 300s"
        kubectl get agentbuilds -n kagenti-agents
        exit 1
    fi
    sleep 2
done

# Wait for build to succeed
for i in {1..90}; do
    phase=$(kubectl get agentbuild k8s-readonly-server-build -n kagenti-agents -o jsonpath='{.status.phase}' 2>/dev/null || echo "Unknown")
    log_info "AgentBuild phase: $phase"
    if [ "$phase" = "Succeeded" ]; then
        log_success "k8s-readonly-server build completed successfully"
        exit 0
    elif [ "$phase" = "Failed" ]; then
        log_error "AgentBuild failed"
        kubectl describe agentbuild k8s-readonly-server-build -n kagenti-agents
        kubectl get pipelineruns -n kagenti-system -l tekton.dev/pipeline=agent-build --sort-by=.metadata.creationTimestamp | tail -3
        exit 1
    fi
    sleep 5
done

log_error "AgentBuild timeout"
exit 1
