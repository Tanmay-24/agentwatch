# AgentWatch

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/badge/PyPI-agentwatch-blue.svg)](https://pypi.org/project/agentwatch/)

Your LangChain agent just called the same API 47 times. Your CrewAI crew burned £200 in tokens overnight. Your research agent started writing marketing copy instead of financial summaries.

You didn't find out until morning.

**AgentWatch catches this stuff in real-time.** It wraps your existing agent, watches what it does, and pings you on Slack or Discord the moment something goes sideways. No dashboard. No cloud. No account to create. Just a Python library that runs alongside your agent.

---

## What it actually does

AgentWatch monitors three things:

**Loop detection**:  Is your agent calling the same tool over and over? Or stuck in a cycle like `search → format → search → format`? AgentWatch spots the pattern and alerts you before it eats your budget.

**Goal drift**:  Is your agent still doing what you asked it to? AgentWatch uses local embeddings (runs on your CPU, no API calls) to measure how far the agent's output has drifted from its original objective.

**Resource spikes**:  Is this run burning way more tokens or taking way longer than usual? AgentWatch learns what "normal" looks like for your agent, then flags when things go abnormal.

Everything stays on your machine. Traces go to a local SQLite file. Embeddings run on your CPU. The only thing that leaves your machine is the alert you choose to send to Slack/Discord.

---

## Get started

```bash
pip install agentwatch

# With your framework of choice:
pip install "agentwatch[openai]"
pip install "agentwatch[langchain]"
pip install "agentwatch[dspy]"
pip install "agentwatch[all]"
```

### One-line integration — `watch()`

Wrap any supported client with a single call. AgentWatch auto-detects the type:

```python
from agentwatch import watch

# OpenAI
from openai import OpenAI
client = watch(OpenAI(), agent_id="my-agent", webhook="https://hooks.slack.com/...")
response = client.chat.completions.create(model="gpt-4o", messages=[...])

# LangChain
agent = watch(existing_langchain_agent, agent_id="my-agent", webhook="https://hooks.slack.com/...")
result = agent.invoke({"input": "summarise ticket #123"})

# DSPy
import dspy
module = watch(MyDSPyModule(), agent_id="my-agent", webhook="https://hooks.slack.com/...")
result = module(question="What is the capital of France?")
```

### Works with any model provider

Swap OpenAI for Anthropic, Groq, Ollama — doesn't matter. AgentWatch only sees the traces (tool calls, token counts, outputs), not model internals.

---

## How calibration works

For the first 30 runs (configurable), AgentWatch quietly observes your agent and builds a baseline average tokens per run, typical tool sequences, normal execution time. No alerts during this phase.

After that, it knows what "normal" looks like and starts flagging deviations. You can inspect the baseline anytime:

```bash
agentwatch baseline my-agent
```

> **Tip:** If 30 runs feels like a lot, you can lower `calibration_runs` or use a preset template. AgentWatch still catches obvious problems (like 50 identical tool calls) even without a baseline, using absolute safety limits.

---

## What an alert looks like

When drift hits your Slack/Discord, you get:

```json
{
  "agent_id": "logistics-v2",
  "detector": "action_loop",
  "severity": "HIGH",
  "message": "Action loop: search_inventory called 6x in 45s",
  "suggested_action": "Check search_inventory input/output for stale data or error loops",
  "context": {
    "tool_name": "search_inventory",
    "repeat_count": 6,
    "recent_actions": ["search_inventory", "search_inventory", "search_inventory", "..."]
  }
}
```

Not just "something's wrong" — it tells you what happened, which detector caught it, and what to check first.

---

## CLI

```bash
# What went wrong in the last 24 hours?
agentwatch alerts --last 24h

# Show me exactly what my agent did on its last run
agentwatch traces logistics-v2 --run latest

# What does "normal" look like for this agent?
agentwatch baseline logistics-v2

# List recent runs
agentwatch runs logistics-v2
```

---

## Configuration

Everything's tuneable. Defaults are sensible, but you can adjust:

```python
monitor = DriftMonitor(
    agent_id="my-agent",
    alert_webhook="https://hooks.slack.com/...",
    goal_description="Summarise financial reports",
    calibration_runs=30,         # runs before baseline kicks in
    loop_window=20,              # how many recent actions to check
    loop_max_repeats=4,          # repeated calls before flagging
    similarity_threshold=0.5,    # goal drift sensitivity (lower = stricter)
    spike_multiplier=2.5,        # how many std devs = a spike
    min_alert_severity="MED",    # ignore LOW severity events
    alert_cooldown=60.0,         # don't spam the same alert
)
```

---

## Custom reactions

AgentWatch alerts you by default, but you can also react programmatically:

```python
def handle_drift(event):
    if event.severity.value == "CRITICAL":
        agent.stop()  # kill the run
        page_oncall()  # wake someone up

monitor.on_drift(handle_drift)
```

---

## What this isn't

I want to be upfront about scope. AgentWatch is **v0.1**, built to solve a real problem with minimal overhead.

- **Not a full observability platform.** No web dashboard, no hosted backend, no team features. If you need that, look at LangSmith, Langfuse, or Arize.
- **Not a guardrail system.** It detects drift after the fact and alerts you. It doesn't block actions before they happen (that's on the roadmap).
- **Not production-hardened yet.** It works, it's tested, but it hasn't been battle-tested by thousands of users. Expect rough edges.

What it IS: the smallest, simplest tool that does one thing well — tells you when your agent is going off the rails, fast, with zero setup overhead.

---

## Roadmap

- **v0.2** — Auto-correction hooks (retry, context trim, kill run). Preset baseline templates so you get value from run 1.
- **v0.3** — Better multi-agent support. Predictive drift (catch it before it happens).
- **v1.0** — Dashboard, team features, historical analytics. But only if people actually want it.

---

## Built with

- Python 3.10+
- SQLite (zero config)
- sentence-transformers (local CPU embeddings)
- scikit-learn (basic stats)
- httpx (webhooks)
- click + rich (CLI)

---

## Contributing

This is early. If you're running agents in production and hit a case AgentWatch missed (or flagged incorrectly), please open an issue. Your real-world edge cases are the most valuable thing you can give this project right now.

**Development setup:**

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/agentwatch.git
cd agentwatch

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install in dev mode
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Why I built this

I kept reading the same story: dev builds agent, agent works great in testing, agent goes haywire in production at 2am, dev wakes up to a hefty API bill and a Slack full of confused users. The big observability platforms exist but they're heavy on dashboards, accounts, pricing tiers, cloud dependencies. Most solo devs and small teams just want to know when their agent is broken. That's it.

So I built the smallest thing that solves that problem.

If you try it and it helps (or doesn't), I genuinely want to hear about it.

---

## Documentation

- **[Getting Started Guide](docs/quickstart.md)** — 5-minute setup
- **[How Detectors Work](docs/detectors.md)** — Deep dive into the three detection mechanisms
- **[API Reference](docs/api-reference.md)** — Complete API documentation
- **[Architecture](ARCHITECTURE.md)** — System design and internals

---

## License

MIT - do whatever you want with it.
