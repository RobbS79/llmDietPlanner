// File: frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  // CRITICAL: Tells Vite assets are served via Django's /static/ path.
  // This ensures that all generated <script> and <link> tags in index.html
  // point to the correct location in the Django static files system.
  base: '/static/', 
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    assetsDir: 'assets',
    // We set the target to es2020 to ensure modern features like 
    // import.meta are handled correctly by the browser and the bundler.
    target: 'es2020',
    // Minify with esbuild for production performance
    minify: 'esbuild',
    // Ensure sourcemaps are disabled in production to protect logic
    sourcemap: false,
    rollupOptions: {
      output: {
        // Ensure consistent naming for long-term caching
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]'
      }
    }
  },
  server: {
    // Port 3000 for local development convenience
    port: 3000,
    strictPort: true,
  }
})