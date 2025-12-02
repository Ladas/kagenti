#!/usr/bin/env bash
# Deploy orchestrator agents (k8s-readonly-server, a2a-bridge, k8s-debug-agent)
#
# This script orchestrates the full deployment of orchestrator agents:
# 1. Build k8s-readonly-server image (AgentBuild CRD)
# 2. Deploy k8s-readonly-server (MCPServer CRD)
# 3. Build a2a-bridge image (AgentBuild CRD)
# 4. Deploy a2a-bridge (MCPServer CRD)
# 5. Build k8s-debug-agent image (AgentBuild CRD)
# 6. Deploy k8s-debug-agent (Agent CRD)
#
# Prerequisites:
# - kagenti-operator installed with Agent/AgentBuild CRDs
# - toolhive-operator installed with MCPServer CRD
# - Tekton pipelines installed
# - agentic-control-plane repo cloned alongside this repo

set -euo pipefail

# Save our script directory BEFORE sourcing libs (env-detect.sh overwrites SCRIPT_DIR)
MY_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$MY_SCRIPT_DIR/../lib/env-detect.sh"
source "$MY_SCRIPT_DIR/../lib/logging.sh"

log_step "75" "Deploying orchestrator agents"

# ============================================================================
# Check prerequisites
# ============================================================================

log_info "Checking prerequisites..."

# Check for agentic-control-plane repo (needed for RBAC manifests)
ORCHESTRATOR_REPO="${ORCHESTRATOR_REPO:-$(dirname "$REPO_ROOT")/agentic-control-plane}"
if [ ! -d "$ORCHESTRATOR_REPO" ]; then
    log_warning "agentic-control-plane repo not found at: $ORCHESTRATOR_REPO"
    log_info "Orchestrator agents require this repo for RBAC manifests."
    log_info "Clone it: git clone https://github.com/kagenti/agentic-control-plane.git"
    log_info "Skipping orchestrator deployment..."
    exit 0
fi
log_info "Found agentic-control-plane at: $ORCHESTRATOR_REPO"

# ============================================================================
# Step 0: Sync agent secrets (OpenAI API key)
# ============================================================================

log_info "Step 0/7: Syncing agent secrets..."
bash "$MY_SCRIPT_DIR/../common/21-sync-agent-secrets.sh"

# ============================================================================
# Step 1: Build k8s-readonly-server
# ============================================================================

log_info "Step 1/7: Building k8s-readonly-server image..."
bash "$MY_SCRIPT_DIR/75-build-k8s-readonly-server.sh"

# ============================================================================
# Step 2: Deploy k8s-readonly-server
# ============================================================================

log_info "Step 2/7: Deploying k8s-readonly-server..."
bash "$MY_SCRIPT_DIR/76-deploy-k8s-readonly-server.sh"

# ============================================================================
# Step 3: Build a2a-bridge
# ============================================================================

log_info "Step 3/7: Building a2a-bridge image..."
bash "$MY_SCRIPT_DIR/79-build-a2a-bridge.sh"

# ============================================================================
# Step 4: Deploy a2a-bridge
# ============================================================================

log_info "Step 4/7: Deploying a2a-bridge..."
bash "$MY_SCRIPT_DIR/80-deploy-a2a-bridge.sh"

# ============================================================================
# Step 5: Build k8s-debug-agent
# ============================================================================

log_info "Step 5/7: Building k8s-debug-agent image..."
bash "$MY_SCRIPT_DIR/77-build-k8s-debug-agent.sh"

# ============================================================================
# Step 6: Deploy k8s-debug-agent
# ============================================================================

log_info "Step 6/7: Deploying k8s-debug-agent..."
bash "$MY_SCRIPT_DIR/78-deploy-k8s-debug-agent.sh"

# ============================================================================
# Step 7: Create AgentCards for agent discovery
# ============================================================================

log_info "Step 7/7: Creating AgentCards for agent discovery..."
bash "$MY_SCRIPT_DIR/81-create-agentcards.sh"

# ============================================================================
# Summary
# ============================================================================

log_info ""
log_info "Orchestrator agents deployment summary:"
log_info "========================================"
kubectl get pods -n kagenti-agents -o wide
log_info ""
log_info "Services:"
kubectl get svc -n kagenti-agents
log_info ""

# Port-forward info for local testing
log_info "For local testing, run port-forwards:"
log_info "  kubectl port-forward -n kagenti-agents svc/k8s-debug-agent 8001:8000"
log_info "  kubectl port-forward -n kagenti-agents svc/a2a-bridge 8002:8080"
log_info "  kubectl port-forward -n kagenti-agents svc/mcp-k8s-readonly-server-proxy 8003:8080"

log_success "All orchestrator agents deployed successfully!"
