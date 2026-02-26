"""
AgentWatch — Real-time behavioural drift detection for agentic AI systems.

Usage:
    from agentwatch import DriftMonitor

    monitor = DriftMonitor(
        agent_id="my-agent",
        alert_webhook="https://hooks.slack.com/...",
    )
    agent = monitor.wrap(existing_agent)
    result = agent.invoke({"input": "do the thing"})
"""

from agentwatch.models import BaselineStats, DetectorType, DriftEvent, Severity, TraceEvent
from agentwatch.monitor import DriftMonitor

__version__ = "0.1.0"

__all__ = [
    "DriftMonitor",
    "TraceEvent",
    "DriftEvent",
    "BaselineStats",
    "DetectorType",
    "Severity",
]
