import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')

export default defineConfig({
  root: path.resolve(path.dirname(fileURLToPath(import.meta.url))),
  base: '/',
  define: { 'import.meta.env.VITE_CLOUD_WEB': JSON.stringify('true') },
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(root, 'src') } },
  build: {
    outDir: path.resolve(root, 'dist-cloud-web'),
    emptyOutDir: true,
    rollupOptions: { input: path.resolve(path.dirname(fileURLToPath(import.meta.url)), 'index.html') },
  },
})
