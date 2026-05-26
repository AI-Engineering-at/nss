"""Tool execution sandbox simulating WASM/WASI isolation.

Uses ProcessPoolExecutor for process-level isolation in the reference
implementation, demonstrating the isolation concept without requiring
a WASM runtime.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

import structlog

from nss.guardian.vigil import check_tool_call
from nss.models import ToolResult

logger = structlog.get_logger(__name__)


def _execute_in_sandbox(func: Callable[..., str], args: dict[str, Any]) -> str:
    """Execute a function in the current process (called by ProcessPoolExecutor)."""
    return func(**args)


class ToolSandbox:
    """Sandboxed tool execution environment.

    Validates tool calls via VIGIL before execution and enforces
    timeouts via process isolation.

    Args:
        max_workers: Maximum concurrent tool executions.
        default_timeout: Default timeout in seconds per tool call.
    """

    def __init__(
        self,
        max_workers: int = 4,
        default_timeout: float = 5.0,
    ) -> None:
        self._max_workers = max_workers
        self._default_timeout = default_timeout
        self._registry: dict[str, Callable[..., str]] = {}

    def register_tool(self, name: str, func: Callable[..., str]) -> None:
        """Register a tool function.

        Args:
            name: Tool name (must match VIGIL allow-list).
            func: Callable that takes keyword args and returns a string.
        """
        self._registry[name] = func

    def execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        user_id: str,
        timeout: float | None = None,
    ) -> ToolResult:
        """Execute a tool in the sandbox.

        Steps:
            1. VIGIL safety check (CIA validation).
            2. Verify tool is registered.
            3. Execute in ProcessPoolExecutor with timeout.
            4. Return ToolResult with execution metadata.

        Args:
            tool_name: Name of the registered tool.
            args: Arguments to pass to the tool.
            user_id: Requesting user's identifier.
            timeout: Override default timeout.

        Returns:
            ToolResult with output and metadata.
        """
        effective_timeout = timeout or self._default_timeout
        start_time = time.monotonic()

        # Step 1: VIGIL safety check
        vigil_result = check_tool_call(tool_name, args, user_id)
        if vigil_result["verdict"] == "DENY":
            return ToolResult(
                output="",
                execution_time_ms=0.0,
                sandbox_metadata={"vigil_reasons": vigil_result["reasons"]},
                vigil_verdict="DENY",
            )

        # Step 2: Check registry
        if tool_name not in self._registry:
            return ToolResult(
                output="",
                execution_time_ms=0.0,
                sandbox_metadata={"error": f"Tool '{tool_name}' not registered."},
                vigil_verdict="ALLOW",
            )

        # Step 3: Execute in sandbox
        func = self._registry[tool_name]
        try:
            with ProcessPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func, **args)
                output = future.result(timeout=effective_timeout)
        except FuturesTimeoutError:
            elapsed = (time.monotonic() - start_time) * 1000
            logger.warning("tool_timeout", tool=tool_name, timeout=effective_timeout)
            return ToolResult(
                output="",
                execution_time_ms=elapsed,
                sandbox_metadata={"error": "Execution timed out."},
                vigil_verdict="ALLOW",
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start_time) * 1000
            logger.exception("tool_execution_failed", tool=tool_name)
            return ToolResult(
                output="",
                execution_time_ms=elapsed,
                sandbox_metadata={"error": str(exc)},
                vigil_verdict="ALLOW",
            )

        elapsed = (time.monotonic() - start_time) * 1000
        logger.info("tool_executed", tool=tool_name, elapsed_ms=round(elapsed, 2))

        return ToolResult(
            output=str(output),
            execution_time_ms=elapsed,
            sandbox_metadata={"tool": tool_name, "isolated": True},
            vigil_verdict="ALLOW",
        )
