import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'
import tailwindcss from '@tailwindcss/vite'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 框架无关 Web Components 组件库的构建产物（仓库级 packages/notemeld-ui）。
const nmUiDist = path.resolve(__dirname, '../../../packages/notemeld-ui/dist/index.js')
// React 绑定包：把 '@notemeld/ui-web' 重定向到 nm-* Web Components 的 React 绑定。
const uiReactSrc = path.resolve(__dirname, 'packages/ui-react/src')

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(__dirname, '../'))

  // The client API base includes `/api`, while Vite's proxy target must be
  // the origin so `/api/*` is forwarded exactly once.
  const apiBaseUrl = (env.VITE_API_BASE_URL || 'http://127.0.0.1:8483').replace(/\/api\/?$/, '')
  const port = parseInt(env.VITE_FRONTEND_PORT || '3015', 10)

  return {
    // Use root-relative assets for both browser and Tauri production builds.
    // The desktop router is a HashRouter, so this does not depend on server
    // fallback routing and avoids WebView MIME/path mismatches caused by a
    // relative `./` base in packaged applications.
    base: env.VITE_BASE_PATH || '/',
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: [
        { find: /^@notemeld\/ui-web$/, replacement: path.join(uiReactSrc, 'index.ts') },
        { find: /^@notemeld\/ui-web\/(.*)$/, replacement: path.join(uiReactSrc, '$1') },
        { find: /^@notemeld\/ui$/, replacement: nmUiDist },
        { find: '@', replacement: path.resolve(__dirname, './src') },
      ],
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            markdown: ['react-markdown', 'react-syntax-highlighter', 'remark-gfm', 'remark-math', 'rehype-katex'],
            markmap: ['markmap-lib', 'markmap-view', 'markmap-toolbar', 'markmap-common'],
            vendor: ['react', 'react-dom', 'react-router-dom'],
          },
        },
      },
    },
    server: {
      host: '0.0.0.0',
      port: port,
      allowedHosts: true, // 允许任意域名访问
      proxy: {
        '/api': {
          target: apiBaseUrl,
          changeOrigin: true,
          rewrite: path => path.replace(/^\/api/, '/api'),
        },
        '/static': {
          target: apiBaseUrl,
          changeOrigin: true,
          rewrite: path => path.replace(/^\/static/, '/static'),
        },
      },
    },
  }
})
