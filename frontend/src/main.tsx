import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import RootLayout from './layouts/RootLayout.tsx'
import { registerDesktopRuntimeOnPageLoad } from './utils/runtime.ts'

const rootElement = document.getElementById('root')!

createRoot(rootElement).render(
  <StrictMode>
    <RootLayout>
      <App />
    </RootLayout>
  </StrictMode>
)

void registerDesktopRuntimeOnPageLoad()
