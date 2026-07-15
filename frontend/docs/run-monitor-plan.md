# Run Monitor Frontend Plan

## Goal

Design and implement a frontend-only Run Monitor page for live and historic simulation runs. The first version uses mock telemetry shaped like future backend data, without changing FastAPI, workers, Kafka, Redis, or database code.

## Current Scope

- Add a Run Monitor tab to the dashboard.
- Show a realistic monitoring workspace for energy and traffic runs.
- Keep the data provider isolated so mock polling can later be replaced by HTTP, SSE, or WebSocket transport.
- Support metric selection/pinning in the UI.
- Use existing Svelte/Vite patterns and current design tokens.

## Initial UI Areas

- Run header with scenario ID, task ID, status, simulated time, progress, and update time.
- Domain/sample selector for energy and traffic mock runs.
- Metric cards for pinned signals.
- Timeline strip for simulation progress.
- Visualization panel:
  - Energy: topology-style bus/line view with voltage/loading cues.
  - Traffic: projected 2D vehicle positions with selectable vehicles.
- Metric history charts.
- Events/logs panel with structured entries.
- Monitor picker for choosing pinned metrics.

## Data Shape

The frontend should consume batches shaped like:

```js
{
  cursor,
  snapshot,
  metrics,
  metricHistory,
  entities,
  network,
  events,
  observables
}
```

The mock client should expose a polling-style method:

```js
getSnapshot(runKey, cursor)
```

Later this can map to:

```text
GET /runs/{task_id}/monitor?since={cursor}
```

or to an SSE/WebSocket stream that is fed by a backend adapter consuming Kafka telemetry.

## Backend Boundary

Kafka remains internal to the simulation system. The browser should receive simplified monitor snapshots, not raw Kafka messages or simulator-specific topic payloads.

## Future Integration Notes

- Pandapower metrics likely include convergence, min/max voltage, total load/generation, losses, and line loading.
- SUMO metrics likely include active vehicles, arrived/departed counts, average speed, and reduced/projected vehicle positions.
- High-volume SUMO position telemetry should be aggregated or filtered before reaching the browser.
