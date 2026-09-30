<script>
  import { createEventDispatcher } from 'svelte';
  import ScenarioBBCard from './ScenarioBBCard.svelte';

  const dispatch = createEventDispatcher();

  // Sub-tab state
  let activeSubTab = 'scenario'; // 'scenario' | 'run'

  // Scenario data model
  let scenario = createBlankScenario();

  function createBlankScenario() {
    return {
      scenarioID: '',
      domainReferences: {},
      simulationStart: 0,
      simulationEnd: 1000,
      execution: { randomSeed: 23, syncedParticipants: 1, constraints: '', priority: 0 },
      buildingBlocks: [],
      translators: [],
      projectors: []
    };
  }

  function createBlankBB() {
    return {
      instanceID: '', type: '', layer: 'micro', domain: 'energy',
      stepLength: 1000, parameters: {}, resources: {}, results: {},
      synchronized: true, isExternal: false, responsibilities: [], observers: []
    };
  }

  // Building blocks management
  function addBB() {
    scenario.buildingBlocks = [...scenario.buildingBlocks, createBlankBB()];
  }
  function removeBB(idx) {
    scenario.buildingBlocks = scenario.buildingBlocks.filter((_, i) => i !== idx);
  }

  // JSON preview
  let showJsonPreview = false;
  $: scenarioJson = JSON.stringify(scenario, null, 2);

  // Upload/Export/Reset
  function handleUpload() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        // Merge with defaults to fill missing fields
        scenario = {
          ...createBlankScenario(),
          ...parsed,
          execution: { ...createBlankScenario().execution, ...(parsed.execution || {}) },
          buildingBlocks: (parsed.buildingBlocks || []).map(bb => ({
            ...createBlankBB(), ...bb,
            resources: bb.resources || {},
            parameters: bb.parameters || {},
            results: bb.results || {},
            responsibilities: bb.responsibilities || [],
            observers: bb.observers || []
          }))
        };
      } catch (err) {
        alert('Failed to parse JSON: ' + err.message);
      }
    };
    input.click();
  }

  function handleExport() {
    const blob = new Blob([scenarioJson], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = (scenario.scenarioID || 'scenario') + '.json';
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleReset() {
    if (confirm('Reset scenario to blank template?')) {
      scenario = createBlankScenario();
      resourceFiles = [];
    }
  }

  // Resource files
  let resourceFiles = [];
  function handleResourceUpload(e) {
    const files = Array.from(e.target.files || []);
    // Avoid duplicates by name
    const existing = new Set(resourceFiles.map(f => f.name));
    resourceFiles = [...resourceFiles, ...files.filter(f => !existing.has(f.name))];
  }
  function removeResource(idx) {
    resourceFiles = resourceFiles.filter((_, i) => i !== idx);
  }

  // Resource validation: check scenario references vs uploaded files
  $: referencedFiles = (() => {
    const s = new Set();
    for (const bb of scenario.buildingBlocks) {
      if (bb.resources) Object.keys(bb.resources).forEach(k => s.add(k));
    }
    return s;
  })();
  $: uploadedNames = new Set(resourceFiles.map(f => f.name));
  $: missingResources = [...referencedFiles].filter(f => !uploadedNames.has(f));

  // Run simulation
  let submitting = false;
  let submitResult = null; // { success, taskId, error }
  let taskStatus = null; // polling result
  let pollTimer = null;

  async function handleSubmit() {
    submitting = true;
    submitResult = null;
    taskStatus = null;

    try {
      const formData = new FormData();
      // Add scenario as file
      const scenarioBlob = new Blob([scenarioJson], { type: 'application/json' });
      formData.append('scenario_file', scenarioBlob, (scenario.scenarioID || 'scenario') + '.json');
      // Add resource files
      for (const f of resourceFiles) {
        formData.append('resource_files', f, f.name);
      }

      const resp = await fetch('/submit', { method: 'POST', body: formData });
      const data = await resp.json();

      if (resp.ok) {
        submitResult = { success: true, taskId: data.task_id };
        startPolling(data.task_id);
      } else {
        submitResult = { success: false, taskId: data.task_id, code: data.code, error: data.error || 'Submission failed' };
      }
    } catch (err) {
      submitResult = { success: false, error: err.message };
    } finally {
      submitting = false;
    }
  }

  function startPolling(taskId) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const resp = await fetch(`/check/${taskId}`);
        if (resp.ok) {
          taskStatus = await resp.json();
          if (taskStatus.status === 'DONE' || taskStatus.status === 'ERROR') {
            clearInterval(pollTimer);
            pollTimer = null;
          }
        }
      } catch (e) { /* ignore transient errors */ }
    }, 3000);
  }

  function openMonitor(taskId) {
    dispatch('openMonitor', { taskId });
  }

  // Scenario validation
  $: validationErrors = (() => {
    const errs = [];
    if (!scenario.scenarioID) errs.push('Scenario ID is required');
    if (scenario.simulationEnd <= scenario.simulationStart) errs.push('End time must be greater than start time');
    if (scenario.buildingBlocks.length === 0) errs.push('At least one building block is required');
    for (const bb of scenario.buildingBlocks) {
      if (!bb.instanceID) errs.push('All building blocks need an Instance ID');
      if (!bb.type) errs.push(`Block "${bb.instanceID || '?'}" needs a Type`);
    }
    return errs;
  })();

  $: canSubmit = validationErrors.length === 0 && missingResources.length === 0;
