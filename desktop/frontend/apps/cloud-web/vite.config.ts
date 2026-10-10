import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '../..')
// 框架无关 Web Components 组件库的构建产物（仓库级 packages/notemeld-ui）。
const nmUiDist = path.resolve(root, '../../../packages/notemeld-ui/dist/index.js')

// 仅 cloud-web：把 React 版 '@notemeld/ui-web'（裸名 + 任意子路径）
// 重定向到 Web Components 的 React 绑定包；并把 '@notemeld/ui' 指向其 dist。
const uiReactSrc = path.resolve(root, 'packages/ui-react/src')

export default defineConfig({
  root: here,
  base: '/',
  define: { 'import.meta.env.VITE_CLOUD_WEB': JSON.stringify('true') },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: [
      { find: /^@notemeld\/ui-web$/, replacement: path.join(uiReactSrc, 'index.ts') },
      {
        find: /^@notemeld\/ui-web\/(.*)$/,
        replacement: path.join(uiReactSrc, '$1'),
      },
      { find: /^@notemeld\/ui$/, replacement: nmUiDist },
      { find: '@', replacement: path.resolve(root, 'src') },
    ],
  },
  build: {
    outDir: path.resolve(root, 'dist-cloud-web'),
    emptyOutDir: true,
    rollupOptions: { input: path.resolve(here, 'index.html') },
  },
})
