import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import RootLayout from './layouts/RootLayout.tsx'
import { registerDesktopRuntimeOnPageLoad } from './utils/runtime.ts'
import { isDemoMode } from './demo/mode.ts'

const rootElement = document.getElementById('root')!

createRoot(rootElement).render(
  <StrictMode>
    <RootLayout>
      <App />
    </RootLayout>
  </StrictMode>
)

if (!isDemoMode()) {
  void registerDesktopRuntimeOnPageLoad()
}
