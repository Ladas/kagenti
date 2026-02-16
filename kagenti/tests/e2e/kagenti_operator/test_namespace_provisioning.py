"""
E2E tests for KagentiNamespace auto-provisioning.

Tests the KagentiNamespace CRD controller that provisions new team namespaces
with all required resources: labels, ConfigMaps, SPIRE config, and RBAC.
"""

import json
import subprocess
import time

import pytest


def kubectl(*args, timeout=30):
    """Run a kubectl command and return stdout."""
    result = subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result


def kubectl_json(*args, timeout=30):
    """Run kubectl with JSON output and return parsed dict."""
    result = kubectl(*args, "-o", "json", timeout=timeout)
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def wait_for_phase(name, expected_phase, timeout_seconds=60):
    """Wait for a KagentiNamespace to reach the expected phase."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        result = kubectl(
            "get",
            "kns",
            name,
            "-o",
            "jsonpath={.status.phase}",
        )
        if result.returncode == 0 and result.stdout == expected_phase:
            return True
        time.sleep(2)
    return False


@pytest.fixture(scope="module")
def kns_crd_exists():
    """Check that KagentiNamespace CRD is installed."""
    result = kubectl("get", "crd", "kagentinamespaces.agent.kagenti.dev")
    if result.returncode != 0:
        pytest.skip("KagentiNamespace CRD not installed")
    return True


@pytest.fixture(scope="module")
def test_namespace_name():
    """Name of the test namespace to provision."""
    return "e2e-test-ns"


@pytest.fixture(scope="module")
def kagenti_namespace_cr(kns_crd_exists, test_namespace_name):
    """Create a KagentiNamespace CR for testing and clean up after."""
    cr_yaml = f"""
apiVersion: agent.kagenti.dev/v1alpha1
kind: KagentiNamespace
metadata:
  name: {test_namespace_name}
spec:
  istio:
    ambientEnabled: true
    waypointEnabled: true
  spire:
    enabled: true
