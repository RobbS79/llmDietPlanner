// File: frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// PHASE 1: Sync Frontend Build
// This configuration ensures Vite prefixes all assets with /static/ 
// so they align with Django's static file serving logic.
export default defineConfig({
  plugins: [react()],
  // CRITICAL: Tells Vite that assets will be served from Django's /static/ path
  base: '/static/', 
  build: {
    // Output directory that the Docker builder and Django will target
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',
    // Support modern features for Google Auth integration
    target: 'es2020',
    sourcemap: false,
    rollupOptions: {
      output: {
        // Prevent naming collisions and ensure clean content hashing
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]'
      }
    }
  }
})