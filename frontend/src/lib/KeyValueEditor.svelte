<script>
  /** Reusable key-value pair editor for parameters, resources, results maps.
   *  @prop {Object} entries - the key-value map to edit (bound)
   *  @prop {string} keyLabel - label for the key column
   *  @prop {string} valueLabel - label for the value column
   *  @prop {string[]} valueSuggestions - optional dropdown suggestions for values
   */
  export let entries = {};
  export let keyLabel = 'Key';
  export let valueLabel = 'Value';
  export let valueSuggestions = [];

  let newKey = '';
  let newValue = '';

  function addEntry() {
    const k = newKey.trim();
    const v = newValue.trim();
    if (!k) return;
    entries = { ...entries, [k]: v };
    newKey = '';
    newValue = '';
  }

  function removeEntry(key) {
    const copy = { ...entries };
    delete copy[key];
    entries = copy;
  }

  function handleKeydown(e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      addEntry();
    }
  }
</script>

<div class="kv-editor">
  {#if Object.keys(entries).length > 0}
    <div class="kv-list">
      {#each Object.entries(entries) as [k, v]}
        <div class="kv-row">
          <span class="kv-key" title={k}>{k}</span>
          <span class="kv-val" title={v}>{v}</span>
          <button class="kv-remove" on:click={() => removeEntry(k)} title="Remove">×</button>
        </div>
      {/each}
    </div>
  {/if}
  <div class="kv-add-row">
    <input
      class="kv-input"
      type="text"
      bind:value={newKey}
      placeholder={keyLabel}
      on:keydown={handleKeydown}
    />
    {#if valueSuggestions.length > 0}
      <select class="kv-input kv-select" bind:value={newValue}>
        <option value="">{valueLabel}…</option>
        {#each valueSuggestions as s}
          <option value={s}>{s}</option>
        {/each}
      </select>
    {:else}
      <input
        class="kv-input"
        type="text"
        bind:value={newValue}
        placeholder={valueLabel}
        on:keydown={handleKeydown}
      />
    {/if}
    <button class="kv-add-btn" on:click={addEntry} title="Add">+</button>
  </div>
</div>

<style>
  .kv-editor { width: 100%; }

  .kv-list {
    display: flex; flex-direction: column; gap: 2px;
    margin-bottom: 6px;
  }

  .kv-row {
    display: grid; grid-template-columns: 1fr 1fr 28px;
    align-items: center; gap: 6px;
    padding: 4px 8px;
    background: var(--bg-inset); border-radius: var(--radius-sm);
    font-size: 0.8rem;
  }

  .kv-key { font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kv-val { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .kv-remove {
    width: 22px; height: 22px;
    display: flex; align-items: center; justify-content: center;
    border: none; background: none; cursor: pointer;
    color: var(--text-muted); font-size: 1rem; font-weight: 700;
    border-radius: 4px;
    transition: all var(--transition-fast);
  }
  .kv-remove:hover { background: rgba(239,68,68,0.1); color: var(--status-error); }

  .kv-add-row {
    display: grid; grid-template-columns: 1fr 1fr 28px;
    gap: 6px; align-items: center;
  }

  .kv-input {
    padding: 5px 8px; border: 1px solid var(--border-light);
    border-radius: var(--radius-sm); font-size: 0.8rem;
    background: var(--bg-surface); color: var(--text-primary);
    outline: none; transition: border-color var(--transition-fast);
    width: 100%;
  }
  .kv-input:focus { border-color: var(--brand-primary); }

  .kv-select { cursor: pointer; }

  .kv-add-btn {
    width: 28px; height: 28px;
    display: flex; align-items: center; justify-content: center;
    border: 1px dashed var(--border-mid); background: none;
    border-radius: var(--radius-sm); cursor: pointer;
    color: var(--brand-primary); font-size: 1.1rem; font-weight: 700;
    transition: all var(--transition-fast);
  }
  .kv-add-btn:hover { background: var(--brand-primary-light); border-style: solid; }
</style>
