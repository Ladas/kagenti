#!/usr/bin/env bash
# Sync Agent Secrets (Wave 21)
# Creates/updates Kubernetes secrets for agent LLM API keys
#
# For local: Reads from deployments/envs/.secret_values.yaml
# For CI: Reads from environment variables (set from GitHub secrets)
#
# This script creates:
# - Secret: openai-api-key in kagenti-agents namespace

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/env-detect.sh"
source "$SCRIPT_DIR/../lib/logging.sh"

log_step "21" "Syncing agent secrets to Kubernetes"

# Namespace for agent secrets
AGENTS_NAMESPACE="kagenti-agents"

# Secret file path
SECRET_FILE="$REPO_ROOT/deployments/envs/.secret_values.yaml"

# ============================================================================
# Helper function to extract YAML value
# ============================================================================
extract_yaml_value() {
    local file="$1"
    local key_path="$2"

    # Use yq if available, otherwise fall back to grep/sed
    if command -v yq &> /dev/null; then
        yq -r "$key_path" "$file" 2>/dev/null || echo ""
    else
        # Fallback: simple grep for the key (works for flat structures)
        # This handles the agents.openapi_secret case
        local key=$(echo "$key_path" | sed 's/.*\.//')
        grep -A1 "^[[:space:]]*${key}:" "$file" 2>/dev/null | tail -1 | sed 's/^[[:space:]]*//' | tr -d '"' || echo ""
    fi
}

# ============================================================================
# Get OpenAI API Key
# ============================================================================
OPENAI_API_KEY=""

if [ "$IS_CI" = true ]; then
    # In CI: Read from environment variable (set from GitHub secret)
    OPENAI_API_KEY="${OPENAI_API_KEY:-}"

    if [ -z "$OPENAI_API_KEY" ]; then
        log_warning "OPENAI_API_KEY not set in CI environment"
        log_info "Set OPENAI_API_KEY secret in GitHub repository settings"
        log_info "Agents will fall back to Ollama if OpenAI key not available"
    fi
else
    # Local: Read from .secret_values.yaml
    if [ -f "$SECRET_FILE" ]; then
        # Use Python for proper YAML parsing (handles multiline strings correctly)
        OPENAI_API_KEY=$(python3 -c "
import yaml
import sys
try:
    with open('$SECRET_FILE') as f:
        data = yaml.safe_load(f)
    key = data.get('agents', {}).get('openapi_secret', '')
    if key:
        print(key, end='')
except Exception as e:
    print(f'Error parsing YAML: {e}', file=sys.stderr)
" 2>/dev/null || echo "")

        if [ -z "$OPENAI_API_KEY" ]; then
            log_warning "agents.openapi_secret not found in $SECRET_FILE"
            log_info "Add the following to your .secret_values.yaml:"
            log_info ""
            log_info "agents:"
            log_info "  openapi_secret: \"sk-your-openai-api-key\""
            log_info ""
        else
            log_info "Loaded OpenAI API key (${#OPENAI_API_KEY} chars)"
        fi
    else
        log_warning "Secret file not found: $SECRET_FILE"
        log_info "Create it with: cp deployments/envs/secret_values.yaml.example $SECRET_FILE"
    fi
fi

# ============================================================================
# Create/Update Kubernetes Secrets
# ============================================================================

# Ensure namespace exists
kubectl get namespace "$AGENTS_NAMESPACE" &>/dev/null || kubectl create namespace "$AGENTS_NAMESPACE"

if [ -n "$OPENAI_API_KEY" ]; then
    log_info "Creating/updating openai-api-key secret in $AGENTS_NAMESPACE namespace..."

    # Delete existing secret if it exists (to update)
    kubectl delete secret openai-api-key -n "$AGENTS_NAMESPACE" --ignore-not-found

    # Create new secret
    kubectl create secret generic openai-api-key \
        -n "$AGENTS_NAMESPACE" \
        --from-literal=api-key="$OPENAI_API_KEY"

    log_success "OpenAI API key secret created successfully"
else
    log_warning "Skipping OpenAI secret creation (no API key provided)"
    log_info "Agents will use Ollama as LLM backend"
fi
