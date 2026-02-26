# AgentWatch Codebase Reference

Complete line-by-line reference for every class and method in the project.

---

## gentwatch/models.py

### `Severity(str, Enum)`
- Values: `LOW`, `MED` (not MEDIUM!), `HIGH`, `CRITICAL`
- `from_score(score: float) → Severity`: score ≥ 0.9 → CRITICAL, ≥ 0.7 → HIGH, ≥ 0.5 → MED, else LOW
- **Note**: The enum uses `"MED"` not `"MEDIUM"`. Alert dispatcher compares against `"MEDIUM"` by default which means it's not in the severity list and defaults to index 1 (MED). This is a subtle bug.

### `DetectorType(str, Enum)`
- Values: `ACTION_LOOP = "action_loop"`, `GOAL_DRIFT = "goal_drift"`, `RESOURCE_SPIKE = "resource_spike"`

### `TraceEvent` (dataclass)
Fields: `agent_id, run_id, action_type, action_name, timestamp (auto), event_id (auto uuid4[:12]), token_count=0, input_data={}, output_data={}, duration_ms=0.0, metadata={}`
- `to_dict()` → serializes all fields
- `from_dict(data)` → only accepts keys matching `__dataclass_fields__`

### `DriftEvent` (dataclass)
Fields: `agent_id, run_id, detector: DetectorType, severity: Severity, score: float, message: str, suggested_action: str, timestamp (auto), event_id (auto), context={}`
- `to_dict()` → converts `detector` to `.value`, `severity` to `.value`
- `from_dict(data)` → converts detector string → DetectorType enum, severity string → Severity enum

### `RunSummary` (dataclass)
Used internally but **not persisted to SQLite** (no save method in TraceStore).
Fields: `agent_id, run_id, start_time, end_time, total_tokens=0, total_tool_calls=0, total_llm_calls=0, action_sequence=[], duration_ms=0.0, drift_events=[], output_text=""`

### `BaselineStats` (dataclass)
Fields: `agent_id, calibration_runs=0, mean_tokens_per_run=0.0, std_tokens_per_run=0.0, mean_tools_per_run=0.0, std_tools_per_run=0.0, mean_duration_ms=0.0, std_duration_ms=0.0, common_sequences=[], goal_embedding=None, mean_goal_similarity=0.0, std_goal_similarity=0.0, is_calibrated=False`
- `to_dict()` / `from_dict()` for SQLite serialization

---

## agentwatch/monitor.py

### `DriftMonitor`

```python
__init__(
    agent_id: str,
    alert_webhook: str | None = None,
    goal_description: str = "",
    calibration_runs: int = 30,
    db_path: str | None = None,
    loop_window: int = 20,
    loop_max_repeats: int = 4,
    similarity_threshold: float = 0.5,
    spike_multiplier: float = 2.5,
    min_alert_severity: str = "MED",
    alert_cooldown: float = 60.0,
)
```
Initializes: TraceStore, Calibrator, ActionLoopDetector, GoalDriftDetector, ResourceSpikeDetector, AlertDispatcher. Loads existing baseline from store.

**`wrap(agent) → _LangChainWrapper`**
Returns a wrapper that intercepts `.invoke()`.

**`start_run(run_id=None, goal=None) → str`**
Sets `self._current_run_id`. If `goal` provided, calls `self.goal_drift.set_goal(goal)`.

**`end_run(run_id=None) → None`**
Calls `self.calibrator.update_baseline(self.agent_id)`, updates `self._baseline`, clears `_current_run_id`.

**`record_event(action_type, action_name, run_id=None, token_count=0, input_data=None, output_data=None, duration_ms=0.0, metadata=None) → list[DriftEvent]`**
Core method. Creates TraceEvent, saves to store, runs all 3 detectors, saves any drift events, fires alerts and callbacks.

**`on_drift(callback: Callable[[DriftEvent], None]) → None`**
Appends callback to `_on_drift_callbacks`.

**`get_baseline() → BaselineStats | None`**
Returns cached `_baseline`.

**`get_recent_alerts(hours=24, limit=50) → list[DriftEvent]`**
Queries store for drift events since `now - hours*3600`.

### `_LangChainWrapper`

