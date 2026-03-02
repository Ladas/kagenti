"""Tests for nono_launcher.py — Landlock filesystem sandbox."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from nono_launcher import apply_sandbox, main


class TestApplySandbox:
    """Test Landlock sandbox application."""

    def test_returns_false_without_nono_py(self):
        """When nono_py is not installed, return False and warn."""
        with patch.dict(sys.modules, {"nono_py": None}):
            # Force re-import failure
            import importlib
            import nono_launcher

            importlib.reload(nono_launcher)
            result = nono_launcher.apply_sandbox()
            assert result is False

    def test_returns_true_with_nono_py(self):
        """When nono_py is available, apply sandbox and return True."""
        mock_nono = MagicMock()
        mock_caps = MagicMock()
        mock_nono.CapabilitySet.return_value = mock_caps
        mock_nono.AccessMode.READ = "READ"
        mock_nono.AccessMode.READ_WRITE = "READ_WRITE"

        with patch.dict(sys.modules, {"nono_py": mock_nono}):
            import importlib
            import nono_launcher

            importlib.reload(nono_launcher)
            result = nono_launcher.apply_sandbox()
            assert result is True
            mock_nono.apply.assert_called_once_with(mock_caps)

    def test_workspace_env_override(self):
        """WORKSPACE_DIR env var overrides default /workspace."""
        mock_nono = MagicMock()
        mock_caps = MagicMock()
        mock_nono.CapabilitySet.return_value = mock_caps
        mock_nono.AccessMode.READ = "READ"
        mock_nono.AccessMode.READ_WRITE = "READ_WRITE"

        with patch.dict(sys.modules, {"nono_py": mock_nono}):
            with patch.dict(os.environ, {"WORKSPACE_DIR": "/custom/ws"}):
                with patch("os.path.exists", return_value=True):
                    import importlib
                    import nono_launcher

                    importlib.reload(nono_launcher)
                    nono_launcher.apply_sandbox()
                    # Verify /custom/ws was added as READ_WRITE
                    calls = mock_caps.allow_path.call_args_list
                    rw_paths = [c[0][0] for c in calls if c[0][1] == "READ_WRITE"]
                    assert "/custom/ws" in rw_paths


class TestMain:
    """Test main() entry point."""

    def test_main_with_command(self):
        """With args, execvp is called with those args."""
        with patch("nono_launcher.apply_sandbox", return_value=True):
            with patch("os.execvp") as mock_exec:
                with patch.object(
                    sys, "argv", ["nono_launcher.py", "python3", "agent_server.py"]
                ):
                    main()
                    mock_exec.assert_called_once_with(
                        "python3", ["python3", "agent_server.py"]
                    )

    def test_main_without_command(self):
        """Without args, execvp uses default sleep command."""
        with patch("nono_launcher.apply_sandbox", return_value=False):
            with patch("os.execvp") as mock_exec:
                with patch.object(sys, "argv", ["nono_launcher.py"]):
                    main()
                    mock_exec.assert_called_once()
                    assert mock_exec.call_args[0][0] == "/bin/sh"
