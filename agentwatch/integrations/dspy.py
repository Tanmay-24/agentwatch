"""AgentWatch integration for DSPy modules."""

from __future__ import annotations

import time
from typing import Any

from agentwatch.monitor import DriftMonitor


class _WatchedDSPyModule:
    """Wraps a dspy.Module, recording each forward() call as a monitored run."""

    def __init__(self, module: Any, monitor: DriftMonitor) -> None:
        self._module = module
        self._monitor = monitor

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        run_id = self._monitor.start_run()
        start = time.time()
        try:
            result = self._module(*args, **kwargs)
            duration_ms = (time.time() - start) * 1000
            output_text = str(result) if result is not None else ""
            self._monitor.record_event(
                action_type="llm_request",
                action_name=type(self._module).__name__,
                run_id=run_id,
                duration_ms=duration_ms,
                output_text=output_text,
            )
            self._monitor.end_run(run_id)
            return result
        except Exception:
            self._monitor.end_run(run_id)
            raise

    def forward(self, *args: Any, **kwargs: Any) -> Any:
        return self(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._module, name)


def wrap_dspy(module: Any, *, monitor: DriftMonitor) -> _WatchedDSPyModule:
    """Wrap a dspy.Module with AgentWatch monitoring."""
    return _WatchedDSPyModule(module, monitor)