</script>

<div class="new-sim">
  <!-- Sub-tabs -->
  <div class="sub-tabs">
    <button class="sub-tab" class:active={activeSubTab === 'scenario'} on:click={() => activeSubTab = 'scenario'}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      Scenario
    </button>
    <button class="sub-tab" class:active={activeSubTab === 'run'} on:click={() => activeSubTab = 'run'}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      Run
    </button>
  </div>

  <!-- Scenario sub-tab -->
  {#if activeSubTab === 'scenario'}
    <div class="scenario-content">
      <!-- Toolbar -->
      <div class="toolbar">
        <button class="tool-btn" on:click={handleUpload}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          Upload JSON
        </button>
        <button class="tool-btn" on:click={handleExport}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          Export JSON
        </button>
        <button class="tool-btn danger" on:click={handleReset}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
          Reset
        </button>
        <div class="toolbar-spacer"></div>
        <button class="tool-btn" class:active={showJsonPreview} on:click={() => showJsonPreview = !showJsonPreview}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          {showJsonPreview ? 'Hide' : 'Show'} JSON
        </button>
      </div>

      <div class="scenario-layout" class:with-preview={showJsonPreview}>
        <!-- Form panel -->
        <div class="form-panel">
          <!-- Scenario Metadata -->
          <section class="form-section">
            <h3 class="section-title">Scenario Metadata</h3>
            <div class="field-grid cols-3">
              <label class="field">
                <span class="field-label">Scenario ID</span>
                <input type="text" bind:value={scenario.scenarioID} placeholder="e.g. erlangen_2" />
              </label>
              <label class="field">
                <span class="field-label">Simulation Start</span>
                <input type="number" bind:value={scenario.simulationStart} min="0" />
              </label>
              <label class="field">
                <span class="field-label">Simulation End</span>
                <input type="number" bind:value={scenario.simulationEnd} min="1" />
              </label>
            </div>
          </section>

          <!-- Execution -->
          <section class="form-section">
            <h3 class="section-title">Execution</h3>
            <div class="field-grid cols-4">
              <label class="field">
                <span class="field-label">Random Seed</span>
                <input type="number" bind:value={scenario.execution.randomSeed} min="0" />
              </label>
              <label class="field">
                <span class="field-label">Synced Participants</span>
                <input type="number" bind:value={scenario.execution.syncedParticipants} min="0" />
              </label>
              <label class="field">
                <span class="field-label">Priority</span>
                <input type="number" bind:value={scenario.execution.priority} />
              </label>
              <label class="field">
                <span class="field-label">Constraints</span>
                <input type="text" bind:value={scenario.execution.constraints} placeholder="Optional" />
              </label>
            </div>
          </section>

          <!-- Building Blocks -->
          <section class="form-section">
            <div class="section-header">
              <h3 class="section-title">Building Blocks <span class="count-badge">{scenario.buildingBlocks.length}</span></h3>
              <button class="add-btn" on:click={addBB}>+ Add Block</button>
            </div>
            <div class="bb-list">
              {#each scenario.buildingBlocks as bb, i (i)}
                <ScenarioBBCard bind:bb={scenario.buildingBlocks[i]} index={i} onRemove={() => removeBB(i)} />
              {/each}
              {#if scenario.buildingBlocks.length === 0}
                <div class="empty-state">No building blocks. Click "Add Block" to begin.</div>
              {/if}
            </div>
          </section>

          <!-- Resource Files -->
          <section class="form-section">
            <div class="section-header">
              <h3 class="section-title">Resource Files <span class="count-badge">{resourceFiles.length}</span></h3>
            </div>
            <div class="resource-upload">
              <label class="upload-area">
                <input type="file" multiple on:change={handleResourceUpload} class="file-input" />
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                <span>Drop files or click to upload</span>
              </label>
              {#if resourceFiles.length > 0}
                <div class="resource-list">
                  {#each resourceFiles as f, i}
                    <div class="resource-item">
                      <span class="resource-name">{f.name}</span>
                      <span class="resource-size">{(f.size / 1024).toFixed(1)} KB</span>
                      <button class="kv-remove" on:click={() => removeResource(i)}>×</button>
                    </div>
                  {/each}
                </div>
              {/if}
              {#if missingResources.length > 0}
                <div class="warning-box">
                  <strong>⚠ Missing resources:</strong> {missingResources.join(', ')}
                </div>
              {/if}
            </div>
          </section>
        </div>

        <!-- JSON Preview panel -->
        {#if showJsonPreview}
          <div class="json-panel">
            <div class="json-header">
              <span>JSON Preview</span>
              <button class="copy-btn" on:click={() => navigator.clipboard.writeText(scenarioJson)}>Copy</button>
            </div>
            <pre class="json-code">{scenarioJson}</pre>
          </div>
        {/if}
      </div>
    </div>

  <!-- Run sub-tab -->
  {:else if activeSubTab === 'run'}
    <div class="run-content">
      <!-- Validation -->
      <section class="form-section">
        <h3 class="section-title">Pre-flight Check</h3>
        {#if validationErrors.length > 0 || missingResources.length > 0}
          <div class="checklist">
            {#each validationErrors as err}
              <div class="check-item fail">✗ {err}</div>
            {/each}
            {#each missingResources as f}
              <div class="check-item fail">✗ Missing resource file: {f}</div>
            {/each}
          </div>
        {:else}
          <div class="checklist">
            <div class="check-item pass">✓ Scenario schema valid</div>
            <div class="check-item pass">✓ All resource files provided</div>
            <div class="check-item pass">✓ Ready to submit</div>
          </div>
        {/if}
      </section>

      <!-- Submit -->
      <section class="form-section">
        <button class="submit-btn" on:click={handleSubmit} disabled={!canSubmit || submitting}>
          {#if submitting}
            <span class="spinner"></span> Submitting…
          {:else}
            ▶ Launch Simulation
          {/if}
        </button>
      </section>

      <!-- Result -->
      {#if submitResult}
        <section class="form-section">
          <h3 class="section-title">Submission Result</h3>
          {#if submitResult.success}
            <div class="result-box success">
              <strong>✓ Submitted!</strong> Task ID: <code>{submitResult.taskId}</code>
            </div>
            <button class="monitor-link" on:click={() => openMonitor(submitResult.taskId)}>
              Open Monitor
            </button>
          {:else}
            <div class="result-box error">
              <strong>{submitResult.code === 'submission_outcome_unknown' ? 'Delivery unconfirmed:' : 'Submission failed:'}</strong> {submitResult.error}
            </div>
            {#if submitResult.taskId}
              <button class="monitor-link" on:click={() => openMonitor(submitResult.taskId)}>Open Monitor</button>
            {/if}
          {/if}
        </section>
      {/if}

      <!-- Live status polling -->
      {#if taskStatus}
        <section class="form-section">
          <h3 class="section-title">Simulation Progress</h3>
          <div class="status-display">
            <span class="status-badge {taskStatus.status.toLowerCase()}">{taskStatus.status}</span>
          </div>
          {#if taskStatus.downloads?.length}
            <div class="result-files">
              <h4>Result Files</h4>
              {#each taskStatus.downloads as url, i}
                <a href={url} class="file-link" download>📄 {taskStatus.files[i]}</a>
              {/each}
            </div>
          {/if}
          {#if taskStatus.status === 'ERROR' && taskStatus.error}
            <div class="result-box error">{taskStatus.error}</div>
          {/if}
        </section>
      {/if}
    </div>
  {/if}
</div>

<style>
  .new-sim { display: flex; flex-direction: column; height: 100%; }

  /* Sub-tabs */
  .sub-tabs {
    display: flex; gap: 2px; padding: 0 16px;
    background: var(--bg-surface); border-bottom: 1px solid var(--border-light);
    flex-shrink: 0;
  }
  .sub-tab {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 10px 16px; border: none; background: none;
    font-size: 0.82rem; font-weight: 600; color: var(--text-muted);
    cursor: pointer; border-bottom: 2px solid transparent;
    transition: all var(--transition-fast);
  }
  .sub-tab svg { width: 14px; height: 14px; }
  .sub-tab:hover { color: var(--text-secondary); }
  .sub-tab.active { color: var(--brand-primary); border-bottom-color: var(--brand-primary); }

  /* Content areas */
  .scenario-content, .run-content {
    flex: 1; overflow-y: auto; padding: 16px;
  }

  /* Toolbar */
  .toolbar {
    display: flex; gap: 6px; align-items: center;
    padding: 8px 0; margin-bottom: 12px; flex-wrap: wrap;
  }
  .tool-btn {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 6px 12px; border: 1px solid var(--border-light);
    border-radius: var(--radius-sm); background: var(--bg-surface);
    font-size: 0.78rem; font-weight: 600; color: var(--text-secondary);
    cursor: pointer; transition: all var(--transition-fast);
  }
  .tool-btn svg { width: 14px; height: 14px; }
  .tool-btn:hover { border-color: var(--brand-primary); color: var(--brand-primary); }
  .tool-btn.active { background: var(--brand-primary-light); border-color: var(--brand-primary); color: var(--brand-primary); }
  .tool-btn.danger:hover { border-color: var(--status-error); color: var(--status-error); }
  .toolbar-spacer { flex: 1; }

  /* Layout */
  .scenario-layout { display: flex; gap: 16px; }
  .scenario-layout.with-preview .form-panel { flex: 1; min-width: 0; }
  .form-panel { flex: 1; display: flex; flex-direction: column; gap: 16px; }

  /* Form sections */
  .form-section {
    background: var(--bg-surface); border: 1px solid var(--border-light);
    border-radius: var(--radius-md); padding: 14px;
  }
  .section-header { display: flex; align-items: center; justify-content: space-between; }
  .section-title {
    margin: 0 0 10px 0; font-size: 0.82rem; font-weight: 700;
    color: var(--text-secondary); display: flex; align-items: center; gap: 6px;
  }
  .count-badge {
    font-size: 0.65rem; font-weight: 700; padding: 1px 6px;
    border-radius: 10px; background: var(--brand-primary-light); color: var(--brand-primary);
  }

  .field-grid { display: grid; gap: 10px; }
  .cols-3 { grid-template-columns: repeat(3, 1fr); }
  .cols-4 { grid-template-columns: repeat(4, 1fr); }

  .field { display: flex; flex-direction: column; gap: 3px; }
  .field-label { font-size: 0.72rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .field input, .field select {
    padding: 6px 10px; border: 1px solid var(--border-light);
    border-radius: var(--radius-sm); font-size: 0.85rem;
    background: var(--bg-surface); color: var(--text-primary);
    outline: none; transition: border-color var(--transition-fast);
  }
  .field input:focus, .field select:focus { border-color: var(--brand-primary); }

  /* BB list */
  .bb-list { display: flex; flex-direction: column; gap: 8px; }
  .empty-state {
    text-align: center; padding: 20px; color: var(--text-muted);
    font-size: 0.85rem; border: 1px dashed var(--border-light);
    border-radius: var(--radius-md);
  }

  .add-btn {
    padding: 5px 12px; border: 1px dashed var(--brand-primary);
    border-radius: var(--radius-sm); background: var(--brand-primary-light);
    color: var(--brand-primary); font-size: 0.78rem; font-weight: 600;
    cursor: pointer; transition: all var(--transition-fast);
  }
  .add-btn:hover { background: var(--brand-primary); color: white; border-style: solid; }

  /* Resource upload */
  .resource-upload { display: flex; flex-direction: column; gap: 8px; }
  .upload-area {
    display: flex; flex-direction: column; align-items: center; gap: 6px;
    padding: 16px; border: 2px dashed var(--border-mid); border-radius: var(--radius-md);
    cursor: pointer; color: var(--text-muted); font-size: 0.82rem;
    transition: all var(--transition-fast);
  }
  .upload-area:hover { border-color: var(--brand-primary); color: var(--brand-primary); }
  .upload-area svg { width: 20px; height: 20px; }
  .file-input { display: none; }

  .resource-list { display: flex; flex-direction: column; gap: 2px; }
  .resource-item {
    display: flex; align-items: center; gap: 8px;
    padding: 4px 8px; background: var(--bg-inset); border-radius: var(--radius-sm);
    font-size: 0.8rem;
  }
  .resource-name { font-weight: 600; color: var(--text-primary); flex: 1; }
  .resource-size { color: var(--text-muted); font-size: 0.72rem; }

  .warning-box {
    padding: 8px 12px; background: #fef3c7; border: 1px solid #fbbf24;
    border-radius: var(--radius-sm); font-size: 0.8rem; color: #92400e;
  }

  /* JSON preview */
  .json-panel {
    width: 380px; flex-shrink: 0; display: flex; flex-direction: column;
    border: 1px solid var(--border-light); border-radius: var(--radius-md);
    background: #1e293b; overflow: hidden;
  }
  .json-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px 12px; background: #0f172a; border-bottom: 1px solid #334155;
    font-size: 0.78rem; font-weight: 600; color: #94a3b8;
  }
  .copy-btn {
    padding: 3px 8px; border: 1px solid #475569; border-radius: 4px;
    background: none; color: #94a3b8; font-size: 0.72rem; cursor: pointer;
  }
  .copy-btn:hover { background: #334155; color: #e2e8f0; }
  .json-code {
    flex: 1; overflow: auto; margin: 0; padding: 12px;
    font-family: 'Fira Code', 'Cascadia Code', monospace; font-size: 0.75rem;
    line-height: 1.5; color: #e2e8f0; white-space: pre;
  }

  /* Run tab */
  .checklist { display: flex; flex-direction: column; gap: 4px; }
  .check-item { font-size: 0.85rem; padding: 4px 0; }
  .check-item.pass { color: var(--status-done); }
  .check-item.fail { color: var(--status-error); }

  .submit-btn {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 10px 24px; border: none; border-radius: var(--radius-sm);
    background: var(--brand-primary); color: white;
    font-size: 0.9rem; font-weight: 700; cursor: pointer;
    transition: all var(--transition-fast);
  }
  .submit-btn:hover:not(:disabled) { background: var(--brand-primary-hover); }
  .submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  .spinner {
    width: 14px; height: 14px;
    border: 2px solid rgba(255,255,255,0.3); border-radius: 50%;
    border-top-color: white; animation: spin 0.7s linear infinite;
  }

  .result-box {
    padding: 10px 14px; border-radius: var(--radius-sm); font-size: 0.85rem;
  }
  .result-box.success { background: #ecfdf5; border: 1px solid #6ee7b7; color: #065f46; }
  .result-box.error { background: #fef2f2; border: 1px solid #fca5a5; color: #991b1b; }
  .result-box code { background: rgba(0,0,0,0.06); padding: 2px 6px; border-radius: 4px; font-size: 0.78rem; }

  .status-display { margin-bottom: 10px; }
  .status-badge {
    display: inline-block; padding: 4px 12px; border-radius: 12px;
    font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  }
  .status-badge.pending { background: #fef3c7; color: #92400e; }
  .status-badge.running { background: #dbeafe; color: #1e40af; }
  .status-badge.done { background: #d1fae5; color: #065f46; }
  .status-badge.error { background: #fee2e2; color: #991b1b; }

  .result-files { display: flex; flex-direction: column; gap: 4px; }
  .result-files h4 { margin: 0 0 4px 0; font-size: 0.82rem; color: var(--text-secondary); }
  .file-link {
    font-size: 0.82rem; color: var(--brand-primary); text-decoration: none;
    padding: 4px 0;
  }
  .file-link:hover { text-decoration: underline; }
  .monitor-link {
    align-self: flex-start;
    margin-top: 10px;
    border: 1px solid var(--border-light);
    background: var(--bg-surface);
    color: var(--brand-primary);
    border-radius: var(--radius-sm);
    padding: 7px 11px;
    font-size: 0.8rem;
    font-weight: 700;
    cursor: pointer;
  }
  .monitor-link:hover { border-color: var(--brand-primary); }

  .kv-remove {
    width: 22px; height: 22px; display: flex; align-items: center; justify-content: center;
    border: none; background: none; cursor: pointer; color: var(--text-muted);
    font-size: 1rem; font-weight: 700; border-radius: 4px;
  }
  .kv-remove:hover { background: rgba(239,68,68,0.1); color: var(--status-error); }

  @keyframes spin { to { transform: rotate(360deg); } }

  @media (max-width: 768px) {
    .cols-3 { grid-template-columns: 1fr; }
    .cols-4 { grid-template-columns: repeat(2, 1fr); }
    .scenario-layout { flex-direction: column; }
    .json-panel { width: 100%; max-height: 300px; }
  }
</style>
