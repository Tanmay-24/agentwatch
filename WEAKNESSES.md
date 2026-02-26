# DriftShield — Known Weaknesses & Improvement Opportunities

## Critical Gaps (Must Fix for Production)

### 1. Manual Instrumentation Required
**Problem**: The LangChain wrapper only intercepts the top-level `.invoke()` call. All internal tool calls, intermediate LLM requests, and state transitions are invisible.

**Impact**: ActionLoopDetector can never fire when using the wrapper. GoalDriftDetector only sees the final output. Resource tracking is coarse.

**Fix**: Use LangChain callbacks (`BaseCallbackHandler`) to intercept tool calls automatically. Implement `on_tool_start`, `on_tool_end`, `on_llm_start`, `on_llm_end` hooks.

### 2. Goal Similarity Baseline Never Computed
**Problem**: `Calibrator.update_baseline()` never computes `mean_goal_similarity` or `std_goal_similarity`. These fields are always 0.0. The GoalDriftDetector's baseline branch (`if baseline and baseline.is_calibrated and baseline.mean_goal_similarity > 0`) never fires.

**Fix**: During calibration, for each run, compute and store goal embeddings and similarities. Track running mean/std of similarity scores across runs.

### 3. Token Counting is a Heuristic
**Problem**: `_estimate_tokens(text)` uses `len(text) // 4`. Real LLM APIs count subword tokens, not characters.

**Impact**: ResourceSpikeDetector token counts are inaccurate, especially for code, non-English text, or structured data.

**Fix**: Accept actual token counts from LLM API responses. Use `tiktoken` for OpenAI models. Pass token counts explicitly via `record_event(token_count=actual_count)`.

### 4. Blocking HTTP Alerts
**Problem**: `AlertDispatcher.send_sync()` is a blocking HTTP call that happens inline during `record_event()`. Slow webhooks will delay agent execution.

**Fix**: Use `asyncio.create_task()` or a background thread queue to send alerts without blocking.

### 5. No Input-Aware Loop Detection
**Problem**: ActionLoopDetector only looks at action names. `search("query1")` and `search("query2")` look identical — both are just `"search"`. Can't distinguish legitimate retries from stuck loops.

**Fix**: Hash or fingerprint action inputs. Flag when same action fires with identical inputs consecutively.

### 6. No Schema Migrations
**Problem**: SQLite tables created once, never migrated. Adding a column to `TraceEvent` breaks existing databases.

**Fix**: Track schema version in a `meta` table. Run migration scripts on startup.

---

## Moderate Issues

### 7. Alert Cooldown Masks Ongoing Issues
60-second default cooldown means if an agent drifts continuously, only the first alert fires per minute. Users won't know the issue persists.

**Fix**: Add escalating severity for repeated drift. After N alerts on cooldown, send a "still drifting" summary.

### 8. Baseline Contamination Risk
If the first 30 runs include anomalies, baseline stats will be corrupted. No outlier rejection during calibration.

**Fix**: Use median instead of mean for baseline stats. Implement IQR-based outlier removal during calibration.

### 9. CrewAI Integration is Shallow
Only wraps `kickoff()`. No per-agent, per-task, or per-step events. Multi-agent traces are collapsed into a single run.

**Fix**: Hook into CrewAI's task callbacks to capture individual agent outputs and tool usage.

### 10. No Async Support
Codebase is entirely synchronous. Modern agent frameworks are async-first.

**Fix**: Add `async_record_event()`, `async_wrap()`. Use `httpx.AsyncClient` for alerts.

### 11. Detectors Can't Be Disabled Individually
All 3 detectors run on every event. If you don't provide a `goal_description`, GoalDriftDetector still runs (just skips due to no goal). No way to configure detectors independently.

**Fix**: Accept a list of enabled detector types in DriftMonitor constructor.

### 12. Run Counter Cleanup is Order-Dependent
`ResourceSpikeDetector._run_counters` keeps last 10 runs, removes the "oldest" by key sort order. Run IDs are UUID hex strings — sort order is meaningless.

**Fix**: Track insertion order via `collections.OrderedDict`. Evict by actual time.

---

## Future Scope (V2 Features)

### Web Dashboard
- Real-time view of active agents, drift events, resource usage
- Timeline chart of runs with drift annotations
- Agent comparison: baseline vs current behavior
- Tech: FastAPI backend + React/Next.js frontend + WebSockets for live updates

### Multi-Agent Tracing
- Parent/child run hierarchy (orchestrator → sub-agents)
- Cross-agent drift detection (agent B behaves differently when called by agent A vs B)
- Distributed trace ID propagation (like OpenTelemetry)

### Learned Baselines
- Instead of simple mean/std, use Isolation Forest or One-Class SVM for anomaly detection
- Handle seasonal patterns (agents that behave differently at peak vs off-peak)
- Auto-weight recent runs higher than old runs

### Prompt Injection Detection
- Special detector that scans agent inputs/outputs for signs of prompt injection
- Keyword patterns + semantic similarity to known injection phrases

### Team Features
- Shared SQLite → PostgreSQL migration path
- Multi-user access control
- Shared alert channels per team
- Agent registry with versioning

### Streaming Support
- Intercept streaming token-by-token output
- Early termination: if drift detected mid-run, optionally abort the agent
- Running resource estimates updated per-token

### Integration Expansions
- OpenAI Assistants API
- Anthropic Claude API (direct)
- AutoGen / Microsoft Semantic Kernel
- LlamaIndex agents
- Native LangGraph support

### Evaluation Mode
- Run agent in "eval" mode: no real tool execution, just checks for drift patterns
- Useful for CI/CD: verify agent behavior doesn't regress between deployments

---

## What Works Well (Don't Break)

- SQLite thread-safety via `threading.local()` — correct and simple
- Absolute hard limits as safety net before calibration — important safety feature
- Lazy sentence-transformers loading — avoids startup cost
- `_LangChainWrapper.__getattr__` proxy — makes wrapping transparent to calling code
- Per-`agent_id:detector` cooldown keys — prevents alert spam correctly
- `is_calibrated` flag — prevents false positives before baseline is ready