**`invoke(input_data: dict, **kwargs) → Any`**
1. `monitor.start_run(goal=input_data.get("input") or input_data.get("query"))`
2. `monitor.record_event("llm_request", "agent_invoke", input_data=input_data)`
3. `self._agent.invoke(input_data, **kwargs)` ← real call
4. `monitor.record_event("llm_request", "agent_complete", output_data={"text": output_text}, duration_ms=..., token_count=_estimate_tokens(output_text))`
5. On exception: records `"state_transition"`, `"agent_error"`, re-raises
6. In `finally`: `monitor.end_run(run_id)`

**`__getattr__(name) → Any`**
Proxies to `self._agent` — makes wrapper transparent.

**`_estimate_tokens(text: str) → int`** (staticmethod)
`len(text) // 4` — rough 4 chars per token heuristic.

---

## agentwatch/detectors/base.py

### `BaseDetector` (ABC)
```python
__init__(store: TraceStore, enabled: bool = True)
name() → str  # abstract
check(event: TraceEvent, baseline: BaselineStats | None) → DriftEvent | None  # abstract
```

---

## agentwatch/detectors/action_loop.py

### `ActionLoopDetector(BaseDetector)`

```python
__init__(store, window_size=20, max_repeats=4, sequence_length=3, enabled=True)
```

**`check(event, baseline) → DriftEvent | None`**
- Returns None immediately if `event.action_type != "tool_call"`
- Fetches `recent = store.get_recent_actions(agent_id, run_id, window=window_size)`
- Returns None if `len(recent) < max_repeats`
- Tries `_check_single_repeat` then `_check_sequence_repeat`

**`_check_single_repeat(recent, event) → DriftEvent | None`**
- `tail = recent[-max_repeats:]`
- If `len(set(tail)) == 1` (all same): count consecutive from end
- Score: `min(1.0, repeat_count / (max_repeats * 2))`

**`_check_sequence_repeat(recent, event) → DriftEvent | None`**
- For `seq_len` in range(2, sequence_length+1):
  - Skip if `len(recent) < seq_len * max_repeats`
  - `pattern = recent[-seq_len:]` — last N actions as pattern
  - Walks backwards counting pattern repeats
  - If `repeat_count >= max_repeats` → drift

---

## agentwatch/detectors/goal_drift.py

### Module-level
- `_embedder = None` — global singleton for SentenceTransformer
- `_get_embedder()` — lazy loads `all-MiniLM-L6-v2` on CPU
- `cosine_similarity(a, b) → float` — numpy dot product / (norm_a * norm_b)

### `GoalDriftDetector(BaseDetector)`

```python
__init__(store, goal_description="", similarity_threshold=0.5, enabled=True)
```

**`set_goal(goal_description: str) → None`**
Updates `self.goal_description`, resets `self._goal_embedding = None` so it's recomputed.

**`_get_goal_embedding() → np.ndarray`**
Lazy computes and caches the goal embedding.

**`check(event, baseline) → DriftEvent | None`**
- Skips if `not enabled` or `action_type != "llm_request"`
- Skips if output text is empty or < 20 chars
- Skips if no `goal_description` set
- Computes cosine similarity between goal embedding and output embedding (truncated to 512 chars)
- If `baseline.is_calibrated and baseline.mean_goal_similarity > 0`:
  `threshold = max(config_threshold, mean - 2 × max(std, 0.05))`
- If `similarity < threshold` → drift
- Score: `min(1.0, (threshold - similarity) / threshold)`
- Context: `{similarity, threshold, output_preview[:200], goal_preview[:200]}`

**`embed_text(text: str) → list[float]`**
Public utility method. Not used internally; useful for testing.

---

## agentwatch/detectors/resource_spike.py

### `ResourceSpikeDetector(BaseDetector)`

```python
__init__(store, spike_multiplier=2.5, absolute_token_limit=50_000,
         absolute_duration_limit_ms=300_000, enabled=True)
```

**In-memory state**: `_run_counters: dict[str, dict]` — max 10 run IDs tracked (cleanup by sorted order)

**`_get_run_counter(run_id) → dict`**
Creates counter if not exists: `{total_tokens, total_duration_ms, tool_calls, llm_calls, start_time}`. Cleans oldest if >10.

**`check(event, baseline) → DriftEvent | None`**
1. Updates counter (always)
2. If `baseline.is_calibrated`: tries `_check_baseline_spike`
3. Tries `_check_absolute_limits`

