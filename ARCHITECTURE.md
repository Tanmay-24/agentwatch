# DriftShield Architecture

## System Overview

```
User's Agent Code
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                    DriftMonitor                          │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │_LangChainWrapper│  │  DriftCrew   │  (optional wrappers)
│  └──────┬───────┘    └──────┬───────┘                   │
│         │                   │                            │
│         ▼                   ▼                            │
│              record_event()                              │
│                    │                                     │
│          ┌─────────▼──────────┐                         │
│          │    TraceEvent      │                         │
│          │  (created + saved) │                         │
│          └─────────┬──────────┘                         │
│                    │                                     │
│         ┌──────────┼──────────┐                         │
│         ▼          ▼          ▼                         │
│  ┌────────────┐ ┌──────────┐ ┌──────────────┐          │
│  │ActionLoop  │ │GoalDrift │ │ResourceSpike │          │
│  │Detector    │ │Detector  │ │Detector      │          │
│  └─────┬──────┘ └────┬─────┘ └──────┬───────┘          │
│        │              │              │                   │
│        └──────────────┼──────────────┘                  │
│                       │ DriftEvent (if detected)         │
│                       ▼                                  │
│          ┌────────────────────────┐                     │
│          │      TraceStore        │  ← SQLite           │
│          │  (save drift + trace)  │                     │
│          └────────────────────────┘                     │
│                       │                                  │
│          ┌────────────┼──────────────┐                  │
│          ▼            ▼              ▼                  │
│   AlertDispatcher  Calibrator   User Callbacks          │
│   (Slack/Discord)  (update      (on_drift hooks)        │
│                     baseline)                            │
└─────────────────────────────────────────────────────────┘
```

## Data Flow: Single Event

1. User's agent calls a tool → user calls `monitor.record_event(action_type="tool_call", action_name="search_db", ...)`
2. `DriftMonitor.record_event()` creates a `TraceEvent` dataclass
3. `TraceStore.save_trace(event)` persists to SQLite `trace_events` table
4. All 3 detectors run sequentially: `detector.check(event, baseline) → DriftEvent | None`
5. If drift detected:
   - `TraceStore.save_drift(drift_event)` persists to `drift_events` table
   - `AlertDispatcher.send_sync(drift)` posts to webhook (if severity ≥ min_severity and cooldown passed)
   - User callbacks fire: `for cb in self._on_drift_callbacks: cb(drift_event)`
6. At `end_run()`: `Calibrator.update_baseline(agent_id)` recalculates baseline stats from all stored runs

## Data Flow: LangChain Wrapper

```
agent.invoke({"input": "..."})
        │
        ▼
_LangChainWrapper.invoke()
   │
   ├─ monitor.start_run(goal=input_text)      # Sets run_id, sets goal embedding
   ├─ monitor.record_event("llm_request", "agent_invoke", input_data=...)
   ├─ self._agent.invoke(input_data, **kwargs)  # ← Real agent call
   ├─ monitor.record_event("llm_request", "agent_complete", output_data=..., token_count=...)
   └─ monitor.end_run(run_id)
```

**Critical limitation**: Only 2 events are captured per `.invoke()` call — the start and end. No intermediate tool calls are visible unless the user manually instruments them.

## Component Details

### DriftMonitor (monitor.py)

The central orchestrator. Instantiated once per agent type.

**Constructor parameters**:
| Parameter | Default | Effect |
|-----------|---------|--------|
| `agent_id` | required | Namespaces all stored data |
| `alert_webhook` | None | Slack/Discord/generic webhook URL |
| `goal_description` | "" | Text description of agent's objective (used by GoalDriftDetector) |
| `calibration_runs` | 30 | Runs before baseline is considered calibrated |
| `db_path` | `~/.driftshield/driftshield.db` | SQLite location |
| `loop_window` | 20 | Recent actions to scan for loops |
| `loop_max_repeats` | 4 | Consecutive repeats before flagging |
| `similarity_threshold` | 0.5 | Cosine similarity cutoff for goal drift |
| `spike_multiplier` | 2.5 | `mean + N×std` threshold for resource spikes |
| `min_alert_severity` | "MED" | Minimum severity to fire webhook |
| `alert_cooldown` | 60.0 | Seconds between same-type alerts for same agent |

**Key methods**:
- `wrap(agent)` → returns `_LangChainWrapper`
- `start_run(run_id?, goal?)` → sets `_current_run_id`, returns run_id
- `end_run(run_id?)` → triggers `Calibrator.update_baseline()`
- `record_event(...)` → core method: saves trace, runs detectors, fires alerts
- `on_drift(callback)` → registers a callback function
- `get_recent_alerts(hours, limit)` → queries drift events from store

### TraceEvent (models.py)

```python
@dataclass
class TraceEvent:
    agent_id: str
    run_id: str
    action_type: str    # "tool_call" | "llm_request" | "state_transition"
    action_name: str    # e.g. "search_database", "agent_invoke", "agent_error"
    timestamp: float    # auto: time.time()
    event_id: str       # auto: uuid4 hex 12 chars
    token_count: int    # 0 by default; set manually or estimated
    input_data: dict
    output_data: dict
    duration_ms: float
    metadata: dict
```

