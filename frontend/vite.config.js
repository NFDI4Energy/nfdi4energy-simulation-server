import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [svelte()],
  base: '/dashboard/',
  build: {
    outDir: '../fastapi_app/static/svelte-dist',
    emptyOutDir: true,
  }
})

