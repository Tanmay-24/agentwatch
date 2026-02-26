# Changelog

All notable changes to AgentWatch will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Auto-correction hooks (retry, context trim, kill run)
- Preset baseline templates
- Better multi-agent support with parent-child hierarchies
- Predictive drift detection
- Web dashboard for historical analytics
- OpenTelemetry export support
- Prometheus metrics endpoint
- pytest plugin for automatic agent monitoring

---

## [0.1.0] - 2026-02-26

### Added
- Initial release of AgentWatch
- Three core detectors:
  - **Action Loop Detection** — catches agents stuck in repetitive tool call patterns
  - **Goal Drift Detection** — detects semantic drift from declared objective using CPU-local embeddings
  - **Resource Spike Detection** — flags abnormal token burn and execution duration
- LangChain agent wrapping via `DriftMonitor.wrap()`
- CrewAI integration via `DriftCrew`
- Manual event instrumentation API for custom agents
- Slack and Discord webhook alerting
- SQLite-based local trace storage (thread-safe)
- Baseline calibration system (statistical norms from initial runs)
- Click CLI: `agentwatch alerts`, `traces`, `baseline`, `runs` commands
- Comprehensive test suite (stdlib + numpy, no external ML dependencies)
- Full documentation: ARCHITECTURE.md, CODEBASE.md, CLAUDE.md

### Known Limitations
- LangChain wrapper captures only high-level events (start/end); requires manual instrumentation for per-tool calls
- Goal similarity baseline never computed during calibration (always 0.0)
- Token counting uses character-based heuristic (len(text) // 4)
- Alert dispatch is blocking (synchronous HTTP POST)
- Input-aware loop detection not implemented (only tool names tracked)
- No SQLite schema versioning/migration system
- CrewAI integration only wraps top-level kickoff() call
- Entirely synchronous (no async/await support)
- All detectors must run together (no individual enable/disable)

See [WEAKNESSES.md](WEAKNESSES.md) for full list of documented gaps and remediation plans.

---

## [Upcoming Releases]

### v0.2.0
- [ ] LangChain BaseCallbackHandler for per-tool event capture
- [ ] Goal similarity baseline computation
- [ ] Accurate token counting via tiktoken / LLM API
- [ ] Async alert dispatch (background thread)
- [ ] Input-aware loop detection with action fingerprinting
- [ ] SQLite schema versioning and migrations
- [ ] Configurable per-detector enable/disable
- [ ] Severity enum fix (MED vs MEDIUM)

### v0.3.0
- [ ] OpenTelemetry span export
- [ ] Prometheus metrics endpoint
- [ ] pytest plugin for test-time monitoring
- [ ] Retry/backoff detector
- [ ] Multi-agent parent-child tracking
- [ ] GitHub Actions example workflow
- [ ] Docker Compose demo setup
- [ ] YAML config file support (agentwatch.yaml)

### v1.0.0
- [ ] Web dashboard (FastAPI + React)
- [ ] Hosted cloud option (optional)
- [ ] Team collaboration features
- [ ] Historical analytics and trending
- [ ] Predictive drift alerts
- [ ] Auto-remediation hooks

---
