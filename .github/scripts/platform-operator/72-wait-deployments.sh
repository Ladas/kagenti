#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/env-detect.sh"
source "$SCRIPT_DIR/../lib/logging.sh"

log_step "72" "Waiting for weather deployments"

# Wait for weather-tool (macOS compatible - no timeout command)
for i in {1..60}; do
    if kubectl get deployment weather-tool -n team1 &> /dev/null; then
        break
    fi
    sleep 2
done
kubectl wait --for=condition=available --timeout=300s deployment/weather-tool -n team1 || {
    log_error "weather-tool deployment not available"
    kubectl get events -n team1 --sort-by='.lastTimestamp'
    exit 1
}

# Wait for weather-service (macOS compatible - no timeout command)
for i in {1..60}; do
    if kubectl get deployment weather-service -n team1 &> /dev/null; then
        break
    fi
    sleep 2
done
kubectl wait --for=condition=available --timeout=300s deployment/weather-service -n team1 || {
    log_error "weather-service deployment not available"
    kubectl get events -n team1 --sort-by='.lastTimestamp'
    exit 1
}

log_success "Deployments ready"