`action_type` values used throughout codebase:
- `"tool_call"` — triggers ActionLoopDetector
- `"llm_request"` — triggers GoalDriftDetector; counted by ResourceSpikeDetector
- `"state_transition"` — used for errors/transitions; no detector specifically handles this

### DriftEvent (models.py)

```python
@dataclass
class DriftEvent:
    agent_id: str
    run_id: str
    detector: DetectorType    # ACTION_LOOP | GOAL_DRIFT | RESOURCE_SPIKE
    severity: Severity        # LOW | MED | HIGH | CRITICAL
    score: float              # 0.0 - 1.0 (normalized drift intensity)
    message: str              # Human-readable description
    suggested_action: str     # What the user should do
    timestamp: float
    event_id: str
    context: dict             # Detector-specific data (tool names, similarity values, etc.)
```

**Severity mapping** (`Severity.from_score(score)`):
- score ≥ 0.9 → CRITICAL
- score ≥ 0.7 → HIGH
- score ≥ 0.5 → MEDIUM
- score < 0.5 → LOW

### BaselineStats (models.py)

```python
@dataclass
class BaselineStats:
    agent_id: str
    calibration_runs: int           # How many runs fed into this baseline
    mean_tokens_per_run: float
    std_tokens_per_run: float
    mean_tools_per_run: float
    std_tools_per_run: float
    mean_duration_ms: float
    std_duration_ms: float
    common_sequences: list[list[str]]  # Top-5 most common action subsequences
    goal_embedding: list[float] | None # NOTE: stored but never actually used
    mean_goal_similarity: float
    std_goal_similarity: float
    is_calibrated: bool              # True only after calibration_runs runs
```

### ActionLoopDetector (detectors/action_loop.py)

**Trigger**: `event.action_type == "tool_call"` only.

**Algorithm**:
1. Fetches last `window_size` (default 20) tool call names for this agent+run from SQLite
2. If fewer than `max_repeats` actions exist, returns None
3. **Single repeat check**: Takes last `max_repeats` actions; if they're all the same tool → drift
4. **Sequence repeat check**: For pattern lengths 2..`sequence_length` (default 3):
   - Extracts pattern from end of recent list
   - Counts how many times that pattern repeats backwards
   - If ≥ `max_repeats` → drift

**Score calculation**: `min(1.0, repeat_count / (max_repeats * 2))`

**Context included in DriftEvent**:
- `tool_name`, `repeat_count`, `recent_actions[-10:]`
- For sequences: `sequence`, `repeat_count`, `recent_actions[-15:]`

### GoalDriftDetector (detectors/goal_drift.py)

**Trigger**: `event.action_type == "llm_request"` AND `event.output_data` contains `"text"` or `"output"` key with ≥20 chars AND `goal_description` is set.

**Model**: `all-MiniLM-L6-v2` via `sentence-transformers`, CPU-only, lazy-loaded on first use.

**Algorithm**:
1. Encode goal description → 384-dim embedding (cached after first call)
2. Encode output text (truncated to 512 chars) → 384-dim embedding
3. Compute cosine similarity
4. Determine threshold:
   - If baseline calibrated and `baseline.mean_goal_similarity > 0`:
     `threshold = max(config_threshold, baseline.mean - 2 × max(std, 0.05))`
   - Otherwise: use config `similarity_threshold` (default 0.5)
5. If `similarity < threshold` → drift

**Score**: `min(1.0, (threshold - similarity) / threshold)`