**`_check_baseline_spike(event, baseline, counter) → DriftEvent | None`**
Checks 3 metrics: `total_tokens`, `total_duration_ms`, `tool_calls`
- Threshold: `mean + spike_multiplier × max(std, mean × 0.1)`
- Also requires `current > mean × 1.5` guard
- Score: `min(1.0, (current - threshold) / threshold)`
- Returns first metric that exceeds threshold

**`_check_absolute_limits(event, counter) → DriftEvent | None`**
- Token limit: `counter["total_tokens"] > absolute_token_limit` → min score 0.7
- Duration: `elapsed > absolute_duration_limit_ms` → score 0.8 (HIGH)
- Uses `time.time() - counter["start_time"]` for elapsed (wall clock, not sum of duration_ms)

---

## agentwatch/storage/__init__.py

### `TraceStore`

```python
DEFAULT_DB_PATH = Path.home() / ".agentwatch" / "agentwatch.db"
__init__(db_path: str | Path | None = None)
```

**Connection management**: `self._local = threading.local()` — each thread creates its own connection via `_conn` property.

**`_conn` property**: Creates connection if not exists, sets WAL mode, NORMAL sync, row_factory.

**`_init_db()`**: Creates all 3 tables + 4 indexes via `executescript`.

**Trace methods**:
- `save_trace(event)` — `INSERT OR REPLACE`; JSON-serializes input_data, output_data, metadata
- `get_traces(agent_id?, run_id?, since?, limit=100)` — dynamic WHERE clause
- `get_run_traces(agent_id, run_id)` — chronological ASC order
- `get_recent_actions(agent_id, run_id, window=20)` → `list[str]` of action_name, filtered to `tool_call` only, reversed (chronological)
- `get_run_ids(agent_id, limit=50)` → distinct run_ids DESC by timestamp

**Drift methods**:
- `save_drift(event)` — `INSERT OR REPLACE`; JSON-serializes context
- `get_drift_events(agent_id?, since?, severity?, limit=50)` — dynamic WHERE clause

**Baseline methods**:
- `save_baseline(baseline)` — `INSERT OR REPLACE`; JSON-serializes entire BaselineStats via `to_dict()`
- `get_baseline(agent_id)` → `BaselineStats | None`

**`get_run_stats(agent_id, run_id) → dict`**
Single SQL query with aggregations: `COUNT(*)`, `SUM(token_count)`, conditional tool/llm counts, `MIN/MAX(timestamp)`, `SUM(duration_ms)`.

**`_row_to_trace(row)` / `_row_to_drift(row)`** — static helpers, JSON-deserialize fields.

**`close()`** — closes thread-local connection.

---

## agentwatch/baseline/__init__.py

### `Calibrator`

```python
__init__(store: TraceStore, required_runs: int = 30)
```

**`update_baseline(agent_id: str) → BaselineStats`**
1. `run_ids = store.get_run_ids(agent_id, limit=required_runs)`
2. If empty: saves empty baseline, returns it
3. For each run_id: `store.get_run_stats()` → append to lists
4. `store.get_recent_actions(agent_id, run_id, window=50)` → append to all_sequences
5. numpy mean/std for tokens, tools, durations
6. `is_calibrated = len(run_ids) >= required_runs`
7. Saves and returns `BaselineStats`

**Note**: Does NOT compute `mean_goal_similarity` or `std_goal_similarity`. These fields are always 0.0.

**`_find_common_sequences(all_sequences, min_length=2, top_n=5) → list[list[str]]`**
Counter of all unique subsequences (len 2..4) across runs. Returns top 5 most common as list of lists.

---

## agentwatch/alerts/__init__.py

### Constants
```python
SEVERITY_COLORS = {"LOW": "#36a64f", "MED": "#daa520", "HIGH": "#ff6600", "CRITICAL": "#ff0000"}
SEVERITY_EMOJI = {"LOW": "🟢", "MED": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
```

### `AlertDispatcher`

```python
__init__(webhook_url=None, min_severity="MEDIUM", cooldown_seconds=60.0)
```
Internal: `_last_alert: dict[str, float]` — key is `"{agent_id}:{detector_type}"`

**`should_alert(event) → bool`**
1. Returns False if no webhook_url
2. Severity check: `severity_order = ["LOW", "MED", "HIGH", "CRITICAL"]`; `min_severity.index()` — **bug**: default is "MEDIUM" which isn't in list, defaults to index 1 (MED position, effectively same as "MED")
3. Cooldown check: `now - _last_alert[key] < cooldown_seconds`

