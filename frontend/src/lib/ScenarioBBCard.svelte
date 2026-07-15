<script>
  /** Reusable Building Block editor card.
   *  @prop {Object} bb - the building block data object (bound)
   *  @prop {number} index - card index for display
   *  @prop {function} onRemove - callback to remove this block
   */
  import KeyValueEditor from "./KeyValueEditor.svelte";

  export let bb;
  export let index = 0;
  export let onRemove = () => {};

  let collapsed = false;

  const domainOptions = ["energy", "communication", "traffic"];
  const layerOptions = ["micro", "meso", "macro", "submicro"];
  const resourceTypeOptions = [
    "RoadMap",
    "Traffic",
    "Additional",
    "Config",
    "Input",
    "Network",
  ];

  // Responsibilities are an array of strings — manage as comma input
  let respInput = (bb.responsibilities || []).join(", ");
  $: bb.responsibilities = respInput
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
</script>

<div class="bb-card" class:collapsed>
  <div class="bb-header" on:click={() => (collapsed = !collapsed)}>
    <div class="bb-header-left">
      <span class="bb-index">#{index + 1}</span>
      <span class="bb-title">{bb.instanceID || "Untitled Block"}</span>
      <span class="bb-type-badge">{bb.type || "—"}</span>
      <span class="bb-domain-badge {bb.domain}">{bb.domain || "—"}</span>
    </div>
    <div class="bb-header-right">
      <button
        class="bb-remove"
        on:click|stopPropagation={onRemove}
        title="Remove block">×</button
      >
      <span class="bb-chevron">{collapsed ? "▸" : "▾"}</span>
    </div>
  </div>

  {#if !collapsed}
    <div class="bb-body">
      <!-- Row 1: Identity -->
      <div class="field-grid cols-3">
        <label class="field">
          <span class="field-label">Instance ID</span>
          <input
            type="text"
            bind:value={bb.instanceID}
            placeholder="e.g. SumoWrapper0"
          />
        </label>
        <label class="field">
          <span class="field-label">Type</span>
          <input
            type="text"
            bind:value={bb.type}
            placeholder="e.g. SumoWrapper"
          />
        </label>
        <label class="field">
          <span class="field-label">Step Length (ms)</span>
          <input
            type="number"
            bind:value={bb.stepLength}
            min="1"
            placeholder="1000"
          />
        </label>
      </div>

      <!-- Row 2: Domain/Layer -->
      <div class="field-grid cols-3">
        <label class="field">
          <span class="field-label">Domain</span>
          <select bind:value={bb.domain}>
            {#each domainOptions as d}
              <option value={d}>{d}</option>
            {/each}
          </select>
        </label>
        <label class="field">
          <span class="field-label">Layer</span>
          <select bind:value={bb.layer}>
            {#each layerOptions as l}
              <option value={l}>{l}</option>
            {/each}
          </select>
        </label>
        <div class="field toggle-group">
          <label class="toggle-item">
            <input type="checkbox" bind:checked={bb.synchronized} />
            <span>Synchronized</span>
          </label>
          <label class="toggle-item">
            <input type="checkbox" bind:checked={bb.isExternal} />
            <span>External</span>
          </label>
        </div>
      </div>

      <!-- Row 3: Responsibilities -->
      <label class="field">
        <span class="field-label">Responsibilities (comma-separated IDs)</span>
        <input
          type="text"
          bind:value={respInput}
          placeholder="1316826203, 1154372516"
        />
      </label>

      <!-- Key-Value sections -->
      <div class="kv-section">
        <span class="kv-section-title">Resources</span>
        <KeyValueEditor
          bind:entries={bb.resources}
          keyLabel="Filename"
          valueLabel="Type"
          valueSuggestions={resourceTypeOptions}
        />
      </div>
      <div class="kv-section">
        <span class="kv-section-title">Parameters</span>
        <KeyValueEditor
          bind:entries={bb.parameters}
          keyLabel="Param"
          valueLabel="Value"
        />
      </div>
      <div class="kv-section">
        <span class="kv-section-title">Results</span>
        <KeyValueEditor
          bind:entries={bb.results}
          keyLabel="Key"
          valueLabel="Value"
        />
      </div>
    </div>
  {/if}
</div>

<style>
  .bb-card {
    border: 1px solid var(--border-light);
    border-radius: var(--radius-md);
    background: var(--bg-surface);
    overflow: hidden;
    transition: box-shadow var(--transition-fast);
  }
  .bb-card:hover {
    box-shadow: var(--shadow-sm);
  }

  .bb-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 14px;
    background: var(--bg-inset);
    cursor: pointer;
    user-select: none;
    border-bottom: 1px solid var(--border-light);
  }
  .collapsed .bb-header {
    border-bottom: none;
  }

  .bb-header-left {
    display: flex;
    align-items: center;
    gap: 8px;
    overflow: hidden;
  }
  .bb-header-right {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .bb-index {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--text-muted);
    background: var(--bg-surface);
    padding: 2px 6px;
    border-radius: 4px;
    border: 1px solid var(--border-light);
  }
  .bb-title {
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .bb-type-badge {
    font-size: 0.7rem;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
    background: var(--brand-primary-light);
    color: var(--brand-primary);
  }
  .bb-domain-badge {
    font-size: 0.65rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .bb-domain-badge.energy {
    background: #fef3c7;
    color: #92400e;
  }
  .bb-domain-badge.traffic {
    background: #dbeafe;
    color: #1e40af;
  }
  .bb-domain-badge.communication {
    background: #ede9fe;
    color: #5b21b6;
  }

  .bb-remove {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: none;
    cursor: pointer;
    color: var(--text-muted);
    font-size: 1.15rem;
    font-weight: 700;
    border-radius: 4px;
    transition: all var(--transition-fast);
  }
  .bb-remove:hover {
    background: rgba(239, 68, 68, 0.1);
    color: var(--status-error);
  }

  .bb-chevron {
    font-size: 0.75rem;
    color: var(--text-muted);
  }

  .bb-body {
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .field-grid {
    display: grid;
    gap: 10px;
  }
  .cols-3 {
    grid-template-columns: repeat(3, 1fr);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .field-label {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .field input,
  .field select {
    padding: 6px 10px;
    border: 1px solid var(--border-light);
    border-radius: var(--radius-sm);
    font-size: 0.85rem;
    background: var(--bg-surface);
    color: var(--text-primary);
    outline: none;
    transition: border-color var(--transition-fast);
  }
  .field input:focus,
  .field select:focus {
    border-color: var(--brand-primary);
  }
  .field select {
    cursor: pointer;
  }

  .toggle-group {
    display: flex;
    flex-direction: row;
    gap: 12px;
    align-items: flex-end;
    padding-bottom: 6px;
  }
  .toggle-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 0.8rem;
    color: var(--text-secondary);
    cursor: pointer;
  }
  .toggle-item input[type="checkbox"] {
    accent-color: var(--brand-primary);
    cursor: pointer;
  }

  .kv-section {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .kv-section-title {
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  @media (max-width: 640px) {
    .cols-3 {
      grid-template-columns: 1fr;
    }
  }
</style>
