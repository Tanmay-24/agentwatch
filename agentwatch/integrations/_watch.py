"""Auto-dispatch watch() to the correct integration based on object type."""

from __future__ import annotations

from typing import Any

from agentwatch.monitor import DriftMonitor


def _dispatch(obj: Any, *, agent_id: str, webhook: str | None = None, **kwargs) -> Any:
    """Detect the type of obj and wrap it with the appropriate integration."""
    monitor = DriftMonitor(agent_id=agent_id, alert_webhook=webhook, **kwargs)

    # OpenAI client
    try:
        import openai
        if isinstance(obj, openai.OpenAI | openai.AsyncOpenAI):
            from agentwatch.integrations.openai import wrap_openai
            return wrap_openai(obj, monitor=monitor)
    except ImportError:
        pass

    # LangChain agent / runnable
    try:
        from langchain_core.runnables import Runnable
        if isinstance(obj, Runnable):
            from agentwatch.integrations.langchain import wrap_langchain
            return wrap_langchain(obj, monitor=monitor)
    except ImportError:
        pass

    # DSPy module
    try:
        import dspy
        if isinstance(obj, dspy.Module):
            from agentwatch.integrations.dspy import wrap_dspy
            return wrap_dspy(obj, monitor=monitor)
    except ImportError:
        pass

    raise TypeError(
        f"agentwatch.watch() does not support {type(obj).__name__}. "
        "Supported: openai.OpenAI, langchain Runnable, dspy.Module"
    )
