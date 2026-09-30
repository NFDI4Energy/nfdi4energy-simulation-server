<script>
  import { onMount, onDestroy } from 'svelte';
  import { submitMosaik, listMosaikTasks, pollMosaikTask, resultUrl } from './mosaikClient.js';
  export let user;
  export let onSwitchFramework = () => {};
  export let onLogout = () => {};
  const guiUrl = 'http://localhost:8002';
  let view = 'new';
  let file = null;
  let submitting = false;
  let message = '';
  let tasks = [];
  let cursor = 0;
  let hasMore = false;
  let count = 0;
  let loading = false;
  let historyError = '';
  let selectedId = null;
  let task = null;
  let taskError = '';
  let refreshing = false;
  let stopPolling = () => {};
  let historyController;
  const submitController = new AbortController();
  $: enabled = Boolean(user.capabilities?.mosaikSubmissionEnabled);

  function authError(error) {
    if (error.status === 401) { window.location.href = '/auth/login'; return true; }
    return false;
  }

  async function loadHistory(more = false) {
    historyController?.abort();
    const controller = new AbortController();
    historyController = controller;
    loading = true;
    historyError = '';
    try {
      const page = await listMosaikTasks(more ? cursor : 0, controller.signal);
      if (controller.signal.aborted) return;
      const merged = more ? [...tasks, ...page.tasks] : page.tasks;
      tasks = [...new Map(merged.map(row => [row.task_id, row])).values()];
      cursor = page.cursor;
      hasMore = page.hasMore;
      count = page.count;
    } catch (error) {
      if (!controller.signal.aborted && !authError(error)) historyError = 'Could not load runs. Please refresh.';
    } finally {
      if (!controller.signal.aborted) loading = false;
    }
  }

  function inspect(taskId) {
    stopPolling();
    selectedId = taskId;
    task = null;
    taskError = '';
    refreshing = true;
    view = 'history';
    stopPolling = pollMosaikTask(taskId, value => {
      task = value;
      refreshing = false;
      taskError = '';
      tasks = tasks.map(row => row.task_id === taskId ? { ...row, status: value.status } : row);
    }, (error, retry) => {
      if (authError(error)) return;
      refreshing = retry;
      taskError = error.status === 404 ? 'Run is unavailable.' : retry ? 'Connection interrupted. Retrying...' : 'Could not refresh run. Please try again.';
    });
  }

  function switchView(next) {
    stopPolling();
    view = next;
    selectedId = null;
    task = null;
    if (next === 'history') loadHistory();
    else historyController?.abort();
  }

  async function submit() {
    if (!file || submitting || !enabled) return;
    submitting = true;
    message = '';
    try {
      const result = await submitMosaik(file, submitController.signal);
      if (submitController.signal.aborted) return;
      inspect(result.task_id);
      loadHistory();
    } catch (error) {
      if (submitController.signal.aborted || authError(error)) return;
      if (error.taskId) {
        inspect(error.taskId);
        loadHistory();
        message = error.code === 'submission_outcome_unknown'
          ? 'Delivery could not be confirmed. Check this run before submitting again.' : error.message;
      } else if (!error.status) {
        message = 'Submission could not be confirmed. Check run history before submitting again.';
      } else message = error.message;
    } finally { submitting = false; }
  }

  function date(value) { return value ? new Date(value).toLocaleString() : '-'; }
  onMount(() => loadHistory());
  onDestroy(() => { stopPolling(); historyController?.abort(); submitController.abort(); });
</script>

<div class="workspace">
  <header>
    <div class="title"><button class="icon" on:click={onSwitchFramework} disabled={submitting} aria-label="Switch framework" title="Switch framework">&larr;</button><h1>Mosaik</h1><span class="engine">Orbit</span></div>
    <button class="quiet" on:click={onLogout}>Sign out</button>
  </header>
  <nav aria-label="Mosaik views">
    <button class:active={view === 'new'} on:click={() => switchView('new')} disabled={submitting}>New run</button>
    <button class:active={view === 'history'} on:click={() => switchView('history')} disabled={submitting}>History <span>{count}</span></button>
  </nav>
  <main>
    {#if message}<p class="notice" role="status">{message}</p>{/if}
    {#if view === 'new'}
      <form on:submit|preventDefault={submit}>
        <div class="section-heading">
          <h2>New run</h2>
          <a class="quiet create-scenario" href={guiUrl} target="_blank" rel="noopener noreferrer" title="Open Mosaik GUI in a new tab">Create scenario <span aria-hidden="true">&#8599;</span></a>
        </div>
        {#if !enabled}<p class="notice">Mosaik submissions are paused.</p>{/if}
        <label for="scenario">Scenario JSON</label>
        <input id="scenario" type="file" accept=".json,application/json" disabled={!enabled || submitting} on:change={event => { file = event.currentTarget.files[0] || null; message = ''; }} />
        <button class="primary" type="submit" disabled={!enabled || !file || submitting}><span aria-hidden="true">&uarr;</span> {submitting ? 'Submitting...' : 'Submit run'}</button>
      </form>
    {:else}
      <div class="history-layout" class:inspecting={selectedId}>
        <section class="runs" aria-label="Run history">
          <div class="section-heading"><h2>Runs <span>{count}</span></h2><button class="icon" title="Refresh history" aria-label="Refresh history" disabled={loading} on:click={() => loadHistory()}>&#8635;</button></div>
          {#if historyError}<p class="error" role="alert">{historyError}</p>{/if}
          {#if !tasks.length}<p class="empty">{loading ? 'Loading runs...' : 'No Mosaik runs yet.'}</p>{/if}
          <div class="run-list">
            {#each tasks as row (row.task_id)}
              <button class="run" class:selected={selectedId === row.task_id} on:click={() => inspect(row.task_id)}>
                <span class="run-id">{row.task_id}</span><span class="status" data-status={row.status}>{row.status}</span><time>{date(row.created_at)}</time>
              </button>
            {/each}
          </div>
          {#if hasMore}<button class="quiet more" disabled={loading} on:click={() => loadHistory(true)}>{loading ? 'Loading...' : 'Load more'}</button>{/if}
        </section>
        {#if selectedId}
          <section class="detail" aria-label="Selected run">
            <div class="section-heading"><h2>Run details</h2><button class="icon" title="Refresh run" aria-label="Refresh run" disabled={refreshing} on:click={() => inspect(selectedId)}>&#8635;</button></div>
            <dl><dt>Task ID</dt><dd class="task-id">{selectedId}</dd><dt>Status</dt><dd><span class="status" data-status={task?.status}>{task?.status || (taskError ? 'Unavailable' : 'Loading...')}</span></dd></dl>
            {#if taskError}<p class="error" role="alert">{taskError}</p>{/if}
            {#if task?.status === 'UNKNOWN'}<p class="notice">Run status is uncertain.</p>{/if}
            {#if task?.error}<p class="error" role="alert">{task.error}</p>{/if}
            {#if task?.redisAvailable === false}<p class="notice">Runtime tracker unavailable.</p>{/if}
            <h3>Results</h3>
            {#if task?.files?.length}
              <ul class="results">{#each task.files as filename}<li><a href={resultUrl(selectedId, filename)}><span aria-hidden="true">&darr;</span> {filename}</a></li>{/each}</ul>
            {:else}<p class="empty">{task ? 'No result files available.' : 'Awaiting run details.'}</p>{/if}
          </section>
        {/if}
      </div>
    {/if}
  </main>
</div>

<style>
  .workspace { height: 100%; display: flex; flex-direction: column; background: var(--bg-page); letter-spacing: 0; }
  header { padding: 12px 24px; min-height: 64px; display: flex; justify-content: space-between; align-items: center; background: white; gap: 12px; border-bottom: 1px solid var(--border-light); }
  .title, .section-heading { display: flex; align-items: center; gap: 12px; }
  .section-heading { justify-content: space-between; margin-bottom: 16px; }
  h1 { font-size: 20px; margin: 0; } h2 { font-size: 18px; margin: 0; } h3 { font-size: 15px; margin: 28px 0 12px; }
  .engine, h2 span, nav span { font-size: 13px; color: var(--text-secondary); font-weight: 400; }
  button, input { font: inherit; } button { cursor: pointer; border-radius: 6px; } button:disabled { cursor: not-allowed; opacity: .55; }
  .icon { width: 36px; height: 36px; flex-shrink: 0; border: 1px solid var(--border-mid); background: white; color: var(--brand-primary-hover); font-size: 22px; }
  .quiet { padding: 8px 12px; border: 1px solid var(--border-mid); background: white; color: var(--text-primary); }
  nav { display: flex; gap: 20px; padding: 0 24px; background: white; border-bottom: 1px solid var(--border-light); }
  nav button { padding: 14px 0; border: 0; border-bottom: 2px solid transparent; border-radius: 0; background: transparent; color: var(--text-secondary); font-size: 14px; }
  nav button.active { border-bottom-color: var(--brand-primary); color: var(--brand-primary-hover); }
  main { flex: 1; overflow: auto; padding: 28px 24px; }
  form { max-width: 640px; } form .section-heading { margin-bottom: 24px; flex-wrap: wrap; } label { display: block; font-size: 14px; font-weight: 600; margin-bottom: 8px; }
  .create-scenario { display: inline-flex; align-items: center; gap: 8px; text-decoration: none; border-radius: 6px; }
  input { display: block; padding: 12px; width: 100%; max-width: 100%; min-width: 0; border: 1px solid var(--border-mid); background: white; border-radius: 6px; font-size: 14px; }
  .primary { margin-top: 24px; background: var(--brand-primary-hover); color: white; border: 0; padding: 12px 18px; font-size: 14px; }
  .notice, .error { font-size: 14px; padding: 12px; border-left: 3px solid #b78b22; background: #fff9e8; overflow-wrap: anywhere; white-space: pre-wrap; }
  .error { border-color: #d95151; background: #fff0f0; color: #962d2d; }
  .history-layout { display: grid; gap: 28px; } .history-layout.inspecting { grid-template-columns: minmax(260px, 1fr) minmax(300px, 1fr); }
  .runs, .detail { min-width: 0; } .detail { border-left: 1px solid var(--border-mid); padding-left: 28px; }
  .run-list { border-top: 1px solid var(--border-mid); }
  .run { display: grid; grid-template-columns: 1fr auto; gap: 8px 12px; width: 100%; text-align: left; padding: 16px 12px; border: 0; border-bottom: 1px solid var(--border-mid); border-radius: 0; background: white; color: var(--text-primary); }
  .run:hover, .run.selected { background: #eaf5f6; } .run.selected { box-shadow: inset 3px 0 var(--brand-primary); }
  .run-id, .task-id { font-family: ui-monospace, monospace; font-size: 13px; overflow-wrap: anywhere; min-width: 0; }
  time { color: var(--text-secondary); font-size: 12px; grid-column: 1 / -1; }
  .status { font-size: 12px; font-weight: 600; color: #666; } .status[data-status='DONE'] { color: #147349; } .status[data-status='ERROR'] { color: #b33333; } .status[data-status='RUNNING'] { color: #2666b5; } .status[data-status='PENDING'] { color: #8f6917; }
  dt { font-size: 12px; color: var(--text-secondary); margin-top: 16px; } dd { margin: 4px 0 0; }
  .empty { color: var(--text-secondary); font-size: 14px; } .results { list-style: none; padding: 0; margin: 0; } .results li { border-bottom: 1px solid var(--border-mid); } a { display: block; padding: 12px 0; color: var(--brand-primary-hover); font-size: 14px; overflow-wrap: anywhere; } .more { margin-top: 16px; }
  @media (max-width: 740px) { .history-layout.inspecting { grid-template-columns: minmax(0, 1fr); } .detail { grid-row: 1; padding-left: 0; border-left: 0; border-bottom: 1px solid var(--border-mid); padding-bottom: 24px; } header, main { padding: 16px; } nav { padding: 0 16px; } .engine { display: none; } }
</style>
