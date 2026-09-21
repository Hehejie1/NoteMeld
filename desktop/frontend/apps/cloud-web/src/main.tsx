import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { ThemeProvider, TooltipProvider } from '@notemeld/ui-web'
import RootLayout from '../../../src/layouts/RootLayout'
import CloudPage from '../../../src/pages/CloudPage'
import '../../../src/index.css'
import '../../../src/App.css'
import '../../../src/newProductDesktop.css'
import '../../../src/newProductPolish.css'
import '../../../src/desktopShellPolish.css'
import '../../../src/desktopShellCompliance.css'
import '../../../src/hostApprovalInbox.css'
import '../../../src/cloudAlignment.css'

function CloudWebApp() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/cloud" element={<Navigate to="/cloud/workbench" replace />} />
        <Route path="/cloud/login" element={<CloudPage />} />
        <Route path="/cloud/access-request" element={<CloudPage />} />
        <Route path="/cloud/workbench" element={<CloudPage />} />
        <Route path="/cloud/sessions/:sessionId?" element={<CloudPage />} />
        <Route path="/cloud/people" element={<CloudPage />} />
        <Route path="/cloud/devices" element={<CloudPage />} />
        <Route path="/cloud/settings/*" element={<CloudPage />} />
        <Route path="/cloud/*" element={<CloudNotFound />} />
        <Route path="*" element={<Navigate to="/cloud/login" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

function CloudNotFound() {
  return <main className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center"><h1 className="text-2xl font-semibold">Cloud page not found</h1><p className="text-sm text-slate-600">The requested Cloud route does not exist.</p><a className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white" href="/cloud/workbench">Open Cloud workbench</a></main>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RootLayout>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
        <TooltipProvider>
          <CloudWebApp />
        </TooltipProvider>
      </ThemeProvider>
    </RootLayout>
  </StrictMode>,
)
