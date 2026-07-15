<script>
  import brandLogo from "../assets/logo.svg";

  let loading = false;

  function handleLogin() {
    loading = true;
    window.location.href = "/auth/login";
  }
</script>

<div class="login-container">
  <div class="login-wrapper">
    <!-- Brand Logo Header -->
    <div class="brand-header">
      <img src={brandLogo} alt="DaceDSX Logo" class="brand-logo-img" />
    </div>

    <!-- Simulation Frameworks List (Option 1) - Positioned after Logo, before Button -->
    <div class="frameworks-list">
      <span class="fw-title">Powering SimaaS</span>
      <div class="fw-badges">
        <span class="fw-tag"><span class="fw-highlight">Da</span>ceDSX</span>
        <span class="fw-tag"><span class="fw-highlight">mo</span>saik</span>
        <span class="fw-tag"
          ><span class="fw-highlight">VI</span>LLASframework</span
        >
      </div>
    </div>

    <!-- Clean, perfectly centered "Sign in" button directly below frameworks list -->
    <button class="login-btn" on:click={handleLogin} disabled={loading}>
      {#if loading}
        <span class="spinner"></span>
        <span>Connecting to NFDI AAI...</span>
      {:else}
        <span>Sign in</span>
      {/if}
    </button>

    <!-- Details Card -->
    <div class="login-card">
      <div class="card-content">
        <!-- Federated Login Tooltip (Option 3) -->
        <div class="aai-info">
          <span class="info-badge">ℹ️</span>
          <span>Uses federated institutional login</span>
          <div class="tooltip-content">
            NFDI AAI allows you to log in securely using your existing home
            university or research center account. No new password registration
            is required.
          </div>
        </div>
      </div>

      <div class="card-footer">
        <p>
          Authorized access only. Registered entities are authenticated securely
          via OpenID Connect (OIDC).
        </p>
      </div>
    </div>
  </div>
</div>

<style>
  :global(body) {
    background-color: #f8fafc; /* Clean slate 50 */
    color: #0f172a; /* Dark slate 900 text */
    margin: 0;
    font-family:
      "Inter",
      -apple-system,
      BlinkMacSystemFont,
      "Segoe UI",
      Roboto,
      sans-serif;
    overflow: hidden;
  }

  .login-container {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background-color: #f8fafc;
    z-index: 9999;
  }

  /* Centered stack container for logo, button, and card */
  .login-wrapper {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 90%;
    max-width: 500px; /* Centered, compact layout suited for standard SVG logo */
  }

  /* Brand Header styling */
  .brand-header {
    display: flex;
    justify-content: center;
    align-items: center;
    margin-bottom: 2rem;
    width: 100%;
  }

  .brand-logo-img {
    max-width: 320px;
    width: 100%;
    height: auto;
    display: block;
  }

  /* Option 1: Simulation Frameworks List styling */
  .frameworks-list {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1.75rem; /* Elegant pacing above the button */
    width: 100%;
  }

  .fw-title {
    font-size: 0.725rem;
    font-weight: 700;
    color: #64748b; /* Slate 500 */
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .fw-badges {
    display: flex;
    gap: 0.5rem;
    justify-content: center;
    flex-wrap: wrap;
  }

  .fw-tag {
    font-size: 0.8rem;
    font-weight: 600;
    color: #334155; /* Slate 700 */
    background-color: #ffffff; /* Contrast card white */
    padding: 0.3rem 0.65rem;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02);
  }

  .fw-highlight {
    color: var(--brand-primary); /* Magenta highlight */
    font-weight: 800;
  }

  /* Clean, perfectly centered solid button directly below frameworks list */
  .login-btn {
    width: 100%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.65rem;
    padding: 0.9rem 1.5rem;
    border-radius: 6px;
    border: none;
    font-size: 0.95rem;
    font-weight: 600;
    color: #ffffff;
    background-color: var(--brand-primary); /* Teal primary */
    cursor: pointer;
    box-shadow: 0 4px 6px -1px rgba(73, 159, 174, 0.15);
    transition: all 0.2s ease-in-out;
    margin-bottom: 2.25rem; /* Elegant separation from details card */
    z-index: 100;
    text-align: center;
  }

  .login-btn:hover:not(:disabled) {
    background-color: var(--brand-primary-hover);
    box-shadow: 0 6px 12px -2px rgba(73, 159, 174, 0.25);
  }

  .login-btn:active:not(:disabled) {
    background-color: #2d626c;
  }

  .login-btn:disabled {
    opacity: 0.65;
    cursor: not-allowed;
    background-color: #94a3b8;
    box-shadow: none;
  }

  /* Loader spinner */
  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-radius: 50%;
    border-top-color: #ffffff;
    animation: spin 0.8s linear infinite;
  }

  /* Simple, flat, clean card below button */
  .login-card {
    width: 100%;
    padding: 2.5rem 2.25rem;
    border-radius: 12px;
    background-color: #ffffff; /* Solid White Card */
    border: 1px solid #e2e8f0; /* Light Slate Border */
    box-shadow:
      0 10px 25px -5px rgba(0, 0, 0, 0.05),
      0 8px 10px -6px rgba(0, 0, 0, 0.05),
      0 0 1px 0 rgba(0, 0, 0, 0.1);
    text-align: center;
  }

  /* Option 3: Federated AAI Tooltip styling */
  .aai-info {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.825rem;
    color: #2d626c; /* Slate 600 */
    background-color: var(--brand-primary-light); /* Teal 50 */
    border: 1px solid #a8d9e0; /* Teal 100 */
    padding: 0.4rem 0.8rem;
    border-radius: 20px;
    cursor: help;
    transition: all 0.2s ease;
  }

  .aai-info:hover {
    background-color: #a8d9e0;
  }

  .info-badge {
    font-size: 0.9rem;
  }

  .tooltip-content {
    visibility: hidden;
    width: 280px;
    background-color: #0f172a; /* Dark slate 900 for high-contrast readability */
    color: #f8fafc;
    text-align: left;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    position: absolute;
    z-index: 9999;
    bottom: 125%; /* Display above the badge */
    left: 50%;
    transform: translateX(-50%);
    opacity: 0;
    transition: opacity 0.3s;
    font-size: 0.75rem;
    line-height: 1.45;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
    pointer-events: none;
  }

  .aai-info:hover .tooltip-content {
    visibility: visible;
    opacity: 1;
  }

  /* Tooltip arrow */
  .tooltip-content::after {
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    margin-left: -5px;
    border-width: 5px;
    border-style: solid;
    border-color: #0f172a transparent transparent transparent;
  }

  /* Footer styling */
  .card-footer {
    margin-top: 2rem;
    border-top: 1px solid #e2e8f0;
    padding-top: 1rem;
  }

  .card-footer p {
    font-size: 0.7rem;
    line-height: 1.4;
    color: #64748b; /* Slate 500 */
    margin: 0;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
