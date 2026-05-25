// File: frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ command }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  base: command === 'build' ? '/static/' : '/',
  server: {
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://web:8000',
        changeOrigin: true,
      },
    },
  },
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
}))