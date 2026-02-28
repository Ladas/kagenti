# Integrations Hub Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an Integrations section to the Kagenti UI that connects repositories, webhooks, cron schedules, and alert sources to deployed agents.

**Architecture:** Single `Integration` CRD per repository with embedded webhook/schedule/alert configs. Stateless FastAPI backend proxies to K8s API. React frontend with PatternFly 5, tabbed page layout. Triggers bridge to existing sandbox agent system.

**Tech Stack:** React 18 + TypeScript + PatternFly 5 + TanStack Query (frontend), FastAPI + kubernetes-client (backend), Custom CRD (storage)

---

### Task 1: Add Integration TypeScript types

**Files:**
- Modify: `kagenti/ui-v2/src/types/index.ts:288` (append after ApiErrorResponse)

**Step 1: Add types at the end of index.ts**

```typescript
// Integration types
export type IntegrationProvider = 'github' | 'gitlab' | 'bitbucket';

export type IntegrationStatus = 'Connected' | 'Error' | 'Pending';

export interface IntegrationWebhook {
  name: string;
  events: string[];
  filters?: {
    branches?: string[];
    actions?: string[];
  };
}

export interface IntegrationSchedule {
  name: string;
  cron: string;
  skill: string;
  agent: string;
  enabled?: boolean;
}

export interface IntegrationAlert {
  name: string;
  source: 'prometheus' | 'pagerduty';
  matchLabels: Record<string, string>;
  agent: string;
}

export interface IntegrationAgentRef {
  name: string;
  namespace: string;
}

export interface Integration {
  name: string;
  namespace: string;
  repository: {
    url: string;
    provider: IntegrationProvider;
    branch: string;
    credentialsSecret?: string;
  };
  agents: IntegrationAgentRef[];
  webhooks: IntegrationWebhook[];
  schedules: IntegrationSchedule[];
  alerts: IntegrationAlert[];
  status: IntegrationStatus;
  webhookUrl?: string;
  lastWebhookEvent?: string;
  lastScheduleRun?: string;
  createdAt?: string;
}

export interface IntegrationDetail extends Integration {
  conditions?: Array<{
    type: string;
    status: string;
    lastTransitionTime?: string;
    message?: string;
  }>;
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd kagenti/ui-v2 && npx tsc --noEmit 2>&1 | head -5`
Expected: No errors (or only pre-existing ones)

**Step 3: Commit**

```bash
git add kagenti/ui-v2/src/types/index.ts
git commit -s -m "feat(ui): add Integration TypeScript types"
```

---

### Task 2: Add Integration API service

**Files:**
- Modify: `kagenti/ui-v2/src/services/api.ts:663` (append after chatService)

**Step 1: Add integrationService at end of api.ts**

```typescript
/**
 * Integration service for managing repository integrations
 */
export const integrationService = {
  async list(namespace: string): Promise<Integration[]> {
    const response = await apiFetch<ApiListResponse<Integration>>(
      `/integrations?namespace=${encodeURIComponent(namespace)}`
    );
    return response.items;
  },

  async get(namespace: string, name: string): Promise<IntegrationDetail> {
    return apiFetch<IntegrationDetail>(
      `/integrations/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`
    );
  },

  async create(data: {
    name: string;
    namespace: string;
    repository: {
      url: string;
      provider: IntegrationProvider;
      branch: string;
      credentialsSecret?: string;
    };
    agents: IntegrationAgentRef[];
    webhooks?: IntegrationWebhook[];
    schedules?: IntegrationSchedule[];
    alerts?: IntegrationAlert[];
  }): Promise<{ success: boolean; name: string; namespace: string; message: string }> {
    return apiFetch('/integrations', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async update(
    namespace: string,
    name: string,
    data: Partial<{
      agents: IntegrationAgentRef[];
      webhooks: IntegrationWebhook[];
      schedules: IntegrationSchedule[];
      alerts: IntegrationAlert[];
    }>
  ): Promise<{ success: boolean; message: string }> {
    return apiFetch(
      `/integrations/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`,
      {
        method: 'PUT',
        body: JSON.stringify(data),
      }
    );
  },

  async delete(namespace: string, name: string): Promise<{ success: boolean; message: string }> {
    return apiFetch(
      `/integrations/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`,
      { method: 'DELETE' }
    );
  },

  async testConnection(
    namespace: string,
    name: string
  ): Promise<{ success: boolean; message: string }> {
    return apiFetch(
      `/integrations/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}/test`,
      { method: 'POST' }
    );
  },
};
```

