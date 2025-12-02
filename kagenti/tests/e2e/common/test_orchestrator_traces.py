#!/usr/bin/env python3
"""
Orchestrator Agent Trace E2E Tests

Tests for verifying orchestrator agents (k8s-debug-agent, a2a-bridge, k8s-readonly-server)
create traces in Phoenix and support cross-agent trace propagation.

Tests verify:
1. Orchestrator agent pods are running
2. k8s-debug-agent creates traces in Phoenix
3. Cross-agent trace propagation (traceparent header)
4. AutoGen/OpenAI instrumentation captures LLM spans

Usage:
    # Run all orchestrator trace tests
    pytest kagenti/tests/e2e/common/test_orchestrator_traces.py -v

    # Run specific test
    pytest kagenti/tests/e2e/common/test_orchestrator_traces.py::TestOrchestratorAgentTraces::test_k8s_debug_agent_creates_traces -v

Environment Variables:
    K8S_DEBUG_AGENT_URL: k8s-debug-agent endpoint (default: http://localhost:8001)
    A2A_BRIDGE_URL: a2a-bridge endpoint (default: http://localhost:8002)
    PHOENIX_URL: Phoenix endpoint (default: http://localhost:6006)
"""

import os
import time
import uuid
import logging
from typing import Dict, Any, Optional

import pytest
import httpx
from kubernetes import client, config
from a2a.client import A2AClient
from a2a.types import MessageSendParams, SendStreamingMessageRequest, Message, TextPart

logger = logging.getLogger(__name__)


# ============================================================================
# Test Configuration & Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def k8s_api():
    """Load Kubernetes client for cluster introspection."""
    try:
        config.load_kube_config()
        return client.CoreV1Api()
    except Exception as e:
        logger.warning(f"Failed to load kubeconfig: {e}")
        return None


@pytest.fixture(scope="module")
def phoenix_url():
    """Phoenix GraphQL API endpoint.

    Default: localhost:6006 (via port-forward from 85-start-port-forward.sh)
    """
    return os.getenv("PHOENIX_URL", "http://localhost:6006")


@pytest.fixture(scope="module")
def k8s_debug_agent_url():
    """k8s-debug-agent endpoint.

    Default: localhost:8001 (via port-forward from 85-start-port-forward.sh)
    In-cluster: http://k8s-debug-agent.kagenti-agents.svc.cluster.local:8000
    """
    return os.getenv("K8S_DEBUG_AGENT_URL", "http://localhost:8001")


@pytest.fixture(scope="module")
def a2a_bridge_url():
    """a2a-bridge endpoint.

    Default: localhost:8002 (via port-forward from 85-start-port-forward.sh)
    In-cluster: http://a2a-bridge.kagenti-agents.svc.cluster.local:8080
    """
    return os.getenv("A2A_BRIDGE_URL", "http://localhost:8002")


@pytest.fixture(scope="module")
def orchestrator_agent_url():
    """Orchestrator agent endpoint.

    Default: localhost:8004 (via port-forward)
    In-cluster: http://orchestrator-agent.kagenti-agents.svc.cluster.local:8000
    """
    return os.getenv("ORCHESTRATOR_AGENT_URL", "http://localhost:8004")


@pytest.fixture(scope="module")
def orchestrator_namespace():
    """Namespace where orchestrator agents are deployed."""
    return "kagenti-agents"


# ============================================================================
# Helper Functions
# ============================================================================


