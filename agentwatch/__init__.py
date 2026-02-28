"""
AgentWatch — Real-time behavioural drift detection for agentic AI systems.

Usage:
    from agentwatch import watch

    client = watch(OpenAI(), agent_id="my-agent", webhook="https://hooks.slack.com/...")
    response = client.chat.completions.create(...)  # automatically monitored
"""

from agentwatch.models import BaselineStats, DetectorType, DriftEvent, Severity, TraceEvent
from agentwatch.monitor import DriftMonitor

__version__ = "0.1.0"

__all__ = [
    "watch",
    "DriftMonitor",
    "TraceEvent",
    "DriftEvent",
    "BaselineStats",
    "DetectorType",
    "Severity",
]


def watch(obj, *, agent_id: str, webhook: str | None = None, **kwargs):
    """Wrap any supported client or agent with AgentWatch monitoring.

    Supported: openai.OpenAI, langchain agents, dspy.Module

    Example:
        client = watch(OpenAI(), agent_id="my-agent", webhook="https://hooks.slack.com/...")
    """
    from agentwatch.integrations._watch import _dispatch
    return _dispatch(obj, agent_id=agent_id, webhook=webhook, **kwargs)
