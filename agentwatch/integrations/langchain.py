"""AgentWatch integration for LangChain via BaseCallbackHandler."""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from agentwatch.monitor import DriftMonitor


class AgentWatchCallbackHandler:
    """LangChain callback handler that records every tool call and LLM request."""

    def __init__(self, monitor: DriftMonitor, run_id: str) -> None:
        self._monitor = monitor
        self._run_id = run_id
        self._tool_starts: dict[str, float] = {}
        self._llm_starts: dict[str, float] = {}

    # --- Tool events ---

    def on_tool_start(
        self, serialized: dict, input_str: str, *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._tool_starts[str(run_id)] = time.time()
        tool_name = serialized.get("name", "unknown_tool")
        self._monitor.record_event(
            action_type="tool_call",
            action_name=tool_name,
            run_id=self._run_id,
        )

    def on_tool_end(self, output: str, *, run_id: UUID, **kwargs: Any) -> None:
        start = self._tool_starts.pop(str(run_id), None)
        duration_ms = (time.time() - start) * 1000 if start else None
        self._monitor.record_event(
            action_type="tool_result",
            action_name="tool_end",
            run_id=self._run_id,
            duration_ms=duration_ms,
        )

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._tool_starts.pop(str(run_id), None)

    # --- LLM events ---

    def on_llm_start(
        self, serialized: dict, prompts: list[str], *, run_id: UUID, **kwargs: Any
    ) -> None:
        self._llm_starts[str(run_id)] = time.time()

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        start = self._llm_starts.pop(str(run_id), None)
        duration_ms = (time.time() - start) * 1000 if start else None
        token_count = 0
        output_text = ""
        if hasattr(response, "llm_output") and response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            token_count = usage.get("total_tokens", 0)
        if response.generations:
            output_text = response.generations[0][0].text if response.generations[0] else ""
        self._monitor.record_event(
            action_type="llm_request",
            action_name="llm_end",
            run_id=self._run_id,
            token_count=token_count,
            duration_ms=duration_ms,
            output_text=output_text,
        )


class _WatchedRunnable:
    """Wraps a LangChain Runnable, injecting AgentWatchCallbackHandler on every invoke."""

    def __init__(self, runnable: Any, monitor: DriftMonitor) -> None:
        self._runnable = runnable
        self._monitor = monitor

    def invoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> Any:
        run_id = self._monitor.start_run()
        handler = AgentWatchCallbackHandler(self._monitor, run_id)
        config = config or {}
        config.setdefault("callbacks", [])
        config["callbacks"].append(handler)
        try:
            result = self._runnable.invoke(input, config=config, **kwargs)
            self._monitor.end_run(run_id)
            return result
        except Exception:
            self._monitor.end_run(run_id)
            raise

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runnable, name)


def wrap_langchain(runnable: Any, *, monitor: DriftMonitor) -> _WatchedRunnable:
    """Wrap a LangChain Runnable with AgentWatch monitoring."""
    return _WatchedRunnable(runnable, monitor)
