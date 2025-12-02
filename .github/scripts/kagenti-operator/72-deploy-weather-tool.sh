#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/env-detect.sh"
source "$SCRIPT_DIR/../lib/logging.sh"

log_step "72" "Deploying weather-tool via Toolhive"

kubectl apply -f "$REPO_ROOT/kagenti/examples/mcpservers/weather_tool.yaml"

# Wait for StatefulSet to be created (quick wait - just for resource creation)
log_info "Waiting for StatefulSet to be created..."
for i in {1..30}; do
    if kubectl get statefulset weather-tool -n team1 &> /dev/null; then
        log_info "StatefulSet created"
        break
    fi
    if [ "$i" -eq 30 ]; then
        log_error "StatefulSet not created after 60s"
        kubectl get mcpservers -n team1
        kubectl describe mcpserver weather-tool -n team1
        kubectl logs -n toolhive-system deployment/toolhive-operator --tail=100 || true
        exit 1
    fi
    sleep 2
done

# Patch StatefulSet immediately with writable /tmp (required for uv cache)
log_info "Patching StatefulSet for writable /tmp..."
kubectl patch statefulset weather-tool -n team1 -p '{"spec":{"template":{"spec":{"volumes":[{"name":"tmp","emptyDir":{}}],"containers":[{"name":"mcp","volumeMounts":[{"name":"tmp","mountPath":"/tmp"}]}]}}}}'

# Delete existing pod to force recreation with new volume
kubectl delete pod -n team1 -l app=weather-tool --wait=false 2>/dev/null || true

# Now wait for pod to be ready
log_info "Waiting for weather-tool pod to be ready..."
kubectl wait --for=condition=ready --timeout=300s pod -n team1 -l app=weather-tool || {
    log_error "Pod not ready after patch"
    kubectl get pods -n team1 -l app=weather-tool
    kubectl logs -n team1 -l app=weather-tool --tail=50 || true
    exit 1
}

log_success "Weather-tool deployed and patched"