"""
    # Apply the CR
    result = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=cr_yaml,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Failed to create KagentiNamespace: {result.stderr}"

    # Wait for provisioning
    time.sleep(5)

    yield test_namespace_name

    # Cleanup: delete the CR
    kubectl("delete", "kns", test_namespace_name, "--ignore-not-found")
    # Give controller time to process finalizer
    time.sleep(5)
    # Namespace is preserved (by design), delete manually
    kubectl("delete", "ns", test_namespace_name, "--ignore-not-found", timeout=60)


class TestKagentiNamespaceProvisioning:
    """Tests for KagentiNamespace auto-provisioning."""

    def test_namespace_created(self, kagenti_namespace_cr):
        """Verify the Kubernetes namespace was created."""
        result = kubectl("get", "ns", kagenti_namespace_cr)
        assert result.returncode == 0, f"Namespace {kagenti_namespace_cr} not created"

    def test_namespace_labels(self, kagenti_namespace_cr):
        """Verify namespace has all required Kagenti and Istio labels."""
        ns = kubectl_json("get", "ns", kagenti_namespace_cr)
        assert ns is not None, "Failed to get namespace"

        labels = ns["metadata"].get("labels", {})

        assert labels.get("kagenti-enabled") == "true", "Missing kagenti-enabled label"
        assert labels.get("istio-discovery") == "enabled", (
            "Missing istio-discovery label"
        )
        assert labels.get("istio.io/dataplane-mode") == "ambient", (
            "Missing ambient label"
        )
        assert labels.get("istio.io/use-waypoint") == "waypoint", (
            "Missing waypoint label"
        )
        assert labels.get("shared-gateway-access") == "true", (
            "Missing shared-gateway label"
        )
        assert labels.get("kagenti.io/managed-by") == "kagenti-operator", (
            "Missing managed-by label"
        )
        assert labels.get("kagenti.io/kagentinamespace") == kagenti_namespace_cr, (
            "Missing CR name label"
        )

    def test_environments_configmap(self, kagenti_namespace_cr):
        """Verify environments ConfigMap was created with expected presets."""
        cm = kubectl_json(
            "get", "configmap", "environments", "-n", kagenti_namespace_cr
        )
        assert cm is not None, "environments ConfigMap not found"

        data = cm.get("data", {})
        # Should have environment presets (copied from existing namespace)
        assert len(data) > 0, "environments ConfigMap is empty"
        # Check for common presets
        assert "ollama" in data or "openai" in data, (
            f"environments ConfigMap missing expected presets, has: {list(data.keys())}"
        )

    def test_spire_configmap(self, kagenti_namespace_cr):
        """Verify SPIRE helper config was created."""
        cm = kubectl_json(
            "get", "configmap", "spiffe-helper-config", "-n", kagenti_namespace_cr
        )
        assert cm is not None, "spiffe-helper-config ConfigMap not found"

        data = cm.get("data", {})
        assert "helper.conf" in data, "Missing helper.conf in SPIRE config"
        assert "spire-agent.sock" in data["helper.conf"], (
            "Missing SPIRE agent socket path"
        )

    def test_rbac_role_created(self, kagenti_namespace_cr):
        """Verify RBAC Role was created for backend access."""
        role = kubectl_json(
            "get", "role", "kagenti-backend-access", "-n", kagenti_namespace_cr
        )
        assert role is not None, "kagenti-backend-access Role not found"

    def test_rbac_rolebinding_created(self, kagenti_namespace_cr):
        """Verify RBAC RoleBinding was created for backend access."""
        rb = kubectl_json(
            "get", "rolebinding", "kagenti-backend-access", "-n", kagenti_namespace_cr
        )
        assert rb is not None, "kagenti-backend-access RoleBinding not found"

        # Verify it references the kagenti-backend service account
        subjects = rb.get("subjects", [])
        assert any(
            s.get("name") == "kagenti-backend"
            and s.get("namespace") == "kagenti-system"
            for s in subjects
        ), "RoleBinding not bound to kagenti-backend SA"

    def test_kns_status_conditions(self, kagenti_namespace_cr):
        """Verify KagentiNamespace status has expected conditions."""
        kns = kubectl_json("get", "kns", kagenti_namespace_cr)
        assert kns is not None, "Failed to get KagentiNamespace"

        conditions = kns.get("status", {}).get("conditions", [])
        condition_types = {c["type"]: c["status"] for c in conditions}

        assert condition_types.get("NamespaceCreated") == "True", (
            "NamespaceCreated condition not True"
        )
        assert condition_types.get("ConfigMapsProvisioned") == "True", (
            "ConfigMapsProvisioned not True"
        )
        assert condition_types.get("SecretsProvisioned") == "True", (
            "SecretsProvisioned not True"
        )

    def test_kns_status_namespace_field(self, kagenti_namespace_cr):
        """Verify KagentiNamespace status.namespace matches the actual namespace."""
        result = kubectl(
            "get",
            "kns",
            kagenti_namespace_cr,
            "-o",
            "jsonpath={.status.namespace}",
        )
        assert result.returncode == 0
        assert result.stdout == kagenti_namespace_cr, (
            f"status.namespace={result.stdout}, expected {kagenti_namespace_cr}"
        )

    def test_namespace_discoverable_by_backend(self, kagenti_namespace_cr):
        """Verify the new namespace appears in kagenti-enabled namespace list."""
        result = kubectl(
            "get",
            "ns",
            "-l",
            "kagenti-enabled=true",
            "-o",
            "jsonpath={.items[*].metadata.name}",
        )
        assert result.returncode == 0
        namespaces = result.stdout.split()
        assert kagenti_namespace_cr in namespaces, (
            f"Namespace {kagenti_namespace_cr} not in kagenti-enabled list: {namespaces}"
        )


class TestKagentiNamespaceWithPrefix:
    """Tests for KagentiNamespace with prefix option."""

    @pytest.fixture(autouse=True)
    def check_crd(self, kns_crd_exists):
        pass

    @pytest.fixture(scope="class")
    def prefixed_kns(self):
        """Create a KagentiNamespace with prefix and clean up after."""
        cr_yaml = """
apiVersion: agent.kagenti.dev/v1alpha1
kind: KagentiNamespace
metadata:
  name: ml-team
spec:
  prefix: "kagenti-"
  istio:
    ambientEnabled: true
  spire:
    enabled: false
"""
        result = subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=cr_yaml,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Failed to create prefixed KagentiNamespace: {result.stderr}"
        )

        time.sleep(5)
        yield "kagenti-ml-team"

        kubectl("delete", "kns", "ml-team", "--ignore-not-found")
        time.sleep(5)
        kubectl("delete", "ns", "kagenti-ml-team", "--ignore-not-found", timeout=60)

    def test_prefixed_namespace_created(self, prefixed_kns):
        """Verify namespace is created with prefix applied."""
        result = kubectl("get", "ns", prefixed_kns)
        assert result.returncode == 0, f"Prefixed namespace {prefixed_kns} not created"

    def test_prefixed_namespace_has_labels(self, prefixed_kns):
        """Verify prefixed namespace has kagenti-enabled label."""
        result = kubectl(
            "get",
            "ns",
            prefixed_kns,
            "-o",
            "jsonpath={.metadata.labels.kagenti-enabled}",
        )
        assert result.stdout == "true"
