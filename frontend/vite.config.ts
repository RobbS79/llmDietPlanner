// File: frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // CRITICAL: Tells Vite assets are served via Django's /static/ path
  base: '/static/', 
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',
    // Set target to es2020 to support import.meta and modern browser features
    target: 'es2020'
  }
})