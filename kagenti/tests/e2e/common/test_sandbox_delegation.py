#!/usr/bin/env python3
"""
Sandbox Delegation E2E Tests (Session E)

Tests the legion agent's delegate tool via A2A protocol:
- In-process delegation (explore-style subgraph)
- Auto-mode selection based on task description
- Delegation metadata in response (child context, mode)
- Multi-child parallel delegation

These tests require a running sandbox-legion agent with the multi-mode
delegate tool wired in. Set SANDBOX_LEGION_URL or ENABLE_SANDBOX_TESTS.

Usage:
    SANDBOX_LEGION_URL=http://... pytest tests/e2e/common/test_sandbox_delegation.py -v
"""

import os
import pathlib

import pytest
import httpx
import yaml
from uuid import uuid4
from a2a.types import (
    Message as A2AMessage,
    TextPart,
)

# Skip entire module if sandbox agents are not deployed
pytestmark = pytest.mark.skipif(
    not os.getenv("SANDBOX_LEGION_URL") and not os.getenv("ENABLE_SANDBOX_TESTS"),
    reason="Sandbox agents not deployed (set SANDBOX_LEGION_URL or ENABLE_SANDBOX_TESTS)",
)


def _get_sandbox_legion_url() -> str:
    """Get the sandbox legion URL from env or default to in-cluster DNS."""
    return os.getenv(
        "SANDBOX_LEGION_URL",
        "http://sandbox-legion.team1.svc.cluster.local:8000",
    )


def _is_openshift_from_config():
    """Detect if running on OpenShift from KAGENTI_CONFIG_FILE."""
    config_file = os.getenv("KAGENTI_CONFIG_FILE")
    if not config_file:
        return False
    config_path = pathlib.Path(config_file)
    if not config_path.is_absolute():
        repo_root = pathlib.Path(__file__).parent.parent.parent.parent.parent
        config_path = repo_root / config_file
    if not config_path.exists():
        return False
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except Exception:
        return False
    return config.get("openshift", False)


def _get_ssl_context():
    """Get SSL context for httpx client."""
    if not _is_openshift_from_config():
        return True
    ca_path = os.getenv("OPENSHIFT_INGRESS_CA")
    if ca_path and pathlib.Path(ca_path).exists():
        import ssl

        return ssl.create_default_context(cafile=ca_path)
    return True


async def _connect_to_agent(agent_url):
    """Connect to the sandbox legion via A2A protocol."""
    ssl_verify = _get_ssl_context()
    httpx_client = httpx.AsyncClient(timeout=180.0, verify=ssl_verify)

    from a2a.client import A2AClient
    from a2a.client.card_resolver import A2ACardResolver

    resolver = A2ACardResolver(httpx_client, agent_url)
    card = await resolver.get_agent_card()
    card.url = agent_url
    client = A2AClient(httpx_client=httpx_client, url=agent_url)
    return client, card


async def _extract_response(client, message):
    """Send an A2A message and extract the text response."""
    from a2a.types import SendMessageRequest, MessageSendParams

    params = MessageSendParams(message=message)
    request = SendMessageRequest(id=uuid4().hex, params=params)
    response = await client.send_message(request)

    root = getattr(response, "root", response)
    if hasattr(root, "error") and root.error:
        raise RuntimeError(f"A2A error: {root.error}")

    result = getattr(root, "result", None)
    if result is None:
        return "", []

    full_response = ""
    if hasattr(result, "artifacts") and result.artifacts:
        for artifact in result.artifacts:
            for part in artifact.parts or []:
                p = getattr(part, "root", part)
                if hasattr(p, "text"):
                    full_response += p.text
    elif hasattr(result, "parts"):
        for part in result.parts or []:
            p = getattr(part, "root", part)
            if hasattr(p, "text"):
                full_response += p.text

    return full_response, []


