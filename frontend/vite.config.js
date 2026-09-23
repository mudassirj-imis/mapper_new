import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        configure: (proxy) => {
          proxy.on('error', (err) => {
            console.log('[proxy] error', err.message);
          });
        }
      }
    }
  },
  preview: {
    port: 5173,
    host: true
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('node_modules/react/') ||
            id.includes('node_modules/react-dom/') ||
            id.includes('node_modules/react-router') ||
            id.includes('node_modules/scheduler/')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/@mui/material/')) {
            return 'vendor-mui-core';
          }
          if (id.includes('node_modules/@mui/icons-material/')) {
            return 'vendor-mui-icons';
          }
          if (id.includes('node_modules/@mui/system/') ||
            id.includes('node_modules/@mui/styled-engine') ||
            id.includes('node_modules/@mui/utils/')) {
            return 'vendor-mui-system';
          }
          if (id.includes('node_modules/@emotion/')) {
            return 'vendor-emotion';
          }
          if (id.includes('node_modules/')) {
            if (!id.includes('@mui/') && !id.includes('react')) {
              return 'vendor-others';
            }
          }
        }
      }
    },
    chunkSizeWarningLimit: 600
  }
})
