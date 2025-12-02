#!/usr/bin/env bash
# Create AgentCard CRDs for deployed agents
#
# AgentCards enable agent discovery via the a2a-bridge discover_agents tool.
# Each AgentCard uses a selector to match against Agent CRDs.
#
# This script creates AgentCards for:
# - k8s-debug-agent: Kubernetes debugging agent
# - orchestrator-agent: Task orchestration agent
# - weather-service: Example weather agent
#
# NOTE: Each Agent CRD needs a unique label (kagenti.io/agent-name) for the
# AgentCard selector to work correctly. This script adds that label.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/env-detect.sh"
source "$SCRIPT_DIR/../lib/logging.sh"

log_step "81" "Creating AgentCards for agent discovery"

# ============================================================================
# Create AgentCard for k8s-debug-agent
# ============================================================================

if kubectl get agent k8s-debug-agent -n kagenti-agents &> /dev/null; then
    log_info "Adding unique label to k8s-debug-agent Agent..."
    kubectl label agent k8s-debug-agent -n kagenti-agents kagenti.io/agent-name=k8s-debug-agent --overwrite

    log_info "Creating AgentCard for k8s-debug-agent..."
    kubectl apply -f - <<EOF
apiVersion: agent.kagenti.dev/v1alpha1
kind: AgentCard
metadata:
  name: k8s-debug-agent
  namespace: kagenti-agents
spec:
  selector:
    matchLabels:
      kagenti.io/agent-name: k8s-debug-agent
  syncPeriod: "30s"
EOF
    log_success "AgentCard k8s-debug-agent created"
else
    log_info "k8s-debug-agent Agent not found, skipping AgentCard creation"
fi

# ============================================================================
# Create AgentCard for orchestrator-agent
# ============================================================================

if kubectl get agent orchestrator-agent -n kagenti-agents &> /dev/null; then
    log_info "Adding unique label to orchestrator-agent Agent..."
    kubectl label agent orchestrator-agent -n kagenti-agents kagenti.io/agent-name=orchestrator-agent --overwrite

    log_info "Creating AgentCard for orchestrator-agent..."
    kubectl apply -f - <<EOF
apiVersion: agent.kagenti.dev/v1alpha1
kind: AgentCard
metadata:
  name: orchestrator-agent
  namespace: kagenti-agents
spec:
  selector:
    matchLabels:
      kagenti.io/agent-name: orchestrator-agent
  syncPeriod: "30s"
EOF
    log_success "AgentCard orchestrator-agent created"
else
    log_info "orchestrator-agent Agent not found, skipping AgentCard creation"
fi

# ============================================================================
# Create AgentCard for weather-service
# ============================================================================

if kubectl get agent weather-service -n team1 &> /dev/null; then
    log_info "Adding unique label to weather-service Agent..."
    kubectl label agent weather-service -n team1 kagenti.io/agent-name=weather-service --overwrite

    log_info "Creating AgentCard for weather-service..."
    kubectl apply -f - <<EOF
apiVersion: agent.kagenti.dev/v1alpha1
kind: AgentCard
metadata:
  name: weather-service
  namespace: team1
spec:
  selector:
    matchLabels:
      kagenti.io/agent-name: weather-service
  syncPeriod: "30s"
EOF
    log_success "AgentCard weather-service created"
else
    log_info "weather-service Agent not found, skipping AgentCard creation"
fi

# ============================================================================
# Summary
# ============================================================================

log_info ""
log_info "AgentCards created:"
kubectl get agentcards -A 2>/dev/null || log_info "No AgentCards found"
log_info ""

log_success "AgentCard creation complete!"
