"""AgentWatch wrapper for the OpenAI Python SDK."""

from __future__ import annotations

import time
from typing import Any

from agentwatch.monitor import DriftMonitor


class _WatchedCompletions:
    def __init__(self, completions: Any, monitor: DriftMonitor) -> None:
        self._completions = completions
        self._monitor = monitor

    def create(self, *args: Any, **kwargs: Any) -> Any:
        run_id = self._monitor.start_run()
        start = time.time()
        try:
            response = self._completions.create(*args, **kwargs)
            duration_ms = (time.time() - start) * 1000
            token_count = 0
            output_text = ""
            if hasattr(response, "usage") and response.usage:
                token_count = response.usage.total_tokens or 0
            if hasattr(response, "choices") and response.choices:
                output_text = response.choices[0].message.content or ""
            self._monitor.record_event(
                action_type="llm_request",
                action_name="chat.completions.create",
                run_id=run_id,
                token_count=token_count,
                duration_ms=duration_ms,
                output_text=output_text,
            )
            self._monitor.end_run(run_id)
            return response
        except Exception:
            self._monitor.end_run(run_id)
            raise

    def __getattr__(self, name: str) -> Any:
        return getattr(self._completions, name)


class _WatchedChat:
    def __init__(self, chat: Any, monitor: DriftMonitor) -> None:
        self._chat = chat
        self.completions = _WatchedCompletions(chat.completions, monitor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._chat, name)


class _WatchedOpenAI:
    """Proxies an openai.OpenAI client, intercepting chat completion calls."""

    def __init__(self, client: Any, monitor: DriftMonitor) -> None:
        self._client = client
        self._monitor = monitor
        self.chat = _WatchedChat(client.chat, monitor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def wrap_openai(client: Any, *, monitor: DriftMonitor) -> _WatchedOpenAI:
    """Wrap an openai.OpenAI client with AgentWatch monitoring."""
    return _WatchedOpenAI(client, monitor)