**Bug**: `baseline.mean_goal_similarity` is never populated by the Calibrator (it doesn't compute goal similarities during calibration). So the baseline branch effectively never fires.

### ResourceSpikeDetector (detectors/resource_spike.py)

**Trigger**: Any event (checks resource counters regardless of action_type).

**Per-run in-memory counters** (reset when new run_id seen, max 10 runs tracked):
```python
{
    "total_tokens": 0,
    "total_duration_ms": 0.0,
    "tool_calls": 0,
    "llm_calls": 0,
    "start_time": time.time()
}
```

**Detection layers**:

1. **Baseline-statistical** (only if `baseline.is_calibrated`):
   - Checks: `total_tokens`, `total_duration_ms`, `tool_calls`
   - Threshold: `mean + spike_multiplier × max(std, mean × 0.1)`
   - Also requires `current > mean × 1.5` (prevents tiny absolute spikes)
   - Score: `min(1.0, (current - threshold) / threshold)`

2. **Absolute limits** (always active, safety net):
   - Token limit: `absolute_token_limit` default **50,000 tokens**
   - Duration limit: `absolute_duration_limit_ms` default **300,000 ms (5 minutes)**
   - Minimum score for token limit: 0.7 (always HIGH or CRITICAL)
   - Duration always scores 0.8 (HIGH)

### TraceStore (storage/__init__.py)

SQLite wrapper. Default path: `~/.driftshield/driftshield.db`.

**Thread safety**: Uses `threading.local()` so each thread gets its own connection.

**Pragmas**: `journal_mode=WAL` (allows concurrent reads), `synchronous=NORMAL`

**Tables**:
```sql
trace_events (event_id PK, agent_id, run_id, action_type, action_name,
              timestamp, token_count, input_data JSON, output_data JSON,
              duration_ms, metadata JSON)

drift_events (event_id PK, agent_id, run_id, detector, severity, score,
              message, suggested_action, timestamp, context JSON)

baselines (agent_id PK, data JSON, updated_at)
```

**Indexes**: `(agent_id, timestamp)` on both trace_events and drift_events; `(severity, timestamp)` on drift_events; `(run_id, timestamp)` on trace_events.

**Key methods**:
- `save_trace(event)` / `get_traces(agent_id?, run_id?, since?, limit=100)`
- `get_run_traces(agent_id, run_id)` — chronological order
- `get_recent_actions(agent_id, run_id, window=20)` — returns list of `action_name` strings for `tool_call` events only
- `get_run_ids(agent_id, limit=50)` — distinct run IDs, most recent first
- `get_run_stats(agent_id, run_id)` → `{event_count, total_tokens, tool_calls, llm_calls, start_time, end_time, total_duration_ms}`
- `save_baseline(baseline)` / `get_baseline(agent_id)`

### Calibrator (baseline/__init__.py)

Called by `DriftMonitor.end_run()` after every run.

**Algorithm**:
1. Fetches last `required_runs` run IDs from store
2. For each run: fetches aggregate stats (tokens, tools, duration)
3. Computes `mean` and `std` for each metric using numpy
4. Extracts common action subsequences (length 2-4, top 5 most frequent across runs)
5. Sets `is_calibrated = len(run_ids) >= required_runs`
6. Saves updated `BaselineStats` to store

**`_find_common_sequences`**: For each run's action sequence, extracts all unique subsequences of length 2-4, counts occurrences across runs, returns top 5. Used for context but not actually used in detection decisions.

### AlertDispatcher (alerts/__init__.py)

**Cooldown**: Per `agent_id:detector_type` key, tracks last alert timestamp. Won't re-alert within `cooldown_seconds` (default 60s).

**Severity filter**: Won't alert if `event.severity` is below `min_severity` in `[LOW, MED, HIGH, CRITICAL]` order.

**Payload formats**:
- Slack (`hooks.slack.com` in URL): `attachments` with colored `blocks`
- Discord (`discord.com` in URL): `embeds` with color as integer
- Generic: `{"source": "driftshield", "event": event.to_dict()}`

**Bug**: `send_async()` exists but is never called. `send_sync()` is always used, which blocks the calling thread during HTTP POST.

### DriftCrew (crewai.py)

Thin wrapper around CrewAI's `.kickoff()`. Creates a `DriftMonitor` internally.

**Goal extraction** (fragile):
1. Tries `crew.description`
2. Falls back to `crew.tasks[0].description`
3. Falls back to empty string

Only wraps start/end of `kickoff()` — no per-agent or per-task events captured.

## SQLite Schema (Complete)

```sql
CREATE TABLE trace_events (
    event_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    action_name TEXT NOT NULL,
    timestamp REAL NOT NULL,
    token_count INTEGER DEFAULT 0,
    input_data TEXT DEFAULT '{}',
    output_data TEXT DEFAULT '{}',
    duration_ms REAL DEFAULT 0.0,
    metadata TEXT DEFAULT '{}'
);

CREATE TABLE drift_events (
    event_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    detector TEXT NOT NULL,
    severity TEXT NOT NULL,
    score REAL NOT NULL,
    message TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    timestamp REAL NOT NULL,
    context TEXT DEFAULT '{}'
);

CREATE TABLE baselines (
    agent_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX idx_traces_agent ON trace_events(agent_id, timestamp);
CREATE INDEX idx_traces_run ON trace_events(run_id, timestamp);
CREATE INDEX idx_drift_agent ON drift_events(agent_id, timestamp);
CREATE INDEX idx_drift_severity ON drift_events(severity, timestamp);
```

## Detector Decision Matrix

| Event action_type | ActionLoop | GoalDrift | ResourceSpike |
|-------------------|-----------|-----------|---------------|
| `tool_call` | ✓ checks | ✗ skips | ✓ counts tool_calls |
| `llm_request` | ✗ skips | ✓ checks (if output exists) | ✓ counts llm_calls + tokens |
| `state_transition` | ✗ skips | ✗ skips | ✓ counts duration |

## Calibration State Machine

```
State: UNCALIBRATED (calibration_runs < required_runs)
  ├─ ActionLoopDetector: active (rule-based, no baseline needed)
  ├─ GoalDriftDetector: active (uses config threshold, not baseline)
  └─ ResourceSpikeDetector: only absolute limits active

State: CALIBRATED (calibration_runs >= required_runs)
  ├─ ActionLoopDetector: active (unchanged)
  ├─ GoalDriftDetector: active (threshold may use baseline if mean_goal_similarity > 0)
  └─ ResourceSpikeDetector: both baseline-statistical AND absolute limits active
```