**`send_async(event) → bool`** (async, never called in current codebase)
Uses `httpx.AsyncClient`.

**`send_sync(event) → bool`** (sync, always called)
Uses `httpx.Client`. Blocking.

**`_build_payload(event) → dict`**
Auto-detects: `"hooks.slack.com"` → slack, `"discord.com"` → discord, else generic.

**`_slack_payload`**: `attachments[0].blocks[0]` with mrkdwn text, colored attachment.

**`_discord_payload`**: `embeds[0]` with title, color as int, fields.

**`_generic_payload`**: `{"source": "agentwatch", "event": event.to_dict()}`

---

## agentwatch/cli.py

Entry point: `agentwatch` command (configured in pyproject.toml).

**`@click.group() cli(ctx, db)`** — creates TraceStore, stores in `ctx.obj["store"]`

**`alerts` command**: `--last 24h --agent --severity --limit 20`
- Parses time window (`_parse_time_window`: supports `m/h/d` suffixes)
- Calls `store.get_drift_events()`
- Rich-formatted output with severity colors

**`traces` command**: `agent_id --run latest --limit 50`
- If `run == "latest"`: gets first from `store.get_run_ids(agent_id, limit=1)`
- Calls `store.get_run_traces(agent_id, run)`
- Rich table: time, type, action, tokens, duration

**`baseline` command**: `agent_id`
- `store.get_baseline(agent_id)`
- Shows CALIBRATED/PENDING status, stats, common sequences

**`runs` command**: `agent_id --limit 10`
- `store.get_run_ids()` then `store.get_run_stats()` per run
- Rich table: run_id, events, tokens, tools, duration

---

## agentwatch/crewai.py

### `DriftCrew`

```python
__init__(crew, agent_id, alert_webhook=None, goal_description="",
         calibration_runs=30, db_path=None, **monitor_kwargs)
```
Creates `DriftMonitor` internally.

**`kickoff(**kwargs) → Any`**
1. Goal extraction: `crew.description` → `crew.tasks[0].description` → `""`
2. `monitor.start_run(goal=goal)`
3. `record_event("llm_request", "crew_kickoff", ...)`
4. `self._crew.kickoff(**kwargs)`
5. `record_event("llm_request", "crew_complete", token_count=len(output)//4, ...)`
6. On error: `record_event("state_transition", "crew_error", ...)`
7. `finally: monitor.end_run(run_id)`

**`__getattr__(name)`** — proxies to `self._crew`

---

## tests/test_standalone.py

**Does NOT import**: `sentence-transformers`, `crewai`, `langchain` — runs with stdlib + numpy only.

**Test classes**:
- `TestModels`: severity score mapping, TraceEvent round-trip
- `TestTraceStore`: save/retrieve, recent actions order, run stats aggregation, baseline round-trip
- `TestActionLoopDetector`: single tool loop (5 calls), no false positive (varied tools), sequence loop (A→B×8)
- `TestResourceSpikeDetector`: absolute token limit (10 × 100 tokens → hits 500 limit), baseline spike (5 × 100 tokens vs baseline mean=200 std=50 multiplier=2.0 → threshold=300, 500 tokens > 300)
- `TestDriftMonitor`: end-to-end loop detection, clean run no drift, baseline calibration after 6 runs (requires 5), drift callbacks, get_recent_alerts

---

## Known Bugs (Quick Reference)

| Location | Bug |
|----------|-----|
| `alerts/__init__.py:51` | `min_severity` default is "MEDIUM" but enum uses "MED"; causes KeyError handled by defaulting to index -1 → effectively no minimum filter |
| `baseline/__init__.py` | Never computes `mean_goal_similarity`/`std_goal_similarity`; GoalDriftDetector baseline branch never fires |
| `monitor.py:251` | Token estimation is `len(text) // 4`; wildly inaccurate for non-English or code |
| `alerts/__init__.py:66` | `send_async` defined but never called; all alerts are blocking sync HTTP |
| `detectors/action_loop.py:48` | Only checks `tool_call` events; loop detection blind to `llm_request` loops |
| `storage/__init__.py` | No schema versioning/migrations |
| `monitor.py:_LangChainWrapper` | Only 2 events captured per `.invoke()`; internal tool calls invisible |
