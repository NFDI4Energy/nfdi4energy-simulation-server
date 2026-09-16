<script>
  import logo from '../assets/logo.svg';
  export let user;
  export let authenticated = false;
  export let onChoose = () => {};
  export let onLogout = () => {};
</script>

<div class="chooser">
  <header>
    <img src={logo} alt="SimaaS" width="112" height="40" />
    <div><span>{user.display_name || user.email}</span><button on:click={onLogout}>Sign out</button></div>
  </header>
  <main>
    <h1>Frameworks</h1>
    <div class="frameworks">
      <button class="framework" on:click={() => onChoose('dacedsx')}>
        <span class="name">DaceDSX</span><span class="state">SimService</span><span aria-hidden="true">&rarr;</span>
      </button>
      <button class="framework" disabled={!authenticated} title={!authenticated ? 'Sign in required' : 'Open Mosaik'} on:click={() => onChoose('mosaik')}>
        <span class="name">Mosaik</span>
        <span class="state">{!authenticated ? 'Sign in required' : user.capabilities?.mosaikSubmissionEnabled ? 'Orbit' : 'Submissions paused'}</span>
        <span aria-hidden="true">&rarr;</span>
      </button>
    </div>
  </main>
</div>

<style>
  .chooser { height: 100%; overflow: auto; background: var(--bg-page); letter-spacing: 0; }
  header { min-height: 64px; padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; gap: 16px; background: white; border-bottom: 1px solid var(--border-light); }
  img { object-fit: contain; }
  header div { display: flex; align-items: center; gap: 16px; min-width: 0; }
  header span { overflow-wrap: anywhere; font-size: 14px; }
  button { font: inherit; cursor: pointer; color: var(--text-primary); }
  header button { background: white; border: 1px solid var(--border-mid); padding: 8px 12px; border-radius: 6px; white-space: nowrap; }
  main { max-width: 800px; margin: 48px auto; padding: 0 24px; }
  h1 { font-size: 24px; margin: 0 0 24px; }
  .frameworks { display: grid; gap: 12px; }
  .framework { display: grid; grid-template-columns: 1fr auto 24px; gap: 16px; align-items: center; min-height: 96px; padding: 24px; text-align: left; background: white; border: 1px solid var(--border-mid); border-radius: 8px; }
  .framework:hover:enabled { border-color: var(--brand-primary); background: #f0f7f8; }
  .framework:disabled { opacity: .6; cursor: not-allowed; }
  .name { font-size: 20px; font-weight: 600; }
  .state { color: var(--text-secondary); font-size: 13px; }
  @media (max-width: 520px) { header { padding: 12px; } header span { display: none; } .framework { grid-template-columns: 1fr 24px; padding: 20px; } .state { grid-row: 2; } .framework > span:last-child { grid-column: 2; grid-row: 1; } }
</style>
