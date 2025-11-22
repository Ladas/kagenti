#!/usr/bin/env python3
"""
Agent Conversation E2E Tests for Kagenti Platform

Tests basic agent functionality:
- Agent responds to queries
- LLM integration (Ollama) works
- A2A protocol communication

Usage:
    pytest tests/e2e/test_agent_conversation.py -v
"""

import pytest
import requests
import time


# ============================================================================
# Test: Weather Agent Conversation
# ============================================================================


class TestWeatherAgentConversation:
    """Test weather-service agent conversation with Ollama LLM."""

    @pytest.mark.critical
    def test_agent_health_endpoint(self):
        """Verify agent health endpoint is accessible."""
        service_url = "http://weather-service.team1.svc.cluster.local:8000"
        health_url = f"{service_url}/health"

        try:
            response = requests.get(health_url, timeout=5)
            assert (
                response.status_code == 200
            ), f"Health check failed: {response.status_code}"
        except requests.exceptions.RequestException as e:
            pytest.fail(f"Failed to reach agent health endpoint: {e}")

    @pytest.mark.critical
    def test_agent_simple_query(self):
        """
        Test agent can process a simple query using Ollama.

        This validates:
        - Agent API is accessible
        - Ollama LLM integration works
        - Agent can generate responses
        """
        service_url = "http://weather-service.team1.svc.cluster.local:8000"

        # Simple query that doesn't require actual weather data
        # (weather-tool might not be accessible from test pod)
        query = "Hello, can you help me?"

        # A2A protocol message format (simplified)
        payload = {
            "messages": [{"role": "user", "content": query}],
            "stream": False,
        }

        try:
            # Give agent some time to be fully ready
            time.sleep(2)

            response = requests.post(
                f"{service_url}/chat",
                json=payload,
                timeout=30,  # LLM inference can take time
            )

            assert (
                response.status_code == 200
            ), f"Agent query failed with status {response.status_code}: {response.text}"

            response_data = response.json()
            assert response_data, "Empty response from agent"

            # Check we got some kind of text response
            # Exact format depends on agent implementation
            assert (
                "content" in response_data
                or "message" in response_data
                or "response" in response_data
            ), f"Response missing expected fields: {response_data.keys()}"

            print(f"\n✓ Agent responded to query")
            print(f"  Query: {query}")
            print(f"  Response keys: {response_data.keys()}")

        except requests.exceptions.Timeout:
            pytest.fail("Agent query timed out after 30s - LLM may not be responding")
        except requests.exceptions.RequestException as e:
            pytest.fail(f"Failed to query agent: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error during agent query: {e}")


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
