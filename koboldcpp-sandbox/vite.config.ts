import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import { nodePolyfills } from 'vite-plugin-node-polyfills'
import path from 'path'

export default defineConfig({
  plugins: [
    // Polyfills FIRST so React-SWC can transform JSX afterwards without
    // the polyfill plugin intercepting .tsx files.
    nodePolyfills({
      include: ['zlib', 'buffer', 'util'],
      globals: { Buffer: true, global: true, process: true },
      protocolImports: true,
    }),
    react(),
  ],
  // Backup: if any file slips through without SWC's react plugin handling it,
  // esbuild will use automatic JSX runtime (no React.createElement fallback).
  esbuild: {
    jsx: 'automatic',
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  optimizeDeps: {
    include: ['just-bash'],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:5002',
    },
  },
})
