// File: frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * PHASE 1: Sync Frontend Build
 * This configuration ensures Vite prefixes all assets with /static/ 
 * so they align with Django's static file serving logic.
 */
export default defineConfig({
  plugins: [react()],
  // Ensures index.html uses <script src="/static/assets/...">
  base: '/static/', 
  build: {
    // Output directory that Django will target
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',
    // Support for modern JS features used in our Auth logic
    target: 'es2020',
    sourcemap: false,
    rollupOptions: {
      output: {
        // Prevent naming collisions and ensure clean hashing
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]'
      }
    }
  }
})