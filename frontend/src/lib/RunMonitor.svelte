<script>
  import { onDestroy, onMount } from "svelte";
  import {
    getDefaultPinnedMetrics,
    getMonitorDebug,
    getMonitorSnapshot,
    getMockMonitorSnapshot,
  } from "./mockMonitorClient";

  export let taskId = null;

  let selectedRun = "energy";
  let activeMonitorMode = "normal";
  let cursor = 0;
  let polling = true;
  let monitor = null;
  let pinnedMetrics = getDefaultPinnedMetrics("energy");
  let selectedEntity = null;
  let pollTimer = null;
  let playbackTimer = null;
  let playbackIndex = 0;
  let playbackCount = 0;
  let followLatest = true;
  let isPlaying = false;
  let eventSource = null;
  let streamStatus = "idle";
  let debugInfo = { failedEvents: [], count: 0 };
  let debugLoadedFor = null;
  let debugLoadError = null;
  let mounted = false;
  let loadedTaskId = null;
  let loadError = null;

  $: snapshot = monitor?.snapshot;
  $: observables = monitor?.observables || [];
  $: metrics = monitor?.metrics || {};
  $: metricHistory = monitor?.metricHistory || [];
  $: events = monitor?.events || [];
  $: importantEvents = events
    .filter((event) => ["error", "failed", "warning"].includes(event.level))
    .slice(0, 6);
  $: debugPayload = monitor
    ? {
        cursor,
        polling,
        followLatest,
        playbackIndex,
        playbackCount,
        taskId: snapshot?.taskId,
        status: snapshot?.status,
        snapshot,
        metrics,
        metricHistory,
        events,
        streamStatus,
        failedEventSamples: debugInfo.failedEvents,
      }
    : {};
  $: visibleMetricMeta = observables.filter((metric) =>
    pinnedMetrics.includes(metric.key),
  );
  $: progressPercent = snapshot
    ? Math.min(100, Math.round(snapshot.progress * 100))
    : 0;
  $: timelinePercent =
    playbackCount > 1
      ? Math.round((playbackIndex / Math.max(1, playbackCount - 1)) * 100)
      : progressPercent;

  $: isRealTask = Boolean(taskId);

  $: if (mounted && taskId !== loadedTaskId) {
    loadedTaskId = taskId;
    cursor = 0;
    selectedEntity = null;
    monitor = null;
    playbackIndex = 0;
    playbackCount = 0;
    followLatest = true;
    stopPlayback();
    debugInfo = { failedEvents: [], count: 0 };
    debugLoadedFor = null;
    debugLoadError = null;
    pinnedMetrics = getDefaultPinnedMetrics("energy");
    stopStream();
    loadNext(0).then(() => startStream());
  }

  $: if (
    mounted &&
    isRealTask &&
    activeMonitorMode === "debug" &&
    taskId &&
    debugLoadedFor !== taskId
  ) {
    loadDebugInfo();
  }

  async function loadNext(nextCursor = cursor, requestedHistoryIndex = followLatest ? null : playbackIndex) {
    try {
      loadError = null;
      const previousEvents = monitor?.events || [];
      const nextMonitor = isRealTask
        ? await getMonitorSnapshot(taskId, nextCursor, pinnedMetrics, requestedHistoryIndex)
        : await getMockMonitorSnapshot(selectedRun, nextCursor, pinnedMetrics);
      cursor = nextMonitor.cursor;
      playbackCount = nextMonitor.playback?.count || 0;
      playbackIndex = nextMonitor.playback?.index ?? playbackIndex;
      monitor = {
        ...nextMonitor,
        events: isRealTask
          ? mergeEvents(previousEvents, nextMonitor.events || [])
          : nextMonitor.events || [],
      };
      if (!pinnedMetrics.length && nextMonitor.snapshot?.domain) {
        pinnedMetrics = getDefaultPinnedMetrics(nextMonitor.snapshot.domain);
      }
      if (
        selectedEntity &&
        monitor.entities.length &&
        !monitor.entities.some((entity) => entity.id === selectedEntity.id)
      ) {
        selectedEntity = null;
      }
    } catch (error) {
      loadError = error.message;
    }
  }

  function mergeEvents(existing = [], incoming = []) {
    const byId = new Map();
    const withoutId = [];
    for (const event of [...existing, ...incoming]) {
      if (event?.id) {
        byId.set(event.id, event);
      } else if (event) {
        withoutId.push(event);
      }
    }
    return [...withoutId, ...byId.values()].slice(-80);
  }

  function appendStreamEvent(payload) {
    if (!payload?.event) return;
    cursor = Math.max(cursor, payload.cursor || cursor);

    if (!monitor) return;

    monitor = {
      ...monitor,
      cursor,
      events: mergeEvents(monitor.events || [], [payload.event]),
    };
  }

  function startStream() {
    stopStream();
    if (!isRealTask || !taskId || typeof EventSource === "undefined") return;

    streamStatus = "connecting";
    eventSource = new EventSource(
      `/monitor/${encodeURIComponent(taskId)}/stream?cursor=${cursor}`,
    );

    eventSource.addEventListener("ready", () => {
      streamStatus = "live";
    });
    eventSource.addEventListener("heartbeat", () => {
      streamStatus = "live";
    });
    eventSource.addEventListener("structured-event", (message) => {
      try {
        appendStreamEvent(JSON.parse(message.data));
        streamStatus = "live";
      } catch (error) {
        streamStatus = "fallback";
      }
    });
    eventSource.onerror = () => {
      stopStream("fallback");
    };
  }

  function stopStream(nextStatus = "idle") {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    streamStatus = nextStatus;
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(() => {
      if (polling && !isPlaying) loadNext();
    }, 1400);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function maxPlaybackIndex() {
    return Math.max(0, playbackCount - 1);
  }

  function loadPlaybackIndex(index) {
    if (!isRealTask || playbackCount <= 0) return;
    const nextIndex = Math.max(0, Math.min(Number(index), maxPlaybackIndex()));
    followLatest = false;
    playbackIndex = nextIndex;
    loadNext(cursor, nextIndex);
  }

  function scrubPlayback(event) {
    stopPlayback();
    loadPlaybackIndex(event.currentTarget.value);
  }

  function stepPlayback(delta) {
    stopPlayback();
    loadPlaybackIndex(playbackIndex + delta);
  }

  function showLatest() {
    stopPlayback();
    followLatest = true;
    loadNext(cursor, null);
  }

  function startPlayback() {
    if (!isRealTask || playbackCount <= 1) return;
    followLatest = false;
    isPlaying = true;
    if (playbackIndex >= maxPlaybackIndex()) {
      playbackIndex = 0;
      loadNext(cursor, playbackIndex);
    }
    if (playbackTimer) clearInterval(playbackTimer);
    playbackTimer = setInterval(() => {
      if (playbackIndex >= maxPlaybackIndex()) {
        stopPlayback();
        return;
      }
      const nextIndex = playbackIndex + 1;
      playbackIndex = nextIndex;
      loadNext(cursor, nextIndex);
    }, 700);
  }

  function stopPlayback() {
    if (playbackTimer) {
      clearInterval(playbackTimer);
      playbackTimer = null;
    }
    isPlaying = false;
  }

  function togglePlayback() {
    if (isPlaying) {
      stopPlayback();
    } else {
      startPlayback();
    }
  }

  async function loadDebugInfo() {
    debugLoadedFor = taskId;
    debugLoadError = null;
    try {
      debugInfo = await getMonitorDebug(taskId);
    } catch (error) {
      debugLoadError = error.message;
      debugInfo = { failedEvents: [], count: 0 };
    }
  }

  function selectRun(runKey) {
    if (isRealTask) return;
    selectedRun = runKey;
    cursor = 0;
    selectedEntity = null;
    followLatest = true;
    stopPlayback();
    pinnedMetrics = getDefaultPinnedMetrics(runKey);
    loadNext(0);
  }

  function toggleMetric(key) {
    if (pinnedMetrics.includes(key)) {
      pinnedMetrics = pinnedMetrics.filter((metricKey) => metricKey !== key);
    } else {
      pinnedMetrics = [...pinnedMetrics, key];
    }
  }

  function formatMetric(value, unit) {
    if (typeof value === "boolean") return value ? "yes" : "no";
    if (value === undefined || value === null) return "n/a";
    return `${value}${unit ? ` ${unit}` : ""}`;
  }

  function metricTrend(key) {
    if (metricHistory.length < 2) return "flat";
    const first = metricHistory[0].values[key];
    const last = metricHistory[metricHistory.length - 1].values[key];
    if (typeof first !== "number" || typeof last !== "number") return "flat";
    if (last > first) return "up";
    if (last < first) return "down";
    return "flat";
  }

  function sparklinePoints(key) {
    const values = metricHistory
      .map((point) => point.values[key])
      .filter((value) => typeof value === "number");
    if (values.length === 0) return "";
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    return values
      .map((value, index) => {
        const x = values.length === 1 ? 50 : (index / (values.length - 1)) * 100;
        const y = 36 - ((value - min) / span) * 30;
        return `${x},${y}`;
      })
      .join(" ");
  }

  function nodeColor(voltage) {
    if (voltage < 0.98) return "#f59e0b";
    if (voltage > 1.035) return "#8b5cf6";
    return "#10b981";
  }

  function edgeColor(loading) {
    if (loading > 85) return "#ef4444";
    if (loading > 70) return "#f59e0b";
    return "#499FAE";
  }

  function findNode(id) {
    return monitor?.network?.nodes?.find((node) => node.id === id);
  }

  function formatTime(seconds) {
    return `${seconds}s`;
  }

  function formatEventSource(event) {
    const category = event.category || "PROGRESS";
    const component = event.component || event.source || "SimService";
    return `[${category}][${component}]`;
  }

  function formatFailedEventTitle(sample) {
    return sample.reason || sample.error || "Event validation failed";
  }

  onMount(() => {
    mounted = true;
    loadedTaskId = taskId;
    loadNext(0).then(() => startStream());
    startPolling();
  });

  onDestroy(() => {
    stopPolling();
    stopPlayback();
    stopStream();
  });
</script>

<div class="run-monitor">
  <div class="monitor-toolbar">
    <div>
      <h2>Run Monitor</h2>
      <p>{isRealTask ? "Task-specific simulation telemetry." : "Frontend telemetry prototype with mock polling snapshots."}</p>
    </div>
    <div class="toolbar-actions">
      {#if !isRealTask}
        <div class="segmented" aria-label="Sample run selector">
          <button
            class:active={selectedRun === "energy"}
            on:click={() => selectRun("energy")}>Energy</button
          >
          <button
            class:active={selectedRun === "traffic"}
            on:click={() => selectRun("traffic")}>Traffic</button
          >
        </div>
      {/if}
      <button class="icon-btn" class:active={polling} on:click={() => (polling = !polling)} title={polling ? "Pause polling" : "Resume polling"}>
        {polling ? "Pause" : "Resume"}
      </button>
    </div>
  </div>

  {#if loadError}
    <div class="loading-state error-state">
      {loadError}
    </div>
  {:else if snapshot}
    <section class="run-header">
      <div class="run-title">
        <span class="domain-badge {snapshot.domain}">{snapshot.domain}</span>
        <div>
          <h3>{snapshot.title}</h3>
          <span>{snapshot.scenarioId || snapshot.taskId}</span>
        </div>
      </div>
      <div class="header-stat">
        <span>Status</span>
        <strong class="status {snapshot.status.toLowerCase()}">{snapshot.status}</strong>
      </div>
      <div class="header-stat">
        <span>Task</span>
        <strong>{snapshot.taskId}</strong>
      </div>
      <div class="header-stat">
        <span>Sim time</span>
        <strong>{formatTime(snapshot.simulationTime)}</strong>
      </div>
      <div class="header-stat">
        <span>Updated</span>
        <strong>{new Date(snapshot.updatedAt).toLocaleTimeString()}</strong>
      </div>
    </section>

    <section class="timeline-panel">
      <div class="timeline-meta">
        <span>{formatTime(snapshot.simulationStart)}</span>
        <strong>{progressPercent}% · step {playbackCount ? playbackIndex + 1 : 0}/{playbackCount || 0}</strong>
        <span>{formatTime(snapshot.simulationEnd)}</span>
      </div>
      <div class="playback-controls">
        <button class="icon-btn" on:click={() => stepPlayback(-1)} disabled={!isRealTask || playbackIndex <= 0}>Back</button>
        <button class="icon-btn" class:active={isPlaying} on:click={togglePlayback} disabled={!isRealTask || playbackCount <= 1}>
          {isPlaying ? "Pause" : "Play"}
        </button>
        <button class="icon-btn" on:click={() => stepPlayback(1)} disabled={!isRealTask || playbackIndex >= maxPlaybackIndex()}>Forward</button>
        <button class="icon-btn" class:active={followLatest} on:click={showLatest} disabled={!isRealTask || playbackCount <= 0}>Latest</button>
      </div>
      <label class="timeline-track">
        <div class="timeline-fill" style={`width: ${timelinePercent}%`}></div>
        <div class="timeline-cursor" style={`left: ${timelinePercent}%`}></div>
        <input
          type="range"
          min="0"
          max={maxPlaybackIndex()}
          value={playbackIndex}
          disabled={!isRealTask || playbackCount <= 1}
          aria-label="Inspect simulation timestep"
          on:input={scrubPlayback}
        />
      </label>
    </section>

    <div class="mode-tabs" role="tablist" aria-label="Run monitor mode">
      <button
        role="tab"
        aria-selected={activeMonitorMode === "normal"}
        class:active={activeMonitorMode === "normal"}
        on:click={() => (activeMonitorMode = "normal")}
      >
        Normal
      </button>
      <button
        role="tab"
        aria-selected={activeMonitorMode === "debug"}
        class:active={activeMonitorMode === "debug"}
        on:click={() => (activeMonitorMode = "debug")}
      >
        Debug
      </button>
    </div>

    {#if activeMonitorMode === "normal"}
      <div class="monitor-grid">
        <section class="visual-panel">
          <div class="panel-head">
            <h3>{snapshot.domain === "energy" ? "Network State" : "Projected Vehicle State"}</h3>
            <span>{snapshot.domain === "energy" ? "voltage and loading encoded" : `${monitor.entities.length} tracked vehicles`}</span>
          </div>

          {#if snapshot.domain === "energy"}
            <svg class="network-view" viewBox="0 0 100 100" role="img" aria-label="Energy network topology">
              {#each monitor.network.edges || [] as edge}
                {@const from = findNode(edge.from)}
                {@const to = findNode(edge.to)}
                {#if from && to}
	                  <line
	                    x1={from.x}
	                    y1={from.y}
	                    x2={to.x}
	                    y2={to.y}
	                    stroke={edgeColor(edge.loading)}
	                    stroke-dasharray={edge.kind === "trafo" ? "2 2" : null}
	                    stroke-width="1.8"
	                    stroke-linecap="round"
	                  />
                {/if}
              {/each}
              {#each monitor.network.nodes || [] as node}
                <g>
                  <circle cx={node.x} cy={node.y} r="4.8" fill={nodeColor(node.voltage)} />
                  <text x={node.x} y={node.y - 7}>{node.label}</text>
                </g>
              {/each}
            </svg>
            <div class="legend-row">
              <span><i class="ok"></i> nominal</span>
              <span><i class="warn"></i> warning</span>
              <span><i class="bad"></i> threshold</span>
            </div>
          {:else}
            <svg class="traffic-view" viewBox="0 0 100 100" role="img" aria-label="Traffic vehicle projection">
              {#each monitor.network.roads || [] as road}
                <polyline
                  points={road.points.map((point) => point.join(",")).join(" ")}
                  fill="none"
                  stroke="#cbd5e1"
                  stroke-width="2.2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              {/each}
              {#each monitor.entities as entity}
                <circle
                  class:selected={selectedEntity?.id === entity.id}
                  class:slow={entity.status === "slow"}
                  cx={entity.x}
                  cy={entity.y}
                  r={selectedEntity?.id === entity.id ? 2.8 : 2}
                  role="button"
                  tabindex="0"
                  aria-label={`Inspect ${entity.id}`}
                  on:click={() => (selectedEntity = entity)}
                  on:keydown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      selectedEntity = entity;
                    }
                  }}
                />
              {/each}
            </svg>
            <div class="entity-detail">
              {#if selectedEntity}
                <strong>{selectedEntity.id}</strong>
                <span>{selectedEntity.edge}</span>
                <span>{selectedEntity.speed} m/s</span>
                <span class:selected-status={selectedEntity.status === "slow"}>{selectedEntity.status}</span>
              {:else}
                <span>Select a vehicle dot to inspect speed and edge.</span>
              {/if}
            </div>
          {/if}
        </section>

        <aside class="metrics-panel">
          <div class="panel-head">
            <h3>Pinned Metrics</h3>
            <span>{visibleMetricMeta.length} selected</span>
          </div>
          <div class="metric-cards">
            {#each visibleMetricMeta as metric}
              <div class="metric-card">
                <span>{metric.label}</span>
                <strong>{formatMetric(metrics[metric.key], metric.unit)}</strong>
                <em class={metricTrend(metric.key)}>{metricTrend(metric.key)}</em>
              </div>
            {/each}
          </div>

          <div class="picker">
            <h4>Monitor</h4>
            {#each observables as metric}
              <label>
                <input
                  type="checkbox"
                  checked={pinnedMetrics.includes(metric.key)}
                  on:change={() => toggleMetric(metric.key)}
                />
                <span>{metric.label}</span>
              </label>
            {/each}
          </div>
        </aside>
      </div>

      <div class="lower-grid">
        <section class="chart-panel">
          <div class="panel-head">
            <h3>Metric History</h3>
            <span>last {metricHistory.length} snapshots</span>
          </div>
          <div class="chart-list">
            {#each visibleMetricMeta.filter((metric) => typeof metrics[metric.key] === "number") as metric}
              <div class="chart-row">
                <div class="chart-label">
                  <strong>{metric.label}</strong>
                  <span>{formatMetric(metrics[metric.key], metric.unit)}</span>
                </div>
                <svg viewBox="0 0 100 40" preserveAspectRatio="none">
                  <polyline points={sparklinePoints(metric.key)} />
                </svg>
              </div>
            {/each}
          </div>
        </section>

        <section class="events-panel">
          <div class="panel-head">
            <h3>Recent Alerts</h3>
            <span>{importantEvents.length || "no"} warnings or errors</span>
          </div>
          <div class="event-list">
            {#each importantEvents as event}
              <div class="event-item {event.level}">
                <span class="event-time">{formatTime(event.time)}</span>
                <span class="event-source">{formatEventSource(event)}</span>
                <span class="event-message">{event.message}</span>
              </div>
            {:else}
              <div class="empty-state">No warning or error events in the current polling window.</div>
            {/each}
          </div>
        </section>
      </div>
    {:else}
      <div class="debug-grid">
        <section class="events-panel debug-events">
          <div class="panel-head">
            <h3>Structured Events</h3>
            <span>{events.length} visible · cursor {cursor}</span>
          </div>
          <div class="event-list">
            {#each events as event}
              <div class="event-item {event.level}">
                <span class="event-time">{formatTime(event.time)}</span>
                <span class="event-source">{formatEventSource(event)}</span>
                <span class="event-message">{event.message}</span>
              </div>
            {:else}
              <div class="empty-state">No structured events loaded yet.</div>
            {/each}
          </div>

          <div class="failed-events">
            <div class="panel-head compact">
              <h3>Failed Event Samples</h3>
              <span>{debugInfo.count || "no"} quarantined</span>
            </div>
            {#if debugLoadError}
              <div class="empty-state error-state">{debugLoadError}</div>
            {:else if debugInfo.failedEvents.length}
              <div class="failed-event-list">
                {#each debugInfo.failedEvents as sample}
                  <div class="failed-event-item">
                    <strong>{formatFailedEventTitle(sample)}</strong>
                    <span>{sample.received_at ? new Date(sample.received_at).toLocaleTimeString() : "unknown time"}</span>
                    <pre>{JSON.stringify(sample.original_event, null, 2)}</pre>
                  </div>
                {/each}
              </div>
            {:else}
              <div class="empty-state">No malformed events recorded for this task.</div>
            {/if}
          </div>
        </section>

        <section class="debug-panel">
          <div class="panel-head">
            <h3>Raw Monitor Snapshot</h3>
            <span>{polling ? "polling" : "paused"}</span>
          </div>
          <pre>{JSON.stringify(debugPayload, null, 2)}</pre>
        </section>
      </div>
    {/if}
  {:else}
    <div class="loading-state">
      <span class="spinner"></span>
      Loading monitor…
    </div>
  {/if}
</div>

<style>
  .run-monitor {
    height: 100%;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .monitor-toolbar,
  .run-header,
  .timeline-panel,
  .visual-panel,
  .metrics-panel,
  .chart-panel,
  .events-panel,
  .debug-panel {
    background: var(--bg-surface);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-md);
  }

  .monitor-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    gap: 12px;
  }
  .monitor-toolbar h2 {
    margin: 0;
    font-size: 1rem;
    color: var(--text-primary);
  }
  .monitor-toolbar p {
    margin: 2px 0 0;
    color: var(--text-muted);
    font-size: 0.8rem;
  }
  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .segmented {
    display: inline-flex;
    padding: 2px;
    background: var(--bg-inset);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-sm);
  }
  .segmented button,
  .icon-btn {
    border: none;
    background: transparent;
    color: var(--text-secondary);
    font-size: 0.78rem;
    font-weight: 700;
    padding: 6px 10px;
    border-radius: 5px;
    cursor: pointer;
  }
  .segmented button.active,
  .icon-btn.active {
    background: var(--brand-primary);
    color: #ffffff;
  }
  .icon-btn {
    border: 1px solid var(--border-light);
    background: var(--bg-surface);
  }
  .icon-btn:disabled {
    cursor: not-allowed;
    opacity: 0.45;
  }

  .run-header {
    display: grid;
    grid-template-columns: minmax(220px, 1.5fr) repeat(4, minmax(120px, 1fr));
    gap: 10px;
    padding: 12px 14px;
    align-items: center;
  }
  .run-title {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .run-title h3 {
    margin: 0;
    font-size: 0.95rem;
    color: var(--text-primary);
  }
  .run-title span:last-child,
  .header-stat span {
    color: var(--text-muted);
    font-size: 0.72rem;
  }
  .domain-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 60px;
    padding: 4px 8px;
    border-radius: 12px;
    font-size: 0.68rem;
    font-weight: 800;
    text-transform: uppercase;
  }
  .domain-badge.energy {
    background: #ecfdf5;
    color: #065f46;
  }
  .domain-badge.traffic {
    background: #dbeafe;
    color: #1e40af;
  }
  .header-stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .header-stat strong {
    color: var(--text-primary);
    font-size: 0.82rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status {
    width: fit-content;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.7rem !important;
  }
  .status.pending {
    background: #fef3c7;
    color: #92400e;
  }
  .status.running {
    background: #dbeafe;
    color: #1e40af;
  }
  .status.done {
    background: #d1fae5;
    color: #065f46;
  }
  .status.error,
  .status.failed {
    background: #fee2e2;
    color: #991b1b;
  }

  .timeline-panel {
    padding: 10px 14px 12px;
  }
  .timeline-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    font-size: 0.76rem;
    color: var(--text-muted);
  }
  .timeline-meta strong {
    color: var(--brand-primary);
  }
  .playback-controls {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 10px;
  }
  .timeline-track {
    position: relative;
    height: 8px;
    background: var(--bg-inset);
    border-radius: 999px;
    overflow: visible;
    display: block;
  }
  .timeline-fill {
    height: 100%;
    background: var(--brand-primary);
    border-radius: inherit;
    pointer-events: none;
  }
  .timeline-cursor {
    position: absolute;
    top: 50%;
    width: 14px;
    height: 14px;
    border: 2px solid #ffffff;
    background: var(--brand-primary);
    border-radius: 50%;
    transform: translate(-50%, -50%);
    box-shadow: var(--shadow-sm);
    pointer-events: none;
  }
  .timeline-track input[type="range"] {
    position: absolute;
    inset: -9px 0;
    width: 100%;
    opacity: 0;
    cursor: pointer;
  }
  .timeline-track input[type="range"]:disabled {
    cursor: not-allowed;
  }

  .mode-tabs {
    display: inline-flex;
    width: fit-content;
    padding: 2px;
    background: var(--bg-inset);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-sm);
  }
  .mode-tabs button {
    border: none;
    background: transparent;
    color: var(--text-secondary);
    font-size: 0.78rem;
    font-weight: 800;
    padding: 7px 14px;
    border-radius: 5px;
    cursor: pointer;
  }
  .mode-tabs button.active {
    background: var(--brand-primary);
    color: #ffffff;
  }

  .monitor-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.7fr) minmax(260px, 0.8fr);
    gap: 14px;
    min-height: 360px;
  }
  .visual-panel,
  .metrics-panel,
  .chart-panel,
  .events-panel,
  .debug-panel {
    padding: 12px;
    min-width: 0;
  }
  .panel-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
  }
  .panel-head h3 {
    margin: 0;
    font-size: 0.86rem;
    color: var(--text-secondary);
  }
  .panel-head span {
    color: var(--text-muted);
    font-size: 0.72rem;
  }

  .network-view,
  .traffic-view {
    width: 100%;
    height: 284px;
    background:
      linear-gradient(var(--border-light) 1px, transparent 1px),
      linear-gradient(90deg, var(--border-light) 1px, transparent 1px);
    background-size: 24px 24px;
    border: 1px solid var(--border-light);
    border-radius: var(--radius-md);
  }
  .network-view text {
    font-size: 3px;
    font-weight: 700;
    text-anchor: middle;
    fill: var(--text-secondary);
  }
  .traffic-view circle {
    fill: var(--brand-primary);
    stroke: #ffffff;
    stroke-width: 0.7;
    cursor: pointer;
  }
  .traffic-view circle.slow {
    fill: var(--status-pending);
  }
  .traffic-view circle.selected {
    fill: var(--status-error);
  }

  .legend-row,
  .entity-detail {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 8px;
    color: var(--text-muted);
    font-size: 0.75rem;
    flex-wrap: wrap;
  }
  .legend-row i {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 4px;
  }
  .legend-row .ok {
    background: var(--status-done);
  }
  .legend-row .warn {
    background: var(--status-pending);
  }
  .legend-row .bad {
    background: var(--status-error);
  }
  .entity-detail strong {
    color: var(--text-primary);
  }
  .selected-status {
    color: var(--status-pending);
    font-weight: 700;
  }

  .metrics-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .metric-cards {
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
  }
  .metric-card {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 4px 8px;
    padding: 10px;
    background: var(--bg-inset);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-sm);
  }
  .metric-card span {
    color: var(--text-muted);
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
  }
  .metric-card strong {
    grid-column: 1 / 2;
    color: var(--text-primary);
    font-size: 1.05rem;
  }
  .metric-card em {
    grid-row: 1 / 3;
    grid-column: 2 / 3;
    align-self: center;
    font-size: 0.7rem;
    font-style: normal;
    font-weight: 800;
    text-transform: uppercase;
    color: var(--text-muted);
  }
  .metric-card em.up {
    color: var(--status-error);
  }
  .metric-card em.down {
    color: var(--status-done);
  }

  .picker {
    padding-top: 10px;
    border-top: 1px solid var(--border-light);
    display: flex;
    flex-direction: column;
    gap: 7px;
  }
  .picker h4 {
    margin: 0 0 2px;
    font-size: 0.78rem;
    color: var(--text-secondary);
  }
  .picker label {
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 0.8rem;
    color: var(--text-secondary);
    cursor: pointer;
  }
  .picker input {
    accent-color: var(--brand-primary);
  }

  .lower-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
    gap: 14px;
  }
  .debug-grid {
    display: grid;
    grid-template-columns: minmax(360px, 0.9fr) minmax(0, 1.1fr);
    gap: 14px;
    min-height: 420px;
  }
  .debug-events .event-list {
    max-height: 520px;
    overflow-y: auto;
    padding-right: 2px;
  }
  .failed-events {
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--border-light);
  }
  .panel-head.compact {
    margin-bottom: 8px;
  }
  .failed-event-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    max-height: 360px;
    overflow-y: auto;
    padding-right: 2px;
  }
  .failed-event-item {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 6px 10px;
    padding: 10px;
    background: var(--bg-inset);
    border-left: 3px solid var(--status-error);
    border-radius: var(--radius-sm);
  }
  .failed-event-item strong {
    color: var(--text-primary);
    font-size: 0.78rem;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .failed-event-item span {
    color: var(--text-muted);
    font-size: 0.72rem;
    font-weight: 700;
  }
  .failed-event-item pre {
    grid-column: 1 / -1;
    max-height: 150px;
    overflow: auto;
    margin: 0;
    color: var(--text-secondary);
    font-size: 0.72rem;
    line-height: 1.4;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .debug-panel {
    display: flex;
    flex-direction: column;
  }
  .debug-panel pre {
    flex: 1;
    min-height: 360px;
    max-height: 620px;
    overflow: auto;
    margin: 0;
    padding: 12px;
    background: var(--bg-inset);
    border: 1px solid var(--border-light);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    font-size: 0.72rem;
    line-height: 1.45;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .chart-list,
  .event-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .chart-row {
    display: grid;
    grid-template-columns: 170px minmax(0, 1fr);
    align-items: center;
    gap: 10px;
    padding: 8px;
    background: var(--bg-inset);
    border-radius: var(--radius-sm);
  }
  .chart-label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .chart-label strong {
    color: var(--text-primary);
    font-size: 0.78rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .chart-label span {
    color: var(--text-muted);
    font-size: 0.72rem;
  }
  .chart-row svg {
    width: 100%;
    height: 42px;
  }
  .chart-row polyline {
    fill: none;
    stroke: var(--brand-primary);
    stroke-width: 2;
    vector-effect: non-scaling-stroke;
  }

  .event-item {
    display: grid;
    grid-template-columns: 56px minmax(150px, 220px) minmax(0, 1fr);
    gap: 8px;
    align-items: center;
    padding: 8px 10px;
    background: var(--bg-inset);
    border-left: 3px solid var(--brand-primary);
    border-radius: var(--radius-sm);
    font-size: 0.78rem;
  }
  .event-item.warning {
    border-left-color: var(--status-pending);
  }
  .event-item.error {
    border-left-color: var(--status-error);
  }
  .event-time,
  .event-source {
    color: var(--text-muted);
    font-weight: 700;
  }
  .event-source {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .event-message {
    color: var(--text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .empty-state {
    padding: 14px;
    background: var(--bg-inset);
    border: 1px dashed var(--border-light);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 0.8rem;
  }

  .loading-state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: var(--text-muted);
  }
  .error-state {
    color: var(--status-error);
  }
  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid var(--border-light);
    border-radius: 50%;
    border-top-color: var(--brand-primary);
    animation: spin 0.7s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  @media (max-width: 980px) {
    .run-header,
    .monitor-grid,
    .lower-grid,
    .debug-grid {
      grid-template-columns: 1fr;
    }
    .chart-row,
    .event-item {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 640px) {
    .monitor-toolbar {
      align-items: stretch;
      flex-direction: column;
    }
    .toolbar-actions {
      justify-content: flex-start;
    }
  }
</style>