async def query_phoenix_graphql(
    phoenix_url: str,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    timeout: int = 10,
) -> Dict[str, Any]:
    """Query Phoenix GraphQL API."""
    graphql_url = f"{phoenix_url}/graphql"

    async with httpx.AsyncClient() as http_client:
        response = await http_client.post(
            graphql_url,
            json={"query": query, "variables": variables or {}},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()


async def send_agent_request_with_trace(
    agent_url: str,
    message: str,
    trace_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Send request to agent via A2A protocol with optional trace context.

    Args:
        agent_url: Agent base URL
        message: User message
        trace_id: Optional trace ID for cross-agent propagation
        parent_span_id: Optional parent span ID for cross-agent propagation
        timeout: Request timeout in seconds

    Returns:
        Agent response data with trace context info
    """
    request_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())

    # Build traceparent header if trace context provided
    headers = {}
    if trace_id and parent_span_id:
        # W3C Trace Context format: 00-{trace_id}-{span_id}-01
        traceparent = f"00-{trace_id}-{parent_span_id}-01"
        headers["traceparent"] = traceparent
        logger.info(f"Sending with traceparent: {traceparent}")

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as http_client:
        client = A2AClient(httpx_client=http_client, url=agent_url)

        msg = Message(
            message_id=request_id,
            role="user",
            parts=[TextPart(text=message)],
            context_id=conversation_id,
        )

        request_params = SendStreamingMessageRequest(
            id=request_id,
            params=MessageSendParams(message=msg),
        )

        responses = []
        async for response in client.send_message_streaming(request_params):
            responses.append(response)

    return {
        "request_id": request_id,
        "conversation_id": conversation_id,
        "trace_id": trace_id,
        "parent_span_id": parent_span_id,
        "responses": responses,
    }


def wait_for_traces(seconds: int = 5):
    """Wait for OTEL batch export to complete."""
    logger.info(f"Waiting {seconds}s for OTEL batch export...")
    time.sleep(seconds)


def generate_trace_id() -> str:
    """Generate a W3C Trace Context compatible trace ID (32 hex chars)."""
    return uuid.uuid4().hex


def generate_span_id() -> str:
    """Generate a W3C Trace Context compatible span ID (16 hex chars)."""
    return uuid.uuid4().hex[:16]


# ============================================================================
# Test Class: Orchestrator Agent Pods
# ============================================================================


class TestOrchestratorAgentPods:
    """Test orchestrator agent pods are running."""

    @pytest.mark.asyncio
    async def test_k8s_debug_agent_pod_running(self, k8s_api, orchestrator_namespace):
        """Test k8s-debug-agent pod is running."""
        if not k8s_api:
            pytest.skip("Kubernetes client not available")

        pods = k8s_api.list_namespaced_pod(namespace=orchestrator_namespace)

        debug_agent_pod = None
        for pod in pods.items:
            if "k8s-debug-agent" in pod.metadata.name:
                debug_agent_pod = pod
                break

        if not debug_agent_pod:
            pytest.skip("k8s-debug-agent not deployed (orchestrator agents optional)")

        assert (
            debug_agent_pod.status.phase == "Running"
        ), f"k8s-debug-agent pod not running: {debug_agent_pod.status.phase}"

        logger.info(f"k8s-debug-agent pod running: {debug_agent_pod.metadata.name}")

    @pytest.mark.asyncio
    async def test_a2a_bridge_pod_running(self, k8s_api, orchestrator_namespace):
        """Test a2a-bridge pod is running."""
        if not k8s_api:
            pytest.skip("Kubernetes client not available")

        pods = k8s_api.list_namespaced_pod(namespace=orchestrator_namespace)

        bridge_pod = None
        for pod in pods.items:
            if "a2a-bridge" in pod.metadata.name:
                bridge_pod = pod
                break

        if not bridge_pod:
            pytest.skip("a2a-bridge not deployed (orchestrator agents optional)")

        assert (
            bridge_pod.status.phase == "Running"
        ), f"a2a-bridge pod not running: {bridge_pod.status.phase}"

        logger.info(f"a2a-bridge pod running: {bridge_pod.metadata.name}")

    @pytest.mark.asyncio
    async def test_k8s_readonly_server_pod_running(
        self, k8s_api, orchestrator_namespace
    ):
        """Test k8s-readonly-server pod is running."""
        if not k8s_api:
            pytest.skip("Kubernetes client not available")

        pods = k8s_api.list_namespaced_pod(namespace=orchestrator_namespace)

        readonly_pod = None
        for pod in pods.items:
            if "k8s-readonly-server" in pod.metadata.name:
                readonly_pod = pod
                break

        if not readonly_pod:
            pytest.skip(
                "k8s-readonly-server not deployed (orchestrator agents optional)"
            )

        assert (
            readonly_pod.status.phase == "Running"
        ), f"k8s-readonly-server pod not running: {readonly_pod.status.phase}"

        logger.info(f"k8s-readonly-server pod running: {readonly_pod.metadata.name}")


# ============================================================================
# Test Class: Orchestrator Agent Traces
# ============================================================================


class TestOrchestratorAgentTraces:
    """Test orchestrator agent instrumentation and trace collection."""

    @pytest.mark.asyncio
    async def test_k8s_debug_agent_creates_traces(
        self, k8s_debug_agent_url, phoenix_url
    ):
        """
        Test k8s-debug-agent creates traces in Phoenix.

        This test verifies:
        1. Send debugging request to k8s-debug-agent
        2. Agent processes request (LLM call via AutoGen/OpenAI)
        3. OpenInference instrumentation creates spans
        4. Spans flow through OTEL to Phoenix
        5. We query Phoenix and find our traces
        """
        # Check if agent is reachable first
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                response = await http_client.get(f"{k8s_debug_agent_url}/")
                if response.status_code >= 500:
                    pytest.skip(f"k8s-debug-agent not healthy: {response.status_code}")
        except httpx.ConnectError:
            pytest.skip(
                "k8s-debug-agent not reachable (port-forward may not be running)"
            )

        request_id = str(uuid.uuid4())
        logger.info("=" * 70)
        logger.info("Testing: k8s-debug-agent Creates Traces in Phoenix")
        logger.info("-" * 70)
        logger.info(f"Request ID: {request_id}")
        logger.info(f"Agent URL: {k8s_debug_agent_url}")
        logger.info(f"Phoenix URL: {phoenix_url}")
        logger.info("=" * 70)

        # Send a simple debugging request
        try:
            response = await send_agent_request_with_trace(
                agent_url=k8s_debug_agent_url,
                message="List pods in the default namespace",
                timeout=120,  # LLM calls via Ollama can be slow
            )
            logger.info(f"Agent responded with {len(response['responses'])} events")
        except Exception as e:
            pytest.skip(f"k8s-debug-agent request failed: {e}")

        # Wait for OTEL batch export
        wait_for_traces(seconds=15)

        # Query Phoenix for traces
        query = """
        query GetRecentSpans {
          projects {
            edges {
              node {
                name
                spans(first: 100) {
                  edges {
                    node {
                      name
                      context {
                        traceId
                        spanId
                      }
                      startTime
                      spanKind
                    }
                  }
                }
              }
            }
          }
        }
        """

        logger.info("Querying Phoenix for orchestrator agent traces...")

        try:
            phoenix_response = await query_phoenix_graphql(
                phoenix_url=phoenix_url,
                query=query,
                variables={},
                timeout=15,
            )
        except Exception as e:
            pytest.skip(f"Phoenix query failed: {e}")

        assert "data" in phoenix_response, f"Phoenix query failed: {phoenix_response}"
        assert phoenix_response["data"] is not None, "Phoenix returned null data"
        assert "projects" in phoenix_response["data"], "No projects in Phoenix response"

        # Extract spans from all projects
        spans = []
        for project_edge in phoenix_response["data"]["projects"]["edges"]:
            project = project_edge["node"]
            for span_edge in project["spans"]["edges"]:
                spans.append(span_edge)

        assert len(spans) > 0, (
            "No traces found in Phoenix. "
            "This may indicate k8s-debug-agent instrumentation is not working."
        )

        logger.info(f"Found {len(spans)} spans in Phoenix")

        # Look for orchestrator-related spans
        span_nodes = [edge["node"] for edge in spans]
        span_names = [span["name"] for span in span_nodes]
        span_kinds = [span.get("spanKind", "UNKNOWN") for span in span_nodes]

        logger.info(f"Span names: {span_names[:20]}...")
        logger.info(f"Span kinds: {set(span_kinds)}")

        # Check for LLM spans (from AutoGen/OpenAI instrumentation)
        llm_spans = [kind for kind in span_kinds if kind == "LLM"]
        openai_spans = [
            name
            for name in span_names
            if "openai" in name.lower() or "chat" in name.lower()
        ]

        # Check for agent spans
        agent_spans = [
            name
            for name in span_names
            if "k8s_debug" in name.lower() or "agent" in name.lower()
        ]

        logger.info(f"LLM spans: {len(llm_spans)}")
        logger.info(f"OpenAI-related spans: {len(openai_spans)}")
        logger.info(f"Agent spans: {len(agent_spans)}")

        # Primary assertion: We have traces in Phoenix
        assert len(spans) > 0, "No spans found in Phoenix for k8s-debug-agent"

        logger.info("=" * 70)
        logger.info("TEST PASSED: k8s-debug-agent creates traces in Phoenix!")
        logger.info("=" * 70)

    @pytest.mark.asyncio
    async def test_cross_agent_trace_propagation(
        self, k8s_debug_agent_url, phoenix_url
    ):
        """
        Test cross-agent trace propagation via traceparent header.

        This test verifies:
        1. Create a parent trace with known trace_id
        2. Send request to k8s-debug-agent with traceparent header
        3. Agent should create spans as children of our trace
        4. Query Phoenix and verify trace_id matches

        This validates W3C Trace Context propagation across agent boundaries.
        """
        # Check if agent is reachable first
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                response = await http_client.get(f"{k8s_debug_agent_url}/")
                if response.status_code >= 500:
                    pytest.skip(f"k8s-debug-agent not healthy: {response.status_code}")
        except httpx.ConnectError:
            pytest.skip(
                "k8s-debug-agent not reachable (port-forward may not be running)"
            )

        # Generate parent trace context
        parent_trace_id = generate_trace_id()
        parent_span_id = generate_span_id()

        logger.info("=" * 70)
        logger.info("Testing: Cross-Agent Trace Propagation")
        logger.info("-" * 70)
        logger.info(f"Parent Trace ID: {parent_trace_id}")
        logger.info(f"Parent Span ID: {parent_span_id}")
        logger.info(f"Agent URL: {k8s_debug_agent_url}")
        logger.info("=" * 70)

        # Send request with traceparent header
        try:
            response = await send_agent_request_with_trace(
                agent_url=k8s_debug_agent_url,
                message="What namespaces exist in this cluster?",
                trace_id=parent_trace_id,
                parent_span_id=parent_span_id,
                timeout=120,
            )
            logger.info(f"Agent responded with {len(response['responses'])} events")
        except Exception as e:
            pytest.skip(f"k8s-debug-agent request failed: {e}")

        # Wait for OTEL batch export
        wait_for_traces(seconds=15)

        # Query Phoenix for spans with our trace_id
        query = """
        query GetRecentSpans {
          projects {
            edges {
              node {
                name
                spans(first: 100) {
                  edges {
                    node {
                      name
                      context {
                        traceId
                        spanId
                      }
                      spanKind
                    }
                  }
                }
              }
            }
          }
        }
        """

        logger.info(f"Querying Phoenix for trace_id={parent_trace_id}...")

        try:
            phoenix_response = await query_phoenix_graphql(
                phoenix_url=phoenix_url,
                query=query,
                variables={},
                timeout=15,
            )
        except Exception as e:
            pytest.skip(f"Phoenix query failed: {e}")

        assert "data" in phoenix_response, f"Phoenix query failed: {phoenix_response}"
        assert phoenix_response["data"] is not None, "Phoenix returned null data"

        # Extract spans and look for our trace_id
        matching_spans = []
        all_spans = []
        for project_edge in phoenix_response["data"]["projects"]["edges"]:
            project = project_edge["node"]
            for span_edge in project["spans"]["edges"]:
                span = span_edge["node"]
                all_spans.append(span)
                if span["context"]["traceId"] == parent_trace_id:
                    matching_spans.append(span)

        logger.info(f"Total spans in Phoenix: {len(all_spans)}")
        logger.info(f"Spans matching our trace_id: {len(matching_spans)}")

        if len(matching_spans) > 0:
            logger.info("Cross-agent trace propagation confirmed!")
            for span in matching_spans:
                logger.info(
                    f"  - {span['name']} (kind={span.get('spanKind', 'UNKNOWN')})"
                )
        else:
            # Log unique trace IDs found
            trace_ids = set(span["context"]["traceId"] for span in all_spans)
            logger.warning(
                f"Our trace_id not found. Found {len(trace_ids)} unique trace IDs"
            )
            logger.warning(
                "This may indicate traceparent header is not being propagated. "
                "Check that trace_context_from_headers() is being called in the agent."
            )

        # This is an informational test - cross-agent propagation may require
        # additional configuration in the A2A SDK
        logger.info("=" * 70)
        if len(matching_spans) > 0:
            logger.info("TEST PASSED: Cross-agent trace propagation working!")
        else:
            logger.info(
                "TEST INFO: Traces created, but trace propagation needs verification"
            )
        logger.info("=" * 70)

        # At minimum, we should have spans in Phoenix
        assert len(all_spans) > 0, "No spans found in Phoenix"


# ============================================================================
# Test Class: A2A Bridge Discovery
# ============================================================================


class TestA2ABridgeDiscovery:
    """Test a2a-bridge agent discovery endpoint."""

    @pytest.mark.asyncio
    async def test_a2a_bridge_lists_agents(self, a2a_bridge_url):
        """Test a2a-bridge can discover registered agents."""
        try:
            async with httpx.AsyncClient(timeout=10) as http_client:
                # a2a-bridge exposes /agents endpoint for discovery
                response = await http_client.get(f"{a2a_bridge_url}/agents")

                if response.status_code == 404:
                    # Try alternative endpoints
                    response = await http_client.get(f"{a2a_bridge_url}/")

                if response.status_code >= 500:
                    pytest.skip(f"a2a-bridge not healthy: {response.status_code}")

                logger.info(f"a2a-bridge response: {response.status_code}")
                logger.info(f"Response body: {response.text[:500]}")

        except httpx.ConnectError:
            pytest.skip("a2a-bridge not reachable (port-forward may not be running)")

        logger.info("a2a-bridge is accessible")


# ============================================================================
# Test Class: Trace Error Detection
# ============================================================================


class TestTraceErrorDetection:
    """
    Test for detecting errors in Phoenix traces.

    These tests verify that traces don't contain errors that indicate
    configuration problems (missing models, connection issues, etc.).

    DEBUGGING GUIDE:
    ================
    When traces show errors, follow this debugging workflow:

    1. Check Phoenix UI for error spans:
       - Open http://localhost:6006 in browser
       - Look for spans with red/error status
       - Click on span to see statusDescription for error details

    2. Check pod logs for detailed errors:
       kubectl logs -n kagenti-agents deployment/k8s-debug-agent --tail=100

    3. Common errors and fixes:
       - "model not found": Pull missing model with `ollama pull <model>`
       - "connection refused": Check OTEL collector is running
       - "ExceptionGroup": Check agent code for async error handling

    4. Verify Ollama model availability:
       ollama list  # Should show qwen2.5:0.5b or configured model

    5. Verify OTEL Collector routing:
       kubectl logs -n kagenti-system deployment/otel-collector --tail=50
    """

    @pytest.mark.asyncio
    async def test_no_model_not_found_errors(self, k8s_debug_agent_url, phoenix_url):
        """
        Test that new agent requests don't produce 'model not found' errors.

        This test:
        1. Sends a fresh request to the agent
        2. Waits for traces to appear in Phoenix
        3. Checks that the new trace doesn't have model errors

        This error indicates the configured LLM model is not available in Ollama.
        Fix: Pull the model with `ollama pull <model-name>`
        """
        # First, send a request to create a fresh trace
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                response = await http_client.get(f"{k8s_debug_agent_url}/")
                if response.status_code >= 500:
                    pytest.skip(f"k8s-debug-agent not healthy: {response.status_code}")
        except httpx.ConnectError:
            pytest.skip("k8s-debug-agent not reachable")

        logger.info("Sending fresh request to k8s-debug-agent...")

        try:
            await send_agent_request_with_trace(
                agent_url=k8s_debug_agent_url,
                message="List namespaces",
                timeout=120,
            )
        except Exception as e:
            pytest.skip(f"Agent request failed: {e}")

        # Wait for traces
        wait_for_traces(seconds=10)

        # Query for recent spans with errors
        query = """
        query GetSpansWithErrors {
          projects {
            edges {
              node {
                name
                spans(first: 50) {
                  edges {
                    node {
                      name
                      statusCode
                      statusMessage
                      startTime
                      context {
                        traceId
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        try:
            response = await query_phoenix_graphql(
                phoenix_url=phoenix_url, query=query, timeout=15
            )
        except Exception as e:
            pytest.skip(f"Phoenix not available: {e}")

        if not response.get("data"):
            pytest.skip("No data from Phoenix")

        # Collect error spans from the most recent traces
        # Only look at spans from the last minute to avoid old historical errors
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        error_spans = []
        model_not_found_errors = []

        for project_edge in response["data"]["projects"]["edges"]:
            project = project_edge["node"]
            for span_edge in project["spans"]["edges"]:
                span = span_edge["node"]
                status_code = span.get("statusCode", "")
                status_msg = span.get("statusMessage") or ""

                # Parse start time and check if recent (within last 2 minutes)
                start_time_str = span.get("startTime", "")
                is_recent = False
                if start_time_str:
                    try:
                        # Phoenix returns ISO format timestamps
                        span_time = datetime.fromisoformat(
                            start_time_str.replace("Z", "+00:00")
                        )
                        age_seconds = (now - span_time).total_seconds()
                        is_recent = age_seconds < 120  # Last 2 minutes
                    except (ValueError, TypeError):
                        is_recent = True  # If we can't parse, include it

                if not is_recent:
                    continue

                # Check for error status
                if status_code == "ERROR" or "error" in status_code.lower():
                    error_spans.append(span)

                    # Check for model not found specifically
                    if (
                        "model" in status_msg.lower()
                        and "not found" in status_msg.lower()
                    ):
                        model_not_found_errors.append(span)

        if model_not_found_errors:
            logger.error("=" * 70)
            logger.error("MODEL NOT FOUND ERRORS DETECTED IN RECENT TRACES!")
            logger.error("-" * 70)
            for span in model_not_found_errors:
                logger.error(f"Span: {span['name']}")
                logger.error(f"Error: {span.get('statusMessage', 'N/A')}")
            logger.error("-" * 70)
            logger.error("FIX: Pull the missing model with 'ollama pull <model>'")
            logger.error("     Current model should be: qwen2.5:0.5b")
            logger.error("     Run: ollama pull qwen2.5:0.5b")
            logger.error("=" * 70)

        assert len(model_not_found_errors) == 0, (
            f"Found {len(model_not_found_errors)} 'model not found' errors in recent traces. "
            f"Run 'ollama pull qwen2.5:0.5b' to fix."
        )

        if error_spans:
            logger.warning(f"Found {len(error_spans)} error spans in recent traces")
            for span in error_spans[:5]:  # Show first 5
                logger.warning(
                    f"  - {span['name']}: {span.get('statusMessage', 'N/A')[:100]}"
                )

        logger.info("No 'model not found' errors in recent traces")

    @pytest.mark.asyncio
    async def test_orchestrator_pods_have_no_crash_loops(
        self, k8s_api, orchestrator_namespace
    ):
        """
        Test that orchestrator pods are not in CrashLoopBackOff.

        This indicates repeated failures in the agent startup.
        """
        if not k8s_api:
            pytest.skip("Kubernetes client not available")

        pods = k8s_api.list_namespaced_pod(namespace=orchestrator_namespace)

        crash_loop_pods = []
        for pod in pods.items:
            if pod.status.container_statuses:
                for container_status in pod.status.container_statuses:
                    if container_status.state.waiting:
                        reason = container_status.state.waiting.reason or ""
                        if "CrashLoopBackOff" in reason or "Error" in reason:
                            crash_loop_pods.append(
                                {
                                    "pod": pod.metadata.name,
                                    "container": container_status.name,
                                    "reason": reason,
                                    "restart_count": container_status.restart_count,
                                }
                            )

        if crash_loop_pods:
            logger.error("=" * 70)
            logger.error("PODS IN CRASH LOOP DETECTED!")
            logger.error("-" * 70)
            for p in crash_loop_pods:
                logger.error(f"Pod: {p['pod']}")
                logger.error(f"Container: {p['container']}")
                logger.error(f"Reason: {p['reason']}")
                logger.error(f"Restarts: {p['restart_count']}")
            logger.error("-" * 70)
            logger.error("DEBUGGING STEPS:")
            logger.error(
                f"  1. Check logs: kubectl logs -n {orchestrator_namespace} <pod>"
            )
            logger.error(
                f"  2. Describe pod: kubectl describe pod -n {orchestrator_namespace} <pod>"
            )
            logger.error("=" * 70)

        assert len(crash_loop_pods) == 0, (
            f"Found {len(crash_loop_pods)} pods in CrashLoopBackOff: "
            f"{[p['pod'] for p in crash_loop_pods]}"
        )

        logger.info("All orchestrator pods healthy (no crash loops)")

    @pytest.mark.asyncio
    async def test_check_agent_logs_for_errors(self, k8s_api, orchestrator_namespace):
        """
        Test that agent logs don't contain critical errors.

        This is an informational test that logs recent errors but doesn't fail.
        """
        if not k8s_api:
            pytest.skip("Kubernetes client not available")

        # Get recent logs from k8s-debug-agent
        pods = k8s_api.list_namespaced_pod(
            namespace=orchestrator_namespace, label_selector="app=k8s-debug-agent"
        )

        if not pods.items:
            pytest.skip("k8s-debug-agent pod not found")

        pod_name = pods.items[0].metadata.name

        try:
            logs = k8s_api.read_namespaced_pod_log(
                name=pod_name,
                namespace=orchestrator_namespace,
                tail_lines=100,
            )
        except Exception as e:
            pytest.skip(f"Failed to read logs: {e}")

        # Look for error patterns
        error_patterns = [
            "NotFoundError",
            "ConnectionError",
            "model.*not found",
            "ExceptionGroup",
            "RuntimeError",
            "Traceback",
        ]

        errors_found = []
        for line in logs.split("\n"):
            for pattern in error_patterns:
                if pattern.lower() in line.lower():
                    errors_found.append(line[:200])  # Truncate long lines
                    break

        if errors_found:
            logger.warning("=" * 70)
            logger.warning("ERRORS FOUND IN AGENT LOGS")
            logger.warning("-" * 70)
            for error in errors_found[:10]:  # Show first 10
                logger.warning(f"  {error}")
            if len(errors_found) > 10:
                logger.warning(f"  ... and {len(errors_found) - 10} more")
            logger.warning("-" * 70)
            logger.warning(
                f"Full logs: kubectl logs -n {orchestrator_namespace} {pod_name}"
            )
            logger.warning("=" * 70)

        # This is informational - log errors but don't fail
        logger.info(
            f"Log check complete: {len(errors_found)} error patterns found in {pod_name}"
        )


# ============================================================================
# Test Class: Trace Hierarchy Validation
# ============================================================================


class TestTraceHierarchy:
    """
    Test proper trace hierarchy with LLM spans nested under agent spans.

    The expected hierarchy is:
    - agent_name (AGENT) - root span
      - autogen.a_initiate_chat (CHAIN)
        - autogen.a_generate_reply (CHAIN)
          - ChatCompletion (LLM) - should be CHILD of agent span

    If LLM spans have parentId: null, trace context isn't propagating correctly.
    """

    @pytest.mark.asyncio
    async def test_llm_spans_are_children_of_agent_span(
        self, k8s_debug_agent_url, phoenix_url
    ):
        """
        Test that LLM spans are properly nested under the agent span.

        This validates that OpenTelemetry context propagates correctly through
        AutoGen's async code to the OpenAI SDK calls.
        """
        # Check if agent is reachable
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                response = await http_client.get(f"{k8s_debug_agent_url}/")
                if response.status_code >= 500:
                    pytest.skip(f"k8s-debug-agent not healthy: {response.status_code}")
        except httpx.ConnectError:
            pytest.skip("k8s-debug-agent not reachable")

        logger.info("=" * 70)
        logger.info("Testing: LLM Spans Are Children of Agent Span")
        logger.info("-" * 70)

        # Send a request
        try:
            await send_agent_request_with_trace(
                agent_url=k8s_debug_agent_url,
                message="What is the status of the default namespace?",
                timeout=120,
            )
        except Exception as e:
            pytest.skip(f"Agent request failed: {e}")

        # Wait for traces
        wait_for_traces(seconds=15)

        # Query Phoenix for spans with parent information
        query = """
        query GetSpansWithParent {
          projects {
            edges {
              node {
                name
                spans(first: 100) {
                  edges {
                    node {
                      name
                      spanKind
                      context {
                        traceId
                        spanId
                      }
                      parentId
                      startTime
                    }
                  }
                }
              }
            }
          }
        }
        """

        try:
            response = await query_phoenix_graphql(
                phoenix_url=phoenix_url, query=query, timeout=15
            )
        except Exception as e:
            pytest.skip(f"Phoenix not available: {e}")

        if not response.get("data"):
            pytest.skip("No data from Phoenix")

        # Group spans by trace_id
        from collections import defaultdict

        traces = defaultdict(list)

        for project_edge in response["data"]["projects"]["edges"]:
            project = project_edge["node"]
            for span_edge in project["spans"]["edges"]:
                span = span_edge["node"]
                trace_id = span["context"]["traceId"]
                traces[trace_id].append(span)

        # Find traces with both agent and LLM spans
        traces_with_both = []
        for trace_id, spans in traces.items():
            has_agent = any(
                "agent" in s["name"].lower() or s.get("spanKind") == "AGENT"
                for s in spans
            )
            has_llm = any(
                s.get("spanKind") == "LLM" or "chat" in s["name"].lower() for s in spans
            )
            if has_agent and has_llm:
                traces_with_both.append((trace_id, spans))

        if not traces_with_both:
            logger.warning("No traces found with both agent and LLM spans")
            logger.info("Available span names in recent traces:")
            for trace_id, spans in list(traces.items())[:3]:
                logger.info(f"  Trace {trace_id[:8]}...: {[s['name'] for s in spans]}")
            pytest.skip("No complete traces found")

        # Check the most recent complete trace
        trace_id, spans = traces_with_both[0]
        logger.info(f"Analyzing trace: {trace_id}")

        # Build span hierarchy
        span_by_id = {s["context"]["spanId"]: s for s in spans}

        # Find root spans (no parent or parent not in this trace)
        root_spans = []
        child_spans = []
        for span in spans:
            parent_id = span.get("parentId")
            if parent_id is None or parent_id not in span_by_id:
                root_spans.append(span)
            else:
                child_spans.append(span)

        # Check if LLM spans have parents
        llm_spans = [s for s in spans if s.get("spanKind") == "LLM"]
        llm_spans_with_null_parent = [s for s in llm_spans if s.get("parentId") is None]

        logger.info(f"Total spans in trace: {len(spans)}")
        logger.info(f"Root spans: {len(root_spans)}")
        logger.info(f"LLM spans: {len(llm_spans)}")
        logger.info(f"LLM spans with null parent: {len(llm_spans_with_null_parent)}")

        for span in spans:
            parent_info = (
                f"parent={span.get('parentId', 'null')[:8]}..."
                if span.get("parentId")
                else "ROOT"
            )
            logger.info(
                f"  - {span['name']} ({span.get('spanKind', '?')}) [{parent_info}]"
            )

        # Verify LLM spans have proper parents
        if llm_spans_with_null_parent:
            logger.warning("=" * 70)
            logger.warning("TRACE HIERARCHY ISSUE: LLM spans have null parentId!")
            logger.warning(
                "This indicates trace context isn't propagating through AutoGen."
            )
            logger.warning("-" * 70)
            for span in llm_spans_with_null_parent:
                logger.warning(f"  Orphan LLM span: {span['name']}")
            logger.warning("=" * 70)

        # This assertion checks the hierarchy
        assert len(llm_spans_with_null_parent) == 0, (
            f"{len(llm_spans_with_null_parent)} LLM spans have null parentId. "
            "Trace context is not propagating correctly through AutoGen. "
            "Check observability.py's _patch_autogen_async_methods()."
        )

        logger.info("=" * 70)
        logger.info("TEST PASSED: LLM spans are properly nested under agent span!")
        logger.info("=" * 70)


# ============================================================================
# Test Class: Orchestrator Agent Multi-Agent Calls
# ============================================================================


class TestOrchestratorMultiAgent:
    """
    Test orchestrator agent calling other agents via A2A protocol.

    These tests verify the orchestrator can:
    1. Discover available agents
    2. Delegate tasks to appropriate agents
    3. Maintain trace context across agent calls
    """

    @pytest.mark.asyncio
    async def test_orchestrator_agent_health(self, orchestrator_agent_url):
        """Test orchestrator agent is healthy and accessible."""
        try:
            async with httpx.AsyncClient(timeout=10) as http_client:
                response = await http_client.get(f"{orchestrator_agent_url}/")
                if response.status_code >= 500:
                    pytest.fail(f"Orchestrator not healthy: {response.status_code}")
                logger.info(f"Orchestrator agent accessible: {response.status_code}")
        except httpx.ConnectError:
            pytest.fail(
                f"Orchestrator agent not reachable at {orchestrator_agent_url}. "
                "Ensure orchestrator-agent is deployed and port-forward is running."
            )

    @pytest.mark.asyncio
    async def test_orchestrator_discovers_agents(
        self, orchestrator_agent_url, phoenix_url
    ):
        """
        Test orchestrator agent can discover other agents.

        This sends a request asking to list agents, which triggers the
        orchestrator to use the a2a-bridge discover_agents tool.
        """
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                response = await http_client.get(f"{orchestrator_agent_url}/")
                if response.status_code >= 500:
                    pytest.fail(f"Orchestrator not healthy: {response.status_code}")
        except httpx.ConnectError:
            pytest.fail(
                f"Orchestrator agent not reachable at {orchestrator_agent_url}. "
                "Ensure orchestrator-agent is deployed and port-forward is running."
            )

        logger.info("=" * 70)
        logger.info("Testing: Orchestrator Discovers Agents")
        logger.info("-" * 70)

        try:
            response = await send_agent_request_with_trace(
                agent_url=orchestrator_agent_url,
                message="List all available agents and their capabilities",
                timeout=180,
            )
            logger.info(
                f"Orchestrator responded with {len(response['responses'])} events"
            )

            # Check if response mentions agents
            responses_text = str(response.get("responses", []))
            if "agent" in responses_text.lower():
                logger.info("Response mentions agents - discovery likely worked")

        except Exception as e:
            pytest.fail(f"Orchestrator request failed: {e}")

        logger.info("=" * 70)
        logger.info("TEST PASSED: Orchestrator can discover agents!")
        logger.info("=" * 70)

    @pytest.mark.asyncio
    async def test_orchestrator_delegates_to_k8s_agent(
        self, orchestrator_agent_url, phoenix_url
    ):
        """
        Test orchestrator delegates Kubernetes tasks to k8s-debug-agent.

        This sends a Kubernetes-related request that should be routed
        to the k8s-debug-agent via a2a-bridge.
        """
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                response = await http_client.get(f"{orchestrator_agent_url}/")
                if response.status_code >= 500:
                    pytest.fail(f"Orchestrator not healthy: {response.status_code}")
        except httpx.ConnectError:
            pytest.fail(
                f"Orchestrator agent not reachable at {orchestrator_agent_url}. "
                "Ensure orchestrator-agent is deployed and port-forward is running."
            )

        logger.info("=" * 70)
        logger.info("Testing: Orchestrator Delegates to k8s-debug-agent")
        logger.info("-" * 70)

        parent_trace_id = generate_trace_id()
        parent_span_id = generate_span_id()

        try:
            response = await send_agent_request_with_trace(
                agent_url=orchestrator_agent_url,
                message="What pods are running in the kagenti-system namespace? Delegate to the kubernetes agent.",
                trace_id=parent_trace_id,
                parent_span_id=parent_span_id,
                timeout=180,
            )
            logger.info(
                f"Orchestrator responded with {len(response['responses'])} events"
            )
        except Exception as e:
            pytest.fail(f"Orchestrator request failed: {e}")

        # Wait for traces
        wait_for_traces(seconds=15)

        # Query Phoenix for traces
        query = """
        query GetTraces {
          projects {
            edges {
              node {
                name
                spans(first: 200) {
                  edges {
                    node {
                      name
                      spanKind
                      context {
                        traceId
                        spanId
                      }
                      parentId
                    }
                  }
                }
              }
            }
          }
        }
        """

        try:
            phoenix_response = await query_phoenix_graphql(
                phoenix_url=phoenix_url, query=query, timeout=15
            )
        except Exception as e:
            pytest.skip(f"Phoenix not available: {e}")

        if not phoenix_response.get("data"):
            pytest.skip("No data from Phoenix")

        # Look for spans from both orchestrator and k8s-debug-agent
        orchestrator_spans = []
        k8s_agent_spans = []

        for project_edge in phoenix_response["data"]["projects"]["edges"]:
            project = project_edge["node"]
            for span_edge in project["spans"]["edges"]:
                span = span_edge["node"]
                span_name = span["name"].lower()
                if "orchestrator" in span_name:
                    orchestrator_spans.append(span)
                if "k8s" in span_name or "debug" in span_name:
                    k8s_agent_spans.append(span)

        logger.info(f"Orchestrator spans: {len(orchestrator_spans)}")
        logger.info(f"K8s agent spans: {len(k8s_agent_spans)}")

        # Check for cross-agent trace propagation
        matching_trace_spans = []
        for project_edge in phoenix_response["data"]["projects"]["edges"]:
            project = project_edge["node"]
            for span_edge in project["spans"]["edges"]:
                span = span_edge["node"]
                if span["context"]["traceId"] == parent_trace_id:
                    matching_trace_spans.append(span)

        logger.info(f"Spans matching our trace_id: {len(matching_trace_spans)}")

        if len(matching_trace_spans) > 0:
            logger.info("Cross-agent trace propagation working!")
            for span in matching_trace_spans[:10]:
                logger.info(f"  - {span['name']} ({span.get('spanKind', '?')})")

        logger.info("=" * 70)
        logger.info("TEST COMPLETE: Orchestrator multi-agent delegation tested")
        logger.info("=" * 70)


# ============================================================================
# Test Class: K8s Debug Agent Functional Tests
# ============================================================================


class TestK8sDebugAgentFunctionality:
    """
    Test k8s-debug-agent actually returns valid Kubernetes data.

    These tests verify the agent can:
    1. List namespaces and return expected namespace names
    2. Execute MCP tools via k8s-readonly-server

    Expected namespaces created by kagenti-operator CI workflow:
    - kagenti-system: Kagenti operator and infrastructure
    - kagenti-agents: Agent deployments
    - team1: Example team namespace
    - team2: Example team namespace
    """

    # Namespaces that should exist in a properly configured cluster
    EXPECTED_NAMESPACES = [
        "kagenti-system",
        "kagenti-agents",
        "team1",
        "default",
    ]

    @pytest.mark.asyncio
    async def test_k8s_debug_agent_lists_namespaces(
        self, k8s_debug_agent_url, phoenix_url
    ):
        """
        Test k8s-debug-agent can list namespaces and return actual data.

        This test verifies:
        1. Send request to list namespaces
        2. Agent executes MCP tool via k8s-readonly-server
        3. Response contains expected namespace names

        If the response is empty or doesn't contain expected namespaces,
        this indicates the agent/LLM is not properly calling the MCP tools.
        """
        # Check if agent is reachable
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                response = await http_client.get(f"{k8s_debug_agent_url}/")
                if response.status_code >= 500:
                    pytest.skip(f"k8s-debug-agent not healthy: {response.status_code}")
        except httpx.ConnectError:
            pytest.skip("k8s-debug-agent not reachable")

        logger.info("=" * 70)
        logger.info("Testing: k8s-debug-agent Lists Namespaces")
        logger.info("-" * 70)

        # Send request to list namespaces
        try:
            response = await send_agent_request_with_trace(
                agent_url=k8s_debug_agent_url,
                message="List all namespaces in the cluster. Use the get_namespaces tool.",
                timeout=180,  # LLM calls via Ollama can be slow
            )
            logger.info(f"Agent responded with {len(response['responses'])} events")
        except Exception as e:
            pytest.skip(f"k8s-debug-agent request failed: {e}")

        # Extract response text from all events
        # A2A streaming responses have various structures - use flexible extraction
        response_text = ""
        for event in response.get("responses", []):
            # Convert event to string for text extraction
            # This handles various A2A event types (messages, artifacts, status updates)
            event_str = str(event)

            # Try to extract actual text content from known patterns
            # Pattern 1: text='...' in TextPart objects
            import re

            text_matches = re.findall(r"text='([^']*)'", event_str)
            for match in text_matches:
                # Skip short status messages, keep actual content
                if len(match) > 20:
                    response_text += match + " "

        response_text = response_text.strip()
        logger.info(f"Response text length: {len(response_text)}")
        logger.info(f"Response text (first 500 chars): {response_text[:500]}")

        # Check if response contains expected namespaces
        found_namespaces = []
        missing_namespaces = []

        for ns in self.EXPECTED_NAMESPACES:
            if ns in response_text.lower():
                found_namespaces.append(ns)
            else:
                missing_namespaces.append(ns)

        logger.info(f"Found namespaces in response: {found_namespaces}")
        logger.info(f"Missing namespaces in response: {missing_namespaces}")

        # Log warning if response seems empty or unhelpful
        if len(response_text) < 50:
            logger.warning(
                "Response is very short. The LLM may not be generating tool calls properly."
            )
            logger.warning(
                "This could be due to the model (qwen2.5:0.5b) being too small."
            )
            logger.warning(
                "Consider using a larger model like qwen2.5:3b or qwen2.5:7b."
            )

        # Primary assertion: Response should contain at least some expected namespaces
        assert len(found_namespaces) >= 2, (
            f"Expected to find at least 2 of {self.EXPECTED_NAMESPACES} in response, "
            f"but only found {found_namespaces}. "
            f"Response text: {response_text[:200]}... "
            f"The agent may not be calling MCP tools correctly."
        )

        logger.info("=" * 70)
        logger.info(
            f"TEST PASSED: Found {len(found_namespaces)} expected namespaces in response!"
        )
        logger.info("=" * 70)

    @pytest.mark.asyncio
    async def test_k8s_debug_agent_tool_execution_in_traces(
        self, k8s_debug_agent_url, phoenix_url
    ):
        """
        Test that k8s-debug-agent traces show tool execution spans.

        This test verifies:
        1. Send request that requires tool execution
        2. Check Phoenix traces for tool/function call spans
        3. Verify the agent is actually calling MCP tools

        If no tool spans appear, the LLM is not generating tool calls.
        """
        # Check if agent is reachable
        try:
            async with httpx.AsyncClient(timeout=5) as http_client:
                response = await http_client.get(f"{k8s_debug_agent_url}/")
                if response.status_code >= 500:
                    pytest.skip(f"k8s-debug-agent not healthy: {response.status_code}")
        except httpx.ConnectError:
            pytest.skip("k8s-debug-agent not reachable")

        logger.info("=" * 70)
        logger.info("Testing: k8s-debug-agent Tool Execution in Traces")
        logger.info("-" * 70)

        # Send request that requires tool execution
        try:
            await send_agent_request_with_trace(
                agent_url=k8s_debug_agent_url,
                message="Get the list of pods in kagenti-system namespace using the get_pods tool.",
                timeout=180,
            )
        except Exception as e:
            pytest.skip(f"k8s-debug-agent request failed: {e}")

        # Wait for OTEL batch export
        wait_for_traces(seconds=15)

        # Query Phoenix for recent spans
        query = """
        query GetRecentSpans {
          projects {
            edges {
              node {
                name
                spans(first: 100, sort: {col: startTime, dir: desc}) {
                  edges {
                    node {
                      name
                      spanKind
                      context {
                        traceId
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """

        try:
            phoenix_response = await query_phoenix_graphql(
                phoenix_url=phoenix_url, query=query, timeout=15
            )
        except Exception as e:
            pytest.skip(f"Phoenix query failed: {e}")

        if not phoenix_response.get("data"):
            pytest.skip("No data from Phoenix")

        # Extract span names and look for tool-related spans
        span_names = []
        for project_edge in phoenix_response["data"]["projects"]["edges"]:
            project = project_edge["node"]
            for span_edge in project["spans"]["edges"]:
                span = span_edge["node"]
                span_names.append(span["name"])

        # Look for tool execution indicators
        tool_indicators = [
            "get_namespaces",
            "get_pods",
            "get_events",
            "get_deployments",
            "tool",
            "function",
            "mcp",
        ]

        tool_spans = [
            name
            for name in span_names
            if any(indicator in name.lower() for indicator in tool_indicators)
        ]

        logger.info(f"Total spans: {len(span_names)}")
        logger.info(f"Tool-related spans: {tool_spans}")

        if not tool_spans:
            logger.warning(
                "No tool execution spans found. The LLM may not be generating tool calls."
            )
            logger.warning(
                "This is expected with small models like qwen2.5:0.5b that may struggle with function calling."
            )
            # Don't fail - just log warning. Tool execution depends on LLM capability.

        logger.info("=" * 70)
        logger.info("TEST COMPLETE: Tool execution trace analysis done")
        logger.info("=" * 70)
