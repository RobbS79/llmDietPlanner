import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  /** * CRITICAL FIX: 
   * This ensures that index.html requests assets from /static/assets/ 
   * instead of /assets/. This allows WhiteNoise to serve them correctly.
   */
  base: '/static/', 
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',
  }
})