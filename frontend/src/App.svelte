<script>
  import { onMount } from 'svelte';
  import Login from './lib/Login.svelte';
  import Dashboard from './lib/Dashboard.svelte';

  let checkingAuth = true;
  let user = null;

  async function checkAuth() {
    try {
      const response = await fetch('/auth/me');
      if (response.ok) {
        user = await response.json();
      } else if (import.meta.env.DEV) {
        user = {
          id: 'dev-user',
          email: 'dev@simaas.local',
          display_name: 'Dev User'
        };
      } else {
        user = null;
      }
    } catch (error) {
      console.error('Failed checking authentication state:', error);
      if (import.meta.env.DEV) {
        user = {
          id: 'dev-user',
          email: 'dev@simaas.local',
          display_name: 'Dev User'
        };
      } else {
        user = null;
      }
    } finally {
      setTimeout(() => {
        checkingAuth = false;
      }, 400);
    }
  }

  function handleLogout() {
    window.location.href = '/auth/logout';
  }

  onMount(() => {
    checkAuth();
  });
</script>

<main>
  {#if checkingAuth}
    <div class="loader-container">
      <div class="loader-ring"></div>
      <div class="loader-text">Securing session…</div>
    </div>
  {:else if !user}
    <Login />
  {:else}
    <Dashboard {user} onLogout={handleLogout} />
  {/if}
</main>

<style>
  main {
    width: 100vw;
    height: 100vh;
    overflow: hidden;
  }

  .loader-container {
    width: 100vw; height: 100vh;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    background-color: var(--bg-page);
    gap: 1.25rem;
  }

  .loader-ring {
    width: 40px; height: 40px;
    border: 3px solid var(--border-light);
    border-radius: 50%;
    border-top-color: var(--brand-primary);
    animation: spin 0.9s cubic-bezier(0.55, 0.055, 0.675, 0.19) infinite;
  }

  .loader-text {
    font-size: 0.9rem; font-weight: 500;
    letter-spacing: 0.03em; color: var(--text-muted);
    animation: pulse 1.5s ease-in-out infinite alternate;
  }

  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes pulse { from { opacity: 0.5; } to { opacity: 1; } }
</style>
