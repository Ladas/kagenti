# Integrations Hub - Design Document

**Date**: 2026-02-28
**Status**: Approved
**Branch**: TBD (will use worktree)

## Overview

Add an **Integrations** section to the Kagenti UI that connects external repositories, webhooks, cron schedules, and alert sources to deployed agents. This enables autonomous agent workflows: CI monitoring, PR reviews, CVE scans, incident response - all triggered automatically.

## Architecture

### Navigation

Single "Integrations" nav item in the left sidebar, between Agentic Workloads and Gateway & Routing. Opens a tabbed page:

```
Home
Agentic Workloads (Agents, Tools)
Integrations              <-- NEW
  [Tabs: Repositories | Webhooks | Schedules | Alerts]
Gateway & Routing (MCP Gateway, AI Gateway, Gateway Policies)
Operations (Observability, Administration)
```

### Data Model: Integration CRD

Single CRD per repository with embedded webhook, schedule, and alert configs:

```yaml
apiVersion: kagenti.io/v1alpha1
kind: Integration
metadata:
  name: kagenti-main
  namespace: team1
  labels:
    kagenti.io/provider: github
spec:
  repository:
    url: https://github.com/kagenti/kagenti
    provider: github              # github | gitlab | bitbucket
    branch: main
    credentialsSecret: gh-token-team1   # Secret with token
  agents:                               # per-repo agent binding
    - name: tdd-agent
      namespace: team1
    - name: review-agent
      namespace: team1
  webhooks:
    - name: pr-events
      events: [pull_request, issue_comment]
      secret: webhook-secret-name       # HMAC validation secret
      filters:                          # optional event filtering
        branches: [main, "release/*"]
        actions: [opened, synchronize, created]
    - name: push-events
      events: [push]
      filters:
        branches: [main]
  schedules:
    - name: nightly-ci-check
      cron: "0 2 * * *"
      skill: tdd:ci
      agent: tdd-agent                  # which bound agent runs this
    - name: weekly-cve-scan
      cron: "0 6 * * 1"
      skill: security:scan
      agent: review-agent
  alerts:
    - name: critical-alerts
      source: prometheus                # prometheus | pagerduty
      matchLabels:
        severity: critical
        service: kagenti
      agent: tdd-agent
status:
  webhookUrl: https://kagenti.example.com/api/v1/integrations/team1/kagenti-main/webhook
  webhookRegistered: true
  lastWebhookEvent: "2026-02-28T10:30:00Z"
  lastScheduleRun: "2026-02-28T02:00:00Z"
  conditions:
    - type: Connected
      status: "True"
      lastTransitionTime: "2026-02-28T09:00:00Z"
    - type: WebhookActive
      status: "True"
```

### Backend API

New router: `kagenti/backend/app/routers/integrations.py`

```
GET    /api/v1/integrations?namespace=team1       List integrations
POST   /api/v1/integrations                        Create integration
GET    /api/v1/integrations/:ns/:name              Get detail
PUT    /api/v1/integrations/:ns/:name              Update
DELETE /api/v1/integrations/:ns/:name              Delete
POST   /api/v1/integrations/:ns/:name/webhook      Receive webhook (public, HMAC-validated)
POST   /api/v1/integrations/:ns/:name/test         Test connection
GET    /api/v1/integrations/:ns/:name/events       Event history (K8s events)
```

Auth: All endpoints require `kagenti-viewer` (read) or `kagenti-operator` (write) roles, except the webhook receiver which validates via HMAC signature.

### Trigger Flow

When a webhook fires, cron ticks, or alert triggers:

```
Event Source (GitHub/Cron/Prometheus)
  |
  v
Backend receives event
  |
  v
Lookup Integration CRD for repo/source
  |
  v
Resolve assigned agent(s)
  |
  v
Create SandboxClaim (sandbox agent system)
  - agent reference
  - event context (PR#, commit SHA, alert details)
  - skill to run (if specified)
  - TTL for auto-cleanup
  |
  v
Sandbox Agent picks up claim
  |
  v
Runs skill, reports results
  |
  v
HITL system handles approval if needed
```

This bridges directly into the sandbox agent trigger system already designed in `triggers.py`.

## UI Design

### Repositories Tab (main landing)

Table columns:
| Column | Description |
|--------|-------------|
| Name | Integration name (link to detail) |
| Repository | GitHub URL (external link) |
| Provider | github/gitlab/bitbucket icon |
| Agents | Assigned agent names as chips |
| Webhooks | Count of webhook configs |
| Schedules | Count of cron schedules |
| Status | Connected / Error / Pending badge |
| Actions | Edit, Delete, Test Connection |

### Add Integration Wizard

Step-by-step wizard:
1. **Connect Repository** - URL, provider dropdown, branch, credentials secret
2. **Assign Agents** - Multi-select from deployed agents in namespace
3. **Configure Webhooks** - Checkboxes for event types, branch filters
4. **Configure Schedules** - Cron expression builder, skill selector
5. **Configure Alerts** - Source type, match labels (optional step)

### Integration Detail Page

Route: `/integrations/:namespace/:name`

- Overview card: repo info, connection status, assigned agents
- Sub-tabs: Webhooks | Schedules | Alerts | Event History
- Each sub-tab shows configs with edit/delete/test actions
- Event History shows recent trigger events with outcomes

### Webhooks Tab (top-level)

Aggregated view of all webhook configs across all integrations:
- Which repos have webhooks
- Recent events received
- Delivery status (success/failure)
- Quick link to webhook settings

### Schedules Tab (top-level)

Aggregated view of all cron schedules:
- Schedule name, cron expression, next run time
- Assigned agent and skill
- Last run status
- Enable/disable toggle

### Alerts Tab (top-level)

Aggregated view of all alert triggers:
- Alert source (Prometheus/PagerDuty)
- Match criteria
- Assigned agent
- Recent alerts handled

## Storage

All state in Kubernetes via Custom Resource Definitions:
- `Integration` CRD (primary resource)
- Credentials in K8s Secrets (referenced by name)
- Event history via K8s Events on Integration resources
- No database required - follows existing stateless backend pattern

## Helm Chart Changes

Add to `charts/kagenti/templates/`:
- `integration-crd.yaml` - CRD definition
- `integration-clusterrole.yaml` - RBAC for Integration resources

## Use Cases Enabled

1. **Nightly CI Monitor**: Cron runs `tdd:ci` skill nightly, agent analyzes failures, creates draft PRs
2. **PR Review Agent**: Webhook on `pull_request.opened`, review-agent runs code review skills
3. **Comment-Triggered Agent**: Webhook on `issue_comment` with `/agent` prefix, parses command
4. **CVE Scanner**: Weekly cron runs security scan skill, reports findings
5. **Incident Responder**: Prometheus alert triggers agent with cluster kubeconfig for diagnosis
6. **Auto-Rebuild**: Push to main triggers Shipwright build via agent

## Dependencies

- Sandbox agent trigger system (`triggers.py` in sandbox-agent worktree)
- HITL approval system (`hitl.py` in sandbox-agent worktree)
- Deployed agents in namespace (existing)
- GitHub App or PAT for webhook registration (user-provided)
