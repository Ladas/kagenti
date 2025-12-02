#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/env-detect.sh"
source "$SCRIPT_DIR/../lib/logging.sh"

log_step "85" "Starting port-forward"

# ============================================================================
# Helper function for idempotent port-forward management
# ============================================================================

# Free a port by killing any process using it
free_port() {
    local port=$1
    if lsof -ti:${port} >/dev/null 2>&1; then
        log_info "Freeing port ${port} (killing existing process)"
        lsof -ti:${port} | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Start a port-forward idempotently
# Usage: start_port_forward <name> <local_port> <namespace> <resource> <remote_port> <health_path>
start_port_forward() {
    local name=$1
    local local_port=$2
    local namespace=$3
    local resource=$4
    local remote_port=$5
    local health_path=${6:-"/"}
    local pid_file="/tmp/port-forward-${name}.pid"
    local log_file="/tmp/port-forward-${name}.log"

    log_info "Port-forwarding ${name} -> localhost:${local_port}"

    # Free the port first (idempotent)
    free_port ${local_port}

    # Start port-forward in background
    kubectl port-forward -n ${namespace} ${resource} ${local_port}:${remote_port} > ${log_file} 2>&1 &
    local pid=$!

    if [ "$IS_CI" = true ]; then
        local env_var_name=$(echo "${name}_PORT_FORWARD_PID" | tr '[:lower:]-' '[:upper:]_')
        echo "${env_var_name}=${pid}" >> $GITHUB_ENV
    else
        echo $pid > ${pid_file}
    fi

    # Wait for port-forward to be ready
    for i in {1..10}; do
        if curl -s http://localhost:${local_port}${health_path} >/dev/null 2>&1; then
            log_success "${name} port-forward is ready (localhost:${local_port})"
            return 0
        fi
        sleep 1
    done
    log_info "${name} port-forward started (health check not responding, may still be starting)"
    return 0
}

# ============================================================================
# Port-forward weather-service (agent) to localhost:8000
# ============================================================================

# Get pod name
POD_NAME=$(kubectl get pod -n team1 -l app.kubernetes.io/name=weather-service -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -z "$POD_NAME" ]; then
    log_error "No weather-service pod found"
    kubectl get pods -n team1
    exit 1
fi

start_port_forward "weather-service" 8000 "team1" "pod/$POD_NAME" 8000

# ============================================================================
# Port-forward Keycloak to localhost:8081
# ============================================================================

start_port_forward "keycloak" 8081 "keycloak" "svc/keycloak-service" 8080

# ============================================================================
# Port-forward Phoenix to localhost:6006
# ============================================================================

start_port_forward "phoenix" 6006 "kagenti-system" "svc/phoenix" 6006 "/graphql"

# ============================================================================
# Port-forward k8s-debug-agent to localhost:8001
# ============================================================================

if kubectl get deployment k8s-debug-agent -n kagenti-agents &> /dev/null; then
    start_port_forward "k8s-debug-agent" 8001 "kagenti-agents" "deployment/k8s-debug-agent" 8000
else
    log_info "k8s-debug-agent not deployed, skipping port-forward"
fi

# ============================================================================
# Port-forward a2a-bridge to localhost:8002
# ============================================================================

if kubectl get deployment a2a-bridge -n kagenti-agents &> /dev/null; then
    start_port_forward "a2a-bridge" 8002 "kagenti-agents" "svc/a2a-bridge" 8080
else
    log_info "a2a-bridge not deployed, skipping port-forward"
fi

# ============================================================================
# Port-forward orchestrator-agent to localhost:8004
# ============================================================================

if kubectl get deployment orchestrator-agent -n kagenti-agents &> /dev/null; then
    # Use deployment directly since the service may have wrong targetPort (8080 vs app's 8000)
    start_port_forward "orchestrator-agent" 8004 "kagenti-agents" "deployment/orchestrator-agent" 8000 "/.well-known/agent.json"
else
    log_info "orchestrator-agent not deployed, skipping port-forward"
fi

log_success "All port-forwards started"
log_info "Port mappings: weather-service:8000, keycloak:8081, phoenix:6006, k8s-debug-agent:8001, a2a-bridge:8002, orchestrator-agent:8004"