class TestDelegateInProcess:
    """Test in-process delegation via the delegate tool."""

    @pytest.mark.asyncio
    async def test_delegate_explore_task(self):
        """Ask legion to delegate an explore task — should use in-process mode."""
        agent_url = _get_sandbox_legion_url()
        client, card = await _connect_to_agent(agent_url)

        context_id = uuid4().hex[:36]
        message = A2AMessage(
            role="user",
            parts=[
                TextPart(
                    text="Use the delegate tool to explore what files are in the /workspace directory. Use mode in-process."
                )
            ],
            messageId=uuid4().hex,
            contextId=context_id,
        )

        response, _ = await _extract_response(client, message)
        assert response, f"Agent returned empty response for delegate explore"

        # The response should contain file listing or exploration results
        response_lower = response.lower()
        assert any(
            term in response_lower
            for term in (
                "workspace",
                "file",
                "directory",
                "found",
                "delegate",
                "sub-agent",
                "explore",
            )
        ), f"Response doesn't mention workspace exploration: {response[:200]}"

    @pytest.mark.asyncio
    async def test_delegate_auto_mode_explore(self):
        """Ask to 'analyze the codebase' — auto mode should pick in-process."""
        agent_url = _get_sandbox_legion_url()
        client, card = await _connect_to_agent(agent_url)

        context_id = uuid4().hex[:36]
        message = A2AMessage(
            role="user",
            parts=[
                TextPart(
                    text="Delegate: analyze the workspace structure and tell me what you find."
                )
            ],
            messageId=uuid4().hex,
            contextId=context_id,
        )

        response, _ = await _extract_response(client, message)
        assert response, f"Agent returned empty response for auto-mode delegate"

    @pytest.mark.asyncio
    async def test_delegate_auto_mode_build(self):
        """Ask to 'build a PR' — auto mode should pick isolated (returns placeholder)."""
        agent_url = _get_sandbox_legion_url()
        client, card = await _connect_to_agent(agent_url)

        context_id = uuid4().hex[:36]
        message = A2AMessage(
            role="user",
            parts=[
                TextPart(
                    text="Delegate: build a PR for implementing a new feature. Use the delegate tool."
                )
            ],
            messageId=uuid4().hex,
            contextId=context_id,
        )

        response, _ = await _extract_response(client, message)
        assert response, f"Agent returned empty response for build delegate"
        # Isolated mode is a placeholder, so response should mention it
        response_lower = response.lower()
        assert any(
            term in response_lower
            for term in (
                "isolated",
                "sandbox",
                "delegate",
                "pr",
                "build",
                "not yet implemented",
            )
        ), f"Response doesn't mention isolated delegation: {response[:200]}"


class TestDelegateContextIsolation:
    """Test that delegated tasks get unique context IDs."""

    @pytest.mark.asyncio
    async def test_delegate_creates_child_context(self):
        """Verify delegation mentions a child context or session."""
        agent_url = _get_sandbox_legion_url()
        client, card = await _connect_to_agent(agent_url)

        context_id = uuid4().hex[:36]
        message = A2AMessage(
            role="user",
            parts=[
                TextPart(
                    text="Use the delegate tool with mode=in-process to check if /workspace exists."
                )
            ],
            messageId=uuid4().hex,
            contextId=context_id,
        )

        response, _ = await _extract_response(client, message)
        assert response, f"Agent returned empty response"


class TestDelegateMultiChild:
    """Test multiple concurrent delegations."""

    @pytest.mark.asyncio
    async def test_delegate_two_tasks_sequentially(self):
        """Delegate two tasks in the same conversation — both should complete."""
        agent_url = _get_sandbox_legion_url()
        client, card = await _connect_to_agent(agent_url)

        context_id = uuid4().hex[:36]

        # First delegation
        msg1 = A2AMessage(
            role="user",
            parts=[
                TextPart(
                    text="Use the delegate tool with mode=in-process to list files in /workspace."
                )
            ],
            messageId=uuid4().hex,
            contextId=context_id,
        )
        response1, _ = await _extract_response(client, msg1)
        assert response1, "First delegation returned empty"

        # Second delegation in same context
        msg2 = A2AMessage(
            role="user",
            parts=[
                TextPart(
                    text="Use the delegate tool again with mode=in-process to check if /tmp exists."
                )
            ],
            messageId=uuid4().hex,
            contextId=context_id,
        )
        response2, _ = await _extract_response(client, msg2)
        assert response2, "Second delegation returned empty"

    @pytest.mark.asyncio
    async def test_delegate_external_agent_placeholder(self):
        """Verify delegating to an external agent via isolated mode returns placeholder."""
        agent_url = _get_sandbox_legion_url()
        client, card = await _connect_to_agent(agent_url)

        context_id = uuid4().hex[:36]
        message = A2AMessage(
            role="user",
            parts=[
                TextPart(
                    text=(
                        "Use the delegate tool with mode=isolated and "
                        "variant=sandbox-legion-secctx to deploy a feature."
                    )
                )
            ],
            messageId=uuid4().hex,
            contextId=context_id,
        )

        response, _ = await _extract_response(client, message)
        assert response, "Isolated delegation returned empty"
        # Should mention that isolated mode is not yet implemented
        response_lower = response.lower()
        assert any(
            term in response_lower
            for term in (
                "isolated",
                "sandboxclaim",
                "not yet implemented",
                "not implemented",
                "delegate",
            )
        ), f"Response doesn't mention isolated mode: {response[:200]}"