**Step 2: Add import for new types at top of api.ts**

Add `Integration`, `IntegrationDetail`, `IntegrationProvider`, `IntegrationAgentRef`, `IntegrationWebhook`, `IntegrationSchedule`, `IntegrationAlert` to the import from `@/types`.

**Step 3: Verify TypeScript compiles**

Run: `cd kagenti/ui-v2 && npx tsc --noEmit 2>&1 | head -5`

**Step 4: Commit**

```bash
git add kagenti/ui-v2/src/services/api.ts
git commit -s -m "feat(ui): add Integration API service layer"
```

---

### Task 3: Create IntegrationsPage with tabs

**Files:**
- Create: `kagenti/ui-v2/src/pages/IntegrationsPage.tsx`

**Step 1: Create the page component**

Follow the `AgentCatalogPage` pattern. The page has 4 tabs: Repositories (default), Webhooks, Schedules, Alerts. The Repositories tab shows a table of integrations.

```typescript
// Copyright 2025 IBM Corp.
// Licensed under the Apache License, Version 2.0

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  PageSection,
  Title,
  Toolbar,
  ToolbarContent,
  ToolbarItem,
  Button,
  Spinner,
  EmptyState,
  EmptyStateHeader,
  EmptyStateIcon,
  EmptyStateBody,
  EmptyStateFooter,
  EmptyStateActions,
  Label,
  LabelGroup,
  Modal,
  ModalVariant,
  TextInput,
  Text,
  TextContent,
  Icon,
  Tabs,
  Tab,
  TabTitleText,
  Dropdown,
  DropdownList,
  DropdownItem,
  MenuToggle,
  MenuToggleElement,
} from '@patternfly/react-core';
import {
  Table,
  Thead,
  Tr,
  Th,
  Tbody,
  Td,
} from '@patternfly/react-table';
import {
  CodeBranchIcon,
  PlusCircleIcon,
  EllipsisVIcon,
  ExclamationTriangleIcon,
  BellIcon,
  ClockIcon,
  PluggedIcon,
} from '@patternfly/react-icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import type { Integration } from '@/types';
import { integrationService } from '@/services/api';
import { NamespaceSelector } from '@/components/NamespaceSelector';

export const IntegrationsPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [namespace, setNamespace] = useState<string>('team1');
  const [activeTabKey, setActiveTabKey] = useState<number>(0);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [integrationToDelete, setIntegrationToDelete] = useState<Integration | null>(null);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);

  const {
    data: integrations = [],
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ['integrations', namespace],
    queryFn: () => integrationService.list(namespace),
    enabled: !!namespace,
  });

  const deleteMutation = useMutation({
    mutationFn: ({ namespace: ns, name }: { namespace: string; name: string }) =>
      integrationService.delete(ns, name),
    onSuccess: (_data, variables) => {
      queryClient.setQueryData<Integration[]>(
        ['integrations', variables.namespace],
        (old) => old?.filter((i) => i.name !== variables.name) ?? []
      );
      queryClient.invalidateQueries({ queryKey: ['integrations', variables.namespace] });
      handleCloseDeleteModal();
    },
  });

  const handleDeleteClick = (integration: Integration) => {
    setIntegrationToDelete(integration);
    setDeleteModalOpen(true);
    setOpenMenuId(null);
  };

  const handleCloseDeleteModal = () => {
    setDeleteModalOpen(false);
    setIntegrationToDelete(null);
    setDeleteConfirmText('');
  };

  const handleDeleteConfirm = () => {
    if (integrationToDelete && deleteConfirmText === integrationToDelete.name) {
      deleteMutation.mutate({
        namespace: integrationToDelete.namespace,
        name: integrationToDelete.name,
      });
    }
  };

  const renderStatusBadge = (status: string) => {
    let color: 'green' | 'red' | 'blue' = 'red';
    if (status === 'Connected') color = 'green';
    else if (status === 'Pending') color = 'blue';
    return <Label color={color}>{status}</Label>;
  };

  const renderProviderLabel = (provider: string) => {
    const colors: Record<string, 'blue' | 'orange' | 'purple'> = {
      github: 'blue',
      gitlab: 'orange',
      bitbucket: 'purple',
    };
    return (
      <Label color={colors[provider] || 'blue'} isCompact>
        {provider}
      </Label>
    );
  };

  const getMenuId = (integration: Integration) =>
    `${integration.namespace}-${integration.name}`;

  // Aggregate counts across integrations for the tab badges
  const totalWebhooks = integrations.reduce((sum, i) => sum + (i.webhooks?.length || 0), 0);
  const totalSchedules = integrations.reduce((sum, i) => sum + (i.schedules?.length || 0), 0);
  const totalAlerts = integrations.reduce((sum, i) => sum + (i.alerts?.length || 0), 0);

  const repoColumns = ['Name', 'Repository', 'Provider', 'Agents', 'Webhooks', 'Schedules', 'Status', ''];

  const renderRepositoriesTab = () => (
    <>
      {isLoading ? (
        <div className="kagenti-loading-center">
          <Spinner size="lg" aria-label="Loading integrations" />
        </div>
      ) : isError ? (
        <EmptyState>
          <EmptyStateHeader
            titleText="Error loading integrations"
            icon={<EmptyStateIcon icon={CodeBranchIcon} />}
            headingLevel="h4"
          />
          <EmptyStateBody>
            {error instanceof Error
              ? error.message
              : 'Unable to fetch integrations from the cluster.'}
          </EmptyStateBody>
        </EmptyState>
      ) : integrations.length === 0 ? (
        <EmptyState>
          <EmptyStateHeader
            titleText="No integrations found"
            icon={<EmptyStateIcon icon={CodeBranchIcon} />}
            headingLevel="h4"
          />
          <EmptyStateBody>
            No integrations found in namespace &quot;{namespace}&quot;.
            Connect a repository to get started.
          </EmptyStateBody>
          <EmptyStateFooter>
            <EmptyStateActions>
              <Button
                variant="primary"
                onClick={() => navigate('/integrations/add')}
              >
                Add Integration
              </Button>
            </EmptyStateActions>
          </EmptyStateFooter>
        </EmptyState>
      ) : (
        <Table aria-label="Integrations table" variant="compact">
          <Thead>
            <Tr>
              {repoColumns.map((col, idx) => (
                <Th key={col || `col-${idx}`}>{col}</Th>
              ))}
            </Tr>
          </Thead>
          <Tbody>
            {integrations.map((integration) => {
              const menuId = getMenuId(integration);
              return (
                <Tr key={menuId}>
                  <Td dataLabel="Name">
                    <Button
                      variant="link"
                      isInline
                      onClick={() =>
                        navigate(`/integrations/${integration.namespace}/${integration.name}`)
                      }
                    >
                      {integration.name}
                    </Button>
                  </Td>
                  <Td dataLabel="Repository">
                    <a
                      href={integration.repository.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {integration.repository.url.replace(/^https?:\/\/(www\.)?/, '')}
                    </a>
                  </Td>
                  <Td dataLabel="Provider">
                    {renderProviderLabel(integration.repository.provider)}
                  </Td>
                  <Td dataLabel="Agents">
                    <LabelGroup>
                      {integration.agents.map((agent) => (
                        <Label key={agent.name} color="cyan" isCompact>
                          {agent.name}
                        </Label>
                      ))}
                    </LabelGroup>
                  </Td>
                  <Td dataLabel="Webhooks">{integration.webhooks?.length || 0}</Td>
                  <Td dataLabel="Schedules">{integration.schedules?.length || 0}</Td>
                  <Td dataLabel="Status">
                    {renderStatusBadge(integration.status)}
                  </Td>
                  <Td isActionCell>
                    <Dropdown
                      isOpen={openMenuId === menuId}
                      onSelect={() => setOpenMenuId(null)}
                      onOpenChange={(isOpen) =>
                        setOpenMenuId(isOpen ? menuId : null)
                      }
                      toggle={(toggleRef: React.Ref<MenuToggleElement>) => (
                        <MenuToggle
                          ref={toggleRef}
                          aria-label="Actions menu"
                          variant="plain"
                          onClick={() =>
                            setOpenMenuId(openMenuId === menuId ? null : menuId)
                          }
                          isExpanded={openMenuId === menuId}
                        >
                          <EllipsisVIcon />
                        </MenuToggle>
                      )}
                      popperProps={{ position: 'right' }}
                    >
                      <DropdownList>
                        <DropdownItem
                          key="view"
                          onClick={() =>
                            navigate(
                              `/integrations/${integration.namespace}/${integration.name}`
                            )
                          }
                        >
                          View details
                        </DropdownItem>
                        <DropdownItem
                          key="delete"
                          onClick={() => handleDeleteClick(integration)}
                          isDanger
                        >
                          Delete integration
                        </DropdownItem>
                      </DropdownList>
                    </Dropdown>
                  </Td>
                </Tr>
              );
            })}
          </Tbody>
        </Table>
      )}
    </>
  );

  const renderWebhooksTab = () => (
    <EmptyState>
      <EmptyStateHeader
        titleText="Webhooks"
        icon={<EmptyStateIcon icon={PluggedIcon} />}
        headingLevel="h4"
      />
      <EmptyStateBody>
        {totalWebhooks === 0
          ? 'No webhooks configured. Add an integration with webhook events to get started.'
          : `${totalWebhooks} webhook configuration(s) across ${integrations.filter(i => (i.webhooks?.length || 0) > 0).length} integration(s).`}
      </EmptyStateBody>
    </EmptyState>
  );

  const renderSchedulesTab = () => (
    <EmptyState>
      <EmptyStateHeader
        titleText="Schedules"
        icon={<EmptyStateIcon icon={ClockIcon} />}
        headingLevel="h4"
      />
      <EmptyStateBody>
        {totalSchedules === 0
          ? 'No schedules configured. Add an integration with cron schedules to get started.'
          : `${totalSchedules} schedule(s) across ${integrations.filter(i => (i.schedules?.length || 0) > 0).length} integration(s).`}
      </EmptyStateBody>
    </EmptyState>
  );

  const renderAlertsTab = () => (
    <EmptyState>
      <EmptyStateHeader
        titleText="Alerts"
        icon={<EmptyStateIcon icon={BellIcon} />}
        headingLevel="h4"
      />
      <EmptyStateBody>
        {totalAlerts === 0
          ? 'No alert triggers configured. Add an integration with alert sources to get started.'
          : `${totalAlerts} alert trigger(s) across ${integrations.filter(i => (i.alerts?.length || 0) > 0).length} integration(s).`}
      </EmptyStateBody>
    </EmptyState>
  );

  return (
    <>
      <PageSection variant="light">
        <Title headingLevel="h1">Integrations</Title>
      </PageSection>

      <PageSection variant="light" padding={{ default: 'noPadding' }}>
        <Toolbar>
          <ToolbarContent>
            <ToolbarItem>
              <NamespaceSelector
                namespace={namespace}
                onNamespaceChange={setNamespace}
              />
            </ToolbarItem>
            <ToolbarItem>
              <Button
                variant="primary"
                icon={<PlusCircleIcon />}
                onClick={() => navigate('/integrations/add')}
              >
                Add Integration
              </Button>
            </ToolbarItem>
          </ToolbarContent>
        </Toolbar>
      </PageSection>

      <PageSection variant="light" padding={{ default: 'noPadding' }}>
        <Tabs
          activeKey={activeTabKey}
          onSelect={(_e, tabIndex) => setActiveTabKey(tabIndex as number)}
          aria-label="Integration tabs"
          role="region"
        >
          <Tab
            eventKey={0}
            title={<TabTitleText>Repositories</TabTitleText>}
            aria-label="Repositories tab"
          >
            <PageSection>{renderRepositoriesTab()}</PageSection>
          </Tab>
          <Tab
            eventKey={1}
            title={<TabTitleText>Webhooks {totalWebhooks > 0 && `(${totalWebhooks})`}</TabTitleText>}
            aria-label="Webhooks tab"
          >
            <PageSection>{renderWebhooksTab()}</PageSection>
          </Tab>
          <Tab
            eventKey={2}
            title={<TabTitleText>Schedules {totalSchedules > 0 && `(${totalSchedules})`}</TabTitleText>}
            aria-label="Schedules tab"
          >
            <PageSection>{renderSchedulesTab()}</PageSection>
          </Tab>
          <Tab
            eventKey={3}
            title={<TabTitleText>Alerts {totalAlerts > 0 && `(${totalAlerts})`}</TabTitleText>}
            aria-label="Alerts tab"
          >
            <PageSection>{renderAlertsTab()}</PageSection>
          </Tab>
        </Tabs>
      </PageSection>

      {/* Delete Warning Modal */}
      <Modal
        variant={ModalVariant.small}
        titleIconVariant="warning"
        title="Delete integration?"
        isOpen={deleteModalOpen}
        onClose={handleCloseDeleteModal}
        actions={[
          <Button
            key="delete"
            variant="danger"
            onClick={handleDeleteConfirm}
            isLoading={deleteMutation.isPending}
            isDisabled={
              deleteMutation.isPending ||
              deleteConfirmText !== integrationToDelete?.name
            }
          >
            Delete
          </Button>,
          <Button
            key="cancel"
            variant="link"
            onClick={handleCloseDeleteModal}
            isDisabled={deleteMutation.isPending}
          >
            Cancel
          </Button>,
        ]}
      >
        <TextContent>
          <Text>
            <Icon status="warning" style={{ marginRight: '8px' }}>
              <ExclamationTriangleIcon />
            </Icon>
            The integration <strong>{integrationToDelete?.name}</strong> will be
            permanently deleted. This removes all webhook, schedule, and alert
            configurations.
          </Text>
          <Text component="small" style={{ marginTop: '16px', display: 'block' }}>
            Type <strong>{integrationToDelete?.name}</strong> to confirm deletion:
          </Text>
        </TextContent>
        <TextInput
          id="delete-confirm-input"
          value={deleteConfirmText}
          onChange={(_e, value) => setDeleteConfirmText(value)}
          aria-label="Confirm integration name"
          style={{ marginTop: '8px' }}
        />
      </Modal>
    </>
  );
};
```

**Step 2: Verify TypeScript compiles**

Run: `cd kagenti/ui-v2 && npx tsc --noEmit 2>&1 | head -5`

**Step 3: Commit**

```bash
git add kagenti/ui-v2/src/pages/IntegrationsPage.tsx
git commit -s -m "feat(ui): create IntegrationsPage with tabbed layout"
```

---

### Task 4: Add route and navigation

**Files:**
- Modify: `kagenti/ui-v2/src/App.tsx:22` (add import and routes)
- Modify: `kagenti/ui-v2/src/components/AppLayout.tsx:338` (add nav item after Agentic Workloads group)

**Step 1: Add import and routes to App.tsx**

After the `NotFoundPage` import (line 22), add:
```typescript
import { IntegrationsPage } from './pages/IntegrationsPage';
```

After the tools routes block (after line 95), add:
```typescript
        <Route
          path="/integrations"
          element={
            <ProtectedRoute>
              <IntegrationsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/integrations/add"
          element={
            <ProtectedRoute>
              <IntegrationsPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/integrations/:namespace/:name"
          element={
            <ProtectedRoute>
              <IntegrationsPage />
            </ProtectedRoute>
          }
        />
```

**Step 2: Add nav item to AppLayout.tsx**

After the closing `</NavGroup>` for "Agentic Workloads" (line 338), add a new NavItem (as a standalone item, not a group, matching user's choice):

```typescript
              <NavList>
                <NavItem
                  itemId="integrations"
                  isActive={isNavItemActive('/integrations')}
                  onClick={() => handleNavSelect('/integrations')}
                >
                  Integrations
                </NavItem>
              </NavList>
```

**Step 3: Verify the app builds**

Run: `cd kagenti/ui-v2 && npx tsc --noEmit 2>&1 | head -5`

**Step 4: Commit**

```bash
git add kagenti/ui-v2/src/App.tsx kagenti/ui-v2/src/components/AppLayout.tsx
git commit -s -m "feat(ui): add Integrations to navigation and routing"
```

---

### Task 5: Create backend Integration router (list/get/create/delete)

**Files:**
- Create: `kagenti/backend/app/routers/integrations.py`
- Modify: `kagenti/backend/app/main.py:34` (add import and router registration)

**Step 1: Create the integrations router**

```python
# Copyright 2025 IBM Corp.
# Licensed under the Apache License, Version 2.0

"""
Integration API endpoints.

Manages Integration custom resources that connect repositories
to agents via webhooks, cron schedules, and alert triggers.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.auth import require_roles, ROLE_VIEWER, ROLE_OPERATOR
from app.services.kubernetes import KubernetesService, get_kubernetes_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

# CRD constants
CRD_GROUP = "kagenti.io"
CRD_VERSION = "v1alpha1"
CRD_PLURAL = "integrations"


# Request/Response models
class IntegrationAgentRef(BaseModel):
    name: str
    namespace: str


class IntegrationWebhook(BaseModel):
    name: str
    events: list[str]
    filters: Optional[dict] = None


class IntegrationSchedule(BaseModel):
    name: str
    cron: str
    skill: str
    agent: str
    enabled: bool = True


class IntegrationAlert(BaseModel):
    name: str
    source: str  # prometheus | pagerduty
    matchLabels: dict[str, str]
    agent: str


class RepositorySpec(BaseModel):
    url: str
    provider: str = "github"
    branch: str = "main"
    credentialsSecret: Optional[str] = None


class CreateIntegrationRequest(BaseModel):
    name: str
    namespace: str
    repository: RepositorySpec
    agents: list[IntegrationAgentRef]
    webhooks: list[IntegrationWebhook] = []
    schedules: list[IntegrationSchedule] = []
    alerts: list[IntegrationAlert] = []


class IntegrationSummary(BaseModel):
    name: str
    namespace: str
    repository: dict
    agents: list[dict]
    webhooks: list[dict]
    schedules: list[dict]
    alerts: list[dict]
    status: str
    webhookUrl: Optional[str] = None
    lastWebhookEvent: Optional[str] = None
    lastScheduleRun: Optional[str] = None
    createdAt: Optional[str] = None


class IntegrationListResponse(BaseModel):
    items: list[IntegrationSummary]


def _crd_to_summary(obj: dict) -> IntegrationSummary:
    """Convert a K8s Integration CRD object to an IntegrationSummary."""
    metadata = obj.get("metadata", {})
    spec = obj.get("spec", {})
    obj_status = obj.get("status", {})

    # Determine status from conditions
    conditions = obj_status.get("conditions", [])
    integration_status = "Pending"
    for cond in conditions:
        if cond.get("type") == "Connected" and cond.get("status") == "True":
            integration_status = "Connected"
            break
        if cond.get("type") == "Error":
            integration_status = "Error"
            break

    return IntegrationSummary(
        name=metadata.get("name", ""),
        namespace=metadata.get("namespace", ""),
        repository=spec.get("repository", {}),
        agents=[a for a in spec.get("agents", [])],
        webhooks=spec.get("webhooks", []),
        schedules=spec.get("schedules", []),
        alerts=spec.get("alerts", []),
        status=integration_status,
        webhookUrl=obj_status.get("webhookUrl"),
        lastWebhookEvent=obj_status.get("lastWebhookEvent"),
        lastScheduleRun=obj_status.get("lastScheduleRun"),
        createdAt=metadata.get("creationTimestamp"),
    )


@router.get(
    "",
    response_model=IntegrationListResponse,
    dependencies=[Depends(require_roles(ROLE_VIEWER))],
)
async def list_integrations(
    namespace: str = Query(..., description="Namespace to list integrations from"),
    kube: KubernetesService = Depends(get_kubernetes_service),
) -> IntegrationListResponse:
    """List Integration resources in a namespace."""
    try:
        result = kube.custom_api.list_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=namespace,
            plural=CRD_PLURAL,
        )
        items = [_crd_to_summary(obj) for obj in result.get("items", [])]
        return IntegrationListResponse(items=items)
    except Exception as e:
        logger.error(f"Failed to list integrations in {namespace}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list integrations: {str(e)}",
        )


@router.get(
    "/{namespace}/{name}",
    dependencies=[Depends(require_roles(ROLE_VIEWER))],
)
async def get_integration(
    namespace: str,
    name: str,
    kube: KubernetesService = Depends(get_kubernetes_service),
):
    """Get a specific Integration resource."""
    try:
        obj = kube.custom_api.get_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=namespace,
            plural=CRD_PLURAL,
            name=name,
        )
        summary = _crd_to_summary(obj)
        # Add conditions for detail view
        obj_status = obj.get("status", {})
        return {
            **summary.model_dump(),
            "conditions": obj_status.get("conditions", []),
        }
    except Exception as e:
        if "NotFound" in str(e) or "404" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Integration {namespace}/{name} not found",
            )
        logger.error(f"Failed to get integration {namespace}/{name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get integration: {str(e)}",
        )


@router.post(
    "",
    dependencies=[Depends(require_roles(ROLE_OPERATOR))],
)
async def create_integration(
    request: CreateIntegrationRequest,
    kube: KubernetesService = Depends(get_kubernetes_service),
):
    """Create a new Integration resource."""
    body = {
        "apiVersion": f"{CRD_GROUP}/{CRD_VERSION}",
        "kind": "Integration",
        "metadata": {
            "name": request.name,
            "namespace": request.namespace,
            "labels": {
                "kagenti.io/provider": request.repository.provider,
            },
        },
        "spec": {
            "repository": request.repository.model_dump(exclude_none=True),
            "agents": [a.model_dump() for a in request.agents],
            "webhooks": [w.model_dump(exclude_none=True) for w in request.webhooks],
            "schedules": [s.model_dump() for s in request.schedules],
            "alerts": [a.model_dump() for a in request.alerts],
        },
    }

    try:
        kube.custom_api.create_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=request.namespace,
            plural=CRD_PLURAL,
            body=body,
        )
        return {
            "success": True,
            "name": request.name,
            "namespace": request.namespace,
            "message": f"Integration {request.name} created",
        }
    except Exception as e:
        if "AlreadyExists" in str(e) or "409" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Integration {request.name} already exists in {request.namespace}",
            )
        logger.error(f"Failed to create integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create integration: {str(e)}",
        )


@router.put(
    "/{namespace}/{name}",
    dependencies=[Depends(require_roles(ROLE_OPERATOR))],
)
async def update_integration(
    namespace: str,
    name: str,
    request: dict,
    kube: KubernetesService = Depends(get_kubernetes_service),
):
    """Update an existing Integration resource (partial spec update)."""
    try:
        # Get existing object
        obj = kube.custom_api.get_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=namespace,
            plural=CRD_PLURAL,
            name=name,
        )

        # Merge spec updates
        spec = obj.get("spec", {})
        for key in ["agents", "webhooks", "schedules", "alerts"]:
            if key in request:
                spec[key] = request[key]
        obj["spec"] = spec

        kube.custom_api.replace_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=namespace,
            plural=CRD_PLURAL,
            name=name,
            body=obj,
        )
        return {"success": True, "message": f"Integration {name} updated"}
    except Exception as e:
        if "NotFound" in str(e) or "404" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Integration {namespace}/{name} not found",
            )
        logger.error(f"Failed to update integration {namespace}/{name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update integration: {str(e)}",
        )


@router.delete(
    "/{namespace}/{name}",
    dependencies=[Depends(require_roles(ROLE_OPERATOR))],
)
async def delete_integration(
    namespace: str,
    name: str,
    kube: KubernetesService = Depends(get_kubernetes_service),
):
    """Delete an Integration resource."""
    try:
        kube.custom_api.delete_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=namespace,
            plural=CRD_PLURAL,
            name=name,
        )
        return {"success": True, "message": f"Integration {name} deleted"}
    except Exception as e:
        if "NotFound" in str(e) or "404" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Integration {namespace}/{name} not found",
            )
        logger.error(f"Failed to delete integration {namespace}/{name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete integration: {str(e)}",
        )


@router.post(
    "/{namespace}/{name}/test",
    dependencies=[Depends(require_roles(ROLE_OPERATOR))],
)
async def test_integration_connection(
    namespace: str,
    name: str,
    kube: KubernetesService = Depends(get_kubernetes_service),
):
    """Test connectivity to the integration's repository."""
    try:
        obj = kube.custom_api.get_namespaced_custom_object(
            group=CRD_GROUP,
            version=CRD_VERSION,
            namespace=namespace,
            plural=CRD_PLURAL,
            name=name,
        )
        repo_url = obj.get("spec", {}).get("repository", {}).get("url", "")
        # Basic connectivity test - check if repo URL is reachable
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.head(repo_url, timeout=10.0, follow_redirects=True)
            if response.status_code < 400:
                return {"success": True, "message": f"Repository {repo_url} is reachable"}
            return {
                "success": False,
                "message": f"Repository returned status {response.status_code}",
            }
    except httpx.HTTPError as e:
        return {"success": False, "message": f"Connection failed: {str(e)}"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test failed: {str(e)}",
        )
```

**Step 2: Register router in main.py**

In `kagenti/backend/app/main.py`, add to the import line (line 34):
```python
from app.routers import agents, tools, namespaces, config, auth, chat, integrations
```

After line 106, add:
```python
app.include_router(integrations.router, prefix="/api/v1")
```

**Step 3: Verify backend starts**

Run: `cd kagenti/backend && python -c "from app.routers.integrations import router; print('OK')" 2>&1`

**Step 4: Commit**

```bash
git add kagenti/backend/app/routers/integrations.py kagenti/backend/app/main.py
git commit -s -m "feat(backend): add Integration API router for CRD management"
```

---

### Task 6: Add Integration CRD to Helm chart

**Files:**
- Create: `charts/kagenti/templates/integration-crd.yaml`

**Step 1: Create the CRD definition**

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: integrations.kagenti.io
  labels:
    app.kubernetes.io/part-of: kagenti
spec:
  group: kagenti.io
  versions:
    - name: v1alpha1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              properties:
                repository:
                  type: object
                  required: [url, provider]
                  properties:
                    url:
                      type: string
                    provider:
                      type: string
                      enum: [github, gitlab, bitbucket]
                    branch:
                      type: string
                      default: main
                    credentialsSecret:
                      type: string
                agents:
                  type: array
                  items:
                    type: object
                    required: [name, namespace]
                    properties:
                      name:
                        type: string
                      namespace:
                        type: string
                webhooks:
                  type: array
                  items:
                    type: object
                    required: [name, events]
                    properties:
                      name:
                        type: string
                      events:
                        type: array
                        items:
                          type: string
                      secret:
                        type: string
                      filters:
                        type: object
                        properties:
                          branches:
                            type: array
                            items:
                              type: string
                          actions:
                            type: array
                            items:
                              type: string
                schedules:
                  type: array
                  items:
                    type: object
                    required: [name, cron, skill, agent]
                    properties:
                      name:
                        type: string
                      cron:
                        type: string
                      skill:
                        type: string
                      agent:
                        type: string
                      enabled:
                        type: boolean
                        default: true
                alerts:
                  type: array
                  items:
                    type: object
                    required: [name, source, agent]
                    properties:
                      name:
                        type: string
                      source:
                        type: string
                        enum: [prometheus, pagerduty]
                      matchLabels:
                        type: object
                        additionalProperties:
                          type: string
                      agent:
                        type: string
            status:
              type: object
              properties:
                webhookUrl:
                  type: string
                webhookRegistered:
                  type: boolean
                lastWebhookEvent:
                  type: string
                lastScheduleRun:
                  type: string
                conditions:
                  type: array
                  items:
                    type: object
                    properties:
                      type:
                        type: string
                      status:
                        type: string
                      lastTransitionTime:
                        type: string
                        format: date-time
                      message:
                        type: string
      subresources:
        status: {}
      additionalPrinterColumns:
        - name: Provider
          type: string
          jsonPath: .spec.repository.provider
        - name: URL
          type: string
          jsonPath: .spec.repository.url
        - name: Age
          type: date
          jsonPath: .metadata.creationTimestamp
  scope: Namespaced
  names:
    plural: integrations
    singular: integration
    kind: Integration
    shortNames:
      - intg
```

**Step 2: Verify Helm template renders**

Run: `cd charts/kagenti && helm template . --show-only templates/integration-crd.yaml 2>&1 | head -5`

**Step 3: Commit**

```bash
git add charts/kagenti/templates/integration-crd.yaml
git commit -s -m "feat(helm): add Integration CRD definition"
```

---

### Task 7: Add RBAC for Integration CRD

**Files:**
- Check existing: `charts/kagenti/templates/` for clusterrole files
- Create or modify: RBAC rules for the backend service account to manage Integration CRDs

**Step 1: Find existing RBAC templates**

Run: `ls charts/kagenti/templates/*role* charts/kagenti/templates/*rbac* 2>/dev/null`

**Step 2: Add Integration rules**

Add rules to the existing clusterrole (or create new one) allowing the backend to manage `integrations.kagenti.io`:

```yaml
- apiGroups: ["kagenti.io"]
  resources: ["integrations", "integrations/status"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
```

**Step 3: Verify Helm template renders**

Run: `helm template charts/kagenti --show-only templates/<rbac-file>.yaml 2>&1 | head -10`

**Step 4: Commit**

```bash
git add charts/kagenti/templates/
git commit -s -m "feat(helm): add RBAC rules for Integration CRD"
```

---

### Task 8: Verify full build and run lint

**Files:** None (verification only)

**Step 1: Run frontend TypeScript check**

Run: `cd kagenti/ui-v2 && npx tsc --noEmit 2>&1 | tail -5`
Expected: No new errors

**Step 2: Run pre-commit hooks**

Run: `pre-commit run --all-files 2>&1 | tail -10`
Expected: All checks pass

**Step 3: Run frontend build**

Run: `cd kagenti/ui-v2 && npm run build 2>&1 | tail -5`
Expected: Build succeeds

**Step 4: Final commit if any lint fixes needed**

```bash
git add -A
git commit -s -m "fix: lint and formatting fixes for integrations feature"
```

---

## Future Tasks (not in this PR)

These are documented for follow-up PRs:

- **Add Integration wizard** - Multi-step form for creating integrations (connect repo, assign agents, configure webhooks/schedules/alerts)
- **Integration detail page** - Dedicated page at `/integrations/:ns/:name` with sub-tabs
- **Webhook receiver endpoint** - Public endpoint with HMAC validation for GitHub webhooks
- **Cron scheduler** - Background loop or K8s CronJob that triggers SandboxClaims
- **Alert receiver** - Prometheus alertmanager webhook receiver
- **Bridge to sandbox agent** - Create SandboxClaim from trigger events
- **Webhooks tab content** - Full table with delivery history
- **Schedules tab content** - Full table with next/last run times
- **Alerts tab content** - Full table with recent alerts handled
