"""Multi-mode delegation tool for the legion agent (Session E).

Extends the existing C20 sub-agent spawning with 4 configurable delegation modes:

1. **in-process**: LangGraph subgraph in the same Python process.
   Shares memory + filesystem. Best for exploration and file-level work.

2. **shared-pvc**: Separate pod with parent's PVC mounted (RWX).
   Child sees parent's workspace. Best for running tests on parent's changes.

3. **isolated**: Separate pod with own PVC/emptyDir via SandboxClaim.
   Full isolation. Best for building separate PRs and independent work.

4. **sidecar**: New container in the legion pod. Shares volume mount.
   A2A over localhost. Low-latency tool execution.

The LLM picks the best mode per task (auto-selection), or the user can specify.
All modes can be enabled simultaneously on the same root session agent.

Configuration via environment variables:
    DELEGATION_MODES=in-process,shared-pvc,isolated,sidecar
    DEFAULT_DELEGATION_MODE=in-process
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger(__name__)

# Maximum iterations for in-process sub-agents
_MAX_SUB_AGENT_ITERATIONS = 15

# Delegation mode configuration
_DELEGATION_MODES = os.environ.get(
    "DELEGATION_MODES", "in-process,shared-pvc,isolated,sidecar"
).split(",")
_DEFAULT_MODE = os.environ.get("DEFAULT_DELEGATION_MODE", "in-process")


# ---------------------------------------------------------------------------
# In-process delegation (mode 1)
# ---------------------------------------------------------------------------


def _create_in_process_subgraph(
    workspace: str,
    llm: Any,
    tools_list: list[Any] | None = None,
) -> Any:
    """Create a full-capability subgraph for in-process delegation.

    Unlike the explore subgraph (read-only), this subgraph has access to
    the parent's full tool set. It shares the parent's filesystem and memory.
    """
    if tools_list is None:
        # Default to read-only tools if no tools provided
        from .subagents import _make_explore_tools  # noqa: delay import

        tools_list = _make_explore_tools(workspace)

    llm_with_tools = llm.bind_tools(tools_list)

    async def assistant(state: MessagesState) -> dict[str, Any]:
        system = SystemMessage(
            content=(
                "You are a sub-agent working on a delegated task. Complete the task "
                "efficiently using the available tools. Return a clear summary of "
                "what you did and the results."
            )
        )
        messages = [system] + state["messages"]
        response = await llm_with_tools.ainvoke(messages)
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("assistant", assistant)
    graph.add_node("tools", ToolNode(tools_list))
    graph.set_entry_point("assistant")
    graph.add_conditional_edges("assistant", tools_condition)
    graph.add_edge("tools", "assistant")

    return graph.compile()


async def _run_in_process(
    task: str,
    workspace: str,
    llm: Any,
    child_context_id: str,
    tools_list: list[Any] | None = None,
    timeout: int = 120,
) -> str:
    """Execute a task as an in-process LangGraph subgraph."""
    sub_graph = _create_in_process_subgraph(workspace, llm, tools_list)
    try:
        result = await asyncio.wait_for(
            sub_graph.ainvoke(
                {"messages": [HumanMessage(content=task)]},
                config={
                    "recursion_limit": _MAX_SUB_AGENT_ITERATIONS,
                    "configurable": {"thread_id": child_context_id},
                },
            ),
            timeout=timeout,
        )
        messages = result.get("messages", [])
        if messages:
            last = messages[-1]
            return last.content if hasattr(last, "content") else str(last)
        return "No results from in-process sub-agent."
    except asyncio.TimeoutError:
        return f"In-process sub-agent timed out after {timeout} seconds."
    except Exception as exc:
        logger.exception("In-process delegation failed for %s", child_context_id)
        return f"In-process sub-agent error: {exc}"


# ---------------------------------------------------------------------------
# Shared-PVC delegation (mode 2) — placeholder
# ---------------------------------------------------------------------------


async def _run_shared_pvc(
    task: str,
    child_context_id: str,
    namespace: str = "team1",
    variant: str = "sandbox-legion",
    timeout_minutes: int = 30,
) -> str:
    """Spawn a pod that mounts the parent's PVC.

    TODO: Implement pod creation with parent PVC subPath mount.
    """
    logger.info(
        "shared-pvc delegation: child=%s task=%s variant=%s",
        child_context_id,
        task,
        variant,
    )
    return (
        f"Shared-PVC delegation requested for '{task}' "
        f"(child={child_context_id}, namespace={namespace}, variant={variant}). "
        "Requires RWX StorageClass and cluster access. Not yet implemented."
    )


# ---------------------------------------------------------------------------
# Isolated delegation (mode 3) — placeholder
# ---------------------------------------------------------------------------


async def _run_isolated(
    task: str,
    child_context_id: str,
    namespace: str = "team1",
    variant: str = "sandbox-legion",
    timeout_minutes: int = 30,
) -> str:
    """Spawn an isolated pod via SandboxClaim CRD.

    TODO: Implement SandboxClaim creation and A2A polling.
    """
    logger.info(
        "isolated delegation: child=%s task=%s variant=%s",
        child_context_id,
        task,
        variant,
    )
    return (
        f"Isolated delegation requested for '{task}' "
        f"(child={child_context_id}, namespace={namespace}, variant={variant}). "
        "Requires SandboxClaim CRD + controller. Not yet implemented."
    )


# ---------------------------------------------------------------------------
# Sidecar delegation (mode 4) — placeholder
# ---------------------------------------------------------------------------


async def _run_sidecar(
    task: str,
    child_context_id: str,
    variant: str = "sandbox-legion",
) -> str:
    """Inject a sidecar container into the legion pod.

    TODO: Implement ephemeral container injection and A2A over localhost.
    """
    logger.info(
        "sidecar delegation: child=%s task=%s variant=%s",
        child_context_id,
        task,
        variant,
    )
    return (
        f"Sidecar delegation requested for '{task}' "
        f"(child={child_context_id}, variant={variant}). "
        "Requires ephemeral container support. Not yet implemented."
    )


# ---------------------------------------------------------------------------
# Delegate tool factory
# ---------------------------------------------------------------------------


def make_delegate_tool(
    workspace: str,
    llm: Any,
    parent_context_id: str = "",
    tools_list: list[Any] | None = None,
    namespace: str = "team1",
) -> Any:
    """Return a LangChain tool for multi-mode delegation.

    The delegate tool supports 4 modes (in-process, shared-pvc, isolated,
    sidecar). The LLM picks the best mode based on the task, or the caller
    can specify explicitly.

    Args:
        workspace: Path to the parent's workspace.
        llm: The LLM instance for in-process subgraphs.
        parent_context_id: The parent session's context_id.
        tools_list: Optional tools for in-process subgraphs (defaults to
            read-only explore tools).
        namespace: Kubernetes namespace for out-of-process modes.
    """

    @tool
    async def delegate(
        task: str,
        mode: str = "auto",
        variant: str = "sandbox-legion",
        timeout_minutes: int = 30,
    ) -> str:
        """Delegate a task to a child session.

        Spawns a child agent session to work on the task independently.
        The child session gets its own context_id and can use any available
        tools. Results are returned to the parent.

        Args:
            task: Description of the task for the child session.
            mode: Delegation mode. Options:
                - "auto": LLM picks based on task (default)
                - "in-process": Same process, shared filesystem (fast)
                - "shared-pvc": Separate pod, parent's PVC visible
                - "isolated": Separate pod, own workspace (for PRs)
                - "sidecar": New container in same pod
            variant: Agent variant for out-of-process modes.
            timeout_minutes: Timeout for the child session.

        Returns:
            The child session's result or status message.
        """
        child_context_id = f"child-{uuid.uuid4().hex[:12]}"

        # Auto-select mode based on task signals
        selected_mode = mode
        if mode == "auto":
            task_lower = task.lower()
            if any(
                w in task_lower
                for w in ("explore", "read", "analyze", "check", "look at", "find")
            ):
                selected_mode = "in-process"
            elif any(
                w in task_lower
                for w in ("pr", "branch", "build", "deploy", "implement")
            ):
                selected_mode = "isolated"
            elif any(w in task_lower for w in ("test", "verify", "validate", "run")):
                selected_mode = "shared-pvc"
            else:
                selected_mode = _DEFAULT_MODE

        # Validate mode
        if selected_mode not in _DELEGATION_MODES:
            return (
                f"Delegation mode '{selected_mode}' is not enabled. "
                f"Available modes: {', '.join(_DELEGATION_MODES)}"
            )

        logger.info(
            "Delegating task to child=%s mode=%s parent=%s",
            child_context_id,
            selected_mode,
            parent_context_id,
        )

        # Dispatch to mode-specific handler
        if selected_mode == "in-process":
            return await _run_in_process(
                task,
                workspace,
                llm,
                child_context_id,
                tools_list=tools_list,
                timeout=timeout_minutes * 60,
            )
        elif selected_mode == "shared-pvc":
            return await _run_shared_pvc(
                task,
                child_context_id,
                namespace=namespace,
                variant=variant,
                timeout_minutes=timeout_minutes,
            )
        elif selected_mode == "isolated":
            return await _run_isolated(
                task,
                child_context_id,
                namespace=namespace,
                variant=variant,
                timeout_minutes=timeout_minutes,
            )
        elif selected_mode == "sidecar":
            return await _run_sidecar(
                task,
                child_context_id,
                variant=variant,
            )
        else:
            return f"Unknown delegation mode: {selected_mode}"

    return delegate
