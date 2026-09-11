<script>
  import { createEventDispatcher } from 'svelte';
  import { onMount } from 'svelte';

  const dispatch = createEventDispatcher();

  let tasks = [];
  let loading = true;
  let error = null;
  let expandedTask = null;
  let taskDetails = {}; // taskId -> detailed check result

  onMount(() => fetchTasks());

  async function fetchTasks() {
    loading = true;
    error = null;
    try {
      let cursor = 0;
      let data;
      const loaded = new Map();
      do {
        const resp = await fetch(`/my-tasks?cursor=${cursor}`);
        if (!resp.ok) throw new Error('Failed to load tasks');
        data = await resp.json();
        for (const task of data.tasks || []) loaded.set(task.task_id, task);
        if (data.hasMore && data.cursor <= cursor) throw new Error('History pagination did not advance');
        cursor = data.cursor;
      } while (data.hasMore);
      tasks = [...loaded.values()];
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  async function toggleExpand(taskId) {
    if (expandedTask === taskId) {
      expandedTask = null;
      return;
    }
    expandedTask = taskId;
    // Fetch full details if not cached
    if (!taskDetails[taskId]) {
      try {
        const resp = await fetch(`/check/${taskId}`);
        if (resp.ok) {
          taskDetails[taskId] = await resp.json();
          taskDetails = { ...taskDetails }; // trigger reactivity
        }
      } catch (e) { /* ignore */ }
    }
  }

  function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
      + ' ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  }

  function truncateId(id) {
    if (!id) return '—';
    return id.substring(0, 8) + '…';
  }

  function openMonitor(taskId) {
    dispatch('openMonitor', { taskId });
  }
</script>

<div class="history">
  <div class="history-header">
    <h3>Simulation History</h3>
    <button class="refresh-btn" on:click={fetchTasks} disabled={loading}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class:spinning={loading}>
        <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
      </svg>
      Refresh
    </button>
  </div>

  {#if loading && tasks.length === 0}
    <div class="center-msg">
      <span class="spinner"></span> Loading history…
    </div>
  {:else if error}
    <div class="center-msg error-msg">⚠ {error}</div>
  {:else if tasks.length === 0}
    <div class="center-msg">No simulations submitted yet.</div>
  {:else}
    <div class="table-wrap">
      <table class="history-table">
        <thead>
          <tr>
            <th>Scenario</th>
            <th>Task ID</th>
            <th>Submitted</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each tasks as task}
            <tr class="task-row" class:expanded={expandedTask === task.task_id} on:click={() => toggleExpand(task.task_id)}>
              <td class="cell-scenario">{task.scenario_id || '—'}</td>
              <td class="cell-id"><code>{truncateId(task.task_id)}</code></td>
              <td class="cell-date">{formatDate(task.created_at)}</td>
              <td><span class="status-badge {task.status.toLowerCase()}">{task.status}</span></td>
              <td class="cell-chevron">{expandedTask === task.task_id ? '▾' : '▸'}</td>
            </tr>
            {#if expandedTask === task.task_id}
              <tr class="detail-row">
                <td colspan="5">
                  <div class="detail-content">
                    <div class="detail-field">
                      <span class="detail-label">Full Task ID</span>
                      <code class="detail-value">{task.task_id}</code>
                    </div>
                    {#if taskDetails[task.task_id]}
                      {#if taskDetails[task.task_id].downloads?.length}
                        <div class="detail-field">
                          <span class="detail-label">Result Files</span>
                          <div class="file-links">
                            {#each taskDetails[task.task_id].downloads as url, i}
                              <a href={url} class="file-link" download on:click|stopPropagation>📄 {taskDetails[task.task_id].files[i]}</a>
                            {/each}
                          </div>
                        </div>
                      {/if}
                      {#if taskDetails[task.task_id].status === 'ERROR' && taskDetails[task.task_id].error}
                        <div class="detail-field error-detail">
                          <span class="detail-label">Error</span>
                          <span class="detail-value">{taskDetails[task.task_id].error}</span>
                        </div>
                      {/if}
                      <button class="monitor-link" on:click|stopPropagation={() => openMonitor(task.task_id)}>
                        Open Monitor
                      </button>
                    {:else}
                      <span class="loading-detail">Loading details…</span>
                    {/if}
                  </div>
                </td>
              </tr>
            {/if}
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

<style>
  .history { display: flex; flex-direction: column; height: 100%; padding: 16px; }

  .history-header {
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 14px;
  }
  .history-header h3 { margin: 0; font-size: 0.95rem; font-weight: 700; color: var(--text-primary); }

  .refresh-btn {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 6px 12px; border: 1px solid var(--border-light);
    border-radius: var(--radius-sm); background: var(--bg-surface);
    font-size: 0.78rem; font-weight: 600; color: var(--text-secondary);
    cursor: pointer; transition: all var(--transition-fast);
  }
  .refresh-btn svg { width: 14px; height: 14px; }
  .refresh-btn:hover { border-color: var(--brand-primary); color: var(--brand-primary); }
  .refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .spinning { animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .center-msg {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    padding: 40px; color: var(--text-muted); font-size: 0.9rem;
  }
  .error-msg { color: var(--status-error); }

  .spinner {
    width: 16px; height: 16px;
    border: 2px solid var(--border-light); border-radius: 50%;
    border-top-color: var(--brand-primary); animation: spin 0.7s linear infinite;
  }

  /* Table */
  .table-wrap {
    flex: 1; overflow-y: auto;
    border: 1px solid var(--border-light); border-radius: var(--radius-md);
    background: var(--bg-surface);
  }

  .history-table {
    width: 100%; border-collapse: collapse; font-size: 0.84rem;
  }

  thead th {
    padding: 10px 14px; text-align: left;
    font-size: 0.72rem; font-weight: 700; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 0.05em;
    background: var(--bg-inset); border-bottom: 1px solid var(--border-light);
    position: sticky; top: 0; z-index: 1;
  }

  .task-row {
    cursor: pointer; transition: background var(--transition-fast);
  }
  .task-row:hover { background: var(--bg-surface-hover); }
  .task-row.expanded { background: var(--bg-inset); }
  .task-row td {
    padding: 10px 14px; border-bottom: 1px solid var(--border-light);
  }

  .cell-scenario { font-weight: 600; color: var(--text-primary); }
  .cell-id code {
    font-size: 0.78rem; background: var(--bg-inset); padding: 2px 6px;
    border-radius: 4px; color: var(--text-secondary);
  }
  .cell-date { color: var(--text-muted); font-size: 0.8rem; }
  .cell-chevron { color: var(--text-muted); font-size: 0.7rem; width: 24px; text-align: center; }

  .status-badge {
    display: inline-block; padding: 3px 10px; border-radius: 10px;
    font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
  }
  .status-badge.pending { background: #fef3c7; color: #92400e; }
  .status-badge.running { background: #dbeafe; color: #1e40af; }
  .status-badge.done { background: #d1fae5; color: #065f46; }
  .status-badge.error { background: #fee2e2; color: #991b1b; }
  .status-badge.unknown { background: var(--bg-inset); color: var(--text-muted); }

  /* Detail row */
  .detail-row td {
    padding: 0; border-bottom: 1px solid var(--border-light);
  }
  .detail-content {
    padding: 12px 14px; background: var(--bg-inset);
    display: flex; flex-direction: column; gap: 8px;
  }
  .detail-field { display: flex; flex-direction: column; gap: 2px; }
  .detail-label { font-size: 0.7rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase; }
  .detail-value { font-size: 0.82rem; color: var(--text-primary); }
  .detail-value code, .detail-content code { font-size: 0.78rem; word-break: break-all; }
  .error-detail .detail-value { color: var(--status-error); }
  .loading-detail { font-size: 0.82rem; color: var(--text-muted); }

  .file-links { display: flex; flex-direction: column; gap: 2px; }
  .file-link {
    font-size: 0.82rem; color: var(--brand-primary); text-decoration: none;
  }
  .file-link:hover { text-decoration: underline; }
  .monitor-link {
    align-self: flex-start;
    margin-top: 4px;
    border: 1px solid var(--border-light);
    background: var(--bg-surface);
    color: var(--brand-primary);
    border-radius: var(--radius-sm);
    padding: 6px 10px;
    font-size: 0.78rem;
    font-weight: 700;
    cursor: pointer;
  }
  .monitor-link:hover {
    border-color: var(--brand-primary);
  }
</style>
