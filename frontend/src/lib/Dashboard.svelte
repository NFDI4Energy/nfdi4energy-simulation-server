<script>
  /** Dashboard: top-level shell with header, collapsible right sidebar, and main content.
   *  @prop {Object} user - the authenticated user object
   *  @prop {function} onLogout - logout callback
   */
  import NewSimulation from "./NewSimulation.svelte";
  import History from "./History.svelte";
  import RunMonitor from "./RunMonitor.svelte";

  export let user;
  export let onLogout = () => {};

  let sidebarOpen = false; // Starts closed (slid out of view)
  let activeTab = null; // Starts blank (no tab open)
  let monitorTaskId = null;

  function selectTab(tab) {
    if (tab === "monitor") {
      monitorTaskId = null;
    }
    activeTab = tab;
    sidebarOpen = false; // Slide drawer back out of view after selection
  }

  function openMonitor(event) {
    monitorTaskId = event.detail.taskId;
    activeTab = "monitor";
    sidebarOpen = false;
  }
</script>

<div class="dashboard">
  <!-- Header -->
  <header class="dash-header">
    <div class="header-left">
      <button
        class="hamburger"
        on:click={() => (sidebarOpen = !sidebarOpen)}
        title="Toggle menu"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      <div class="header-brand">
        <span class="header-brand-name"
          >Sim<span class="brand-highlight">aaS</span></span
        >
      </div>
    </div>
    <div class="header-right">
      <div class="user-chip">
        <span class="user-avatar"
          >{user.display_name ? user.display_name[0].toUpperCase() : "U"}</span
        >
        <span class="user-name">{user.display_name || user.email}</span>
      </div>
      <button class="logout-btn" on:click={onLogout} title="Log out">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"
          />
        </svg>
      </button>
    </div>
  </header>

  <div class="dash-body">
    <!-- Main content (left side) -->
    <main class="main-content">
      {#if activeTab === "new"}
        <NewSimulation on:openMonitor={openMonitor} />
      {:else if activeTab === "history"}
        <History on:openMonitor={openMonitor} />
      {:else if activeTab === "monitor"}
        <RunMonitor taskId={monitorTaskId} />
      {:else}
        <div class="blank-state">
          <div class="blank-message">
            <h2>Welcome to SimaaS</h2>
            <p>
              Click the menu icon on the top left to start a new simulation or
              view run history.
            </p>
          </div>
        </div>
      {/if}
    </main>

    <!-- Sidebar / Drawer (right side) -->
    <aside class="sidebar" class:collapsed={!sidebarOpen}>
      <div class="sidebar-header">
        <span class="sidebar-title">DaceDSX</span>
      </div>
      <nav class="sidebar-nav">
        <button
          class="nav-item"
          class:active={activeTab === "new"}
          on:click={() => selectTab("new")}
          title="New Simulation"
        >
          <span class="nav-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="16" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
          </span>
          <div class="nav-text">
            <span class="nav-label">New Simulation</span>
            <span class="nav-desc">Configure & run scenario</span>
          </div>
        </button>

        <button
          class="nav-item"
          class:active={activeTab === "history"}
          on:click={() => selectTab("history")}
          title="History"
        >
          <span class="nav-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </span>
          <div class="nav-text">
            <span class="nav-label">History</span>
            <span class="nav-desc">Past simulation runs</span>
          </div>
        </button>

        <button
          class="nav-item"
          class:active={activeTab === "monitor"}
          on:click={() => selectTab("monitor")}
          title="Run Monitor"
        >
          <span class="nav-icon">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          </span>
          <div class="nav-text">
            <span class="nav-label">Run Monitor</span>
            <span class="nav-desc">Live stats & events</span>
          </div>
        </button>
      </nav>
      <div class="sidebar-footer">
        <span class="sidebar-version">v1.0</span>
      </div>
    </aside>
  </div>
</div>

<style>
  .dashboard {
    display: flex;
    flex-direction: column;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    background: var(--bg-page);
  }

  /* Header */
  .dash-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--header-height);
    padding: 0 16px;
    background: var(--bg-header);
    border-bottom: 1px solid var(--border-light);
    flex-shrink: 0;
    z-index: 20;
    box-shadow: var(--shadow-sm);
  }

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .header-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .hamburger {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: none;
    cursor: pointer;
    border-radius: var(--radius-sm);
    color: #499fae !important; /* Force brand teal */
    transition: all var(--transition-fast);
  }
  .hamburger svg {
    width: 20px;
    height: 20px;
    stroke: #499fae !important; /* Force teal stroke */
  }
  .hamburger:hover {
    background: var(--bg-inset);
  }

  .header-brand {
    display: flex;
    align-items: center;
  }
  .header-brand-name {
    font-size: 1.1rem;
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -0.02em;
  }
  .brand-highlight {
    color: var(--brand-primary);
  }

  .user-chip {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 12px 4px 4px;
    background: var(--bg-inset);
    border-radius: 20px;
    border: 1px solid var(--border-light);
  }
  .user-avatar {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: linear-gradient(
      135deg,
      var(--brand-primary),
      var(--brand-accent)
    );
    color: white;
    font-weight: 700;
    font-size: 0.78rem;
  }
  .user-name {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--text-primary);
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .logout-btn {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px solid #499fae !important;
    background: none; /* Force teal border */
    border-radius: var(--radius-sm);
    cursor: pointer;
    color: #499fae !important;
    transition: all var(--transition-fast); /* Force teal color */
  }
  .logout-btn svg {
    width: 18px;
    height: 18px;
    stroke: #499fae !important; /* Force teal stroke */
  }
  .logout-btn:hover {
    background: rgba(73, 159, 174, 0.06);
  }

  /* Body layout */
  .dash-body {
    display: flex;
    flex: 1;
    overflow: hidden;
    position: relative;
  }

  /* Sidebar on the Right (Drawer Style) */
  .sidebar {
    width: var(--sidebar-width);
    display: flex;
    flex-direction: column;
    background: var(--bg-sidebar);
    box-shadow: -4px 0 16px rgba(0, 0, 0, 0.15);
    transition:
      width var(--transition-normal),
      box-shadow var(--transition-normal);
    flex-shrink: 0;
    overflow: hidden;
    z-index: 10;
  }
  .sidebar.collapsed {
    width: 0;
    box-shadow: none;
  }

  .sidebar-header {
    padding: 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }
  .sidebar-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: #ffffff;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .sidebar-nav {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 8px;
    gap: 4px;
  }

  .nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border: none;
    background: transparent;
    border-radius: var(--radius-sm);
    cursor: pointer;
    color: rgba(255, 255, 255, 0.6);
    transition: all var(--transition-fast);
    text-align: left;
    width: 100%;
  }
  .nav-item:hover {
    background: rgba(255, 255, 255, 0.06);
    color: rgba(255, 255, 255, 0.85);
  }
  .nav-item.active {
    background: rgba(73, 159, 174, 0.15);
    color: #a8d9e0;
  }

  .nav-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    flex-shrink: 0;
  }
  .nav-icon svg {
    width: 18px;
    height: 18px;
  }

  .nav-text {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .nav-label {
    font-size: 0.82rem;
    font-weight: 600;
    white-space: nowrap;
  }
  .nav-desc {
    font-size: 0.68rem;
    opacity: 0.6;
    white-space: nowrap;
  }

  .sidebar-footer {
    padding: 12px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
  .sidebar-version {
    font-size: 0.68rem;
    color: rgba(255, 255, 255, 0.3);
  }

  /* Main content */
  .main-content {
    flex: 1;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* Blank State */
  .blank-state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: var(--bg-page);
    padding: 24px;
    text-align: center;
  }
  .blank-message h2 {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 8px;
  }
  .blank-message p {
    font-size: 0.9rem;
    color: var(--text-muted);
    max-width: 400px;
    margin: 0 auto;
  }
</style>
