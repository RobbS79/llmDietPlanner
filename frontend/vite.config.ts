// File: frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ command, isSsrBuild }) => ({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  base: command === 'build' && !isSsrBuild ? '/static/' : '/',
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
    outDir: isSsrBuild ? 'dist/server' : 'dist',
    emptyOutDir: !isSsrBuild,
    assetsDir: 'assets',
    target: 'es2020',
    sourcemap: false,
    rollupOptions: {
      output: isSsrBuild
        ? { entryFileNames: '[name].js' }
        : {
            chunkFileNames: 'assets/[name]-[hash].js',
            entryFileNames: 'assets/[name]-[hash].js',
            assetFileNames: 'assets/[name]-[hash].[ext]',
          },
    },
  },
}))