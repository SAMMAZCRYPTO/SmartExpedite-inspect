import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: true,
    proxy: {
      '/api': {
        target: 'http://localhost:5214',
        changeOrigin: true,
      },
      '/uploads': {
        target: 'http://localhost:5214',
        changeOrigin: true,
      },
      '/smartexpedit-app': {
        target: 'http://localhost:5214',
        changeOrigin: true,
      },
      '/sx-config.js': {
        target: 'http://localhost:5214',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
    extensions: ['.mjs', '.js', '.jsx', '.ts', '.tsx', '.json']
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        '.js': 'jsx',
      },
    },
  },
})
