import './App.css'
import './newProductDesktop.css'
import './newProductPolish.css'
import { lazy, Suspense, useEffect, useState } from 'react'
import { BrowserRouter, HashRouter, Navigate, Outlet, Routes, Route, useLocation, useParams } from 'react-router-dom'
import { useTaskPolling } from '@/hooks/useTaskPolling.ts'
import { BackendInitProvider, useBackendInitContext } from '@/contexts/BackendInitContext.tsx'
import { systemCheck } from '@/services/system.ts'
import BackendInitDialog from '@/components/BackendInitDialog'
import AppLayout from '@/layouts/AppLayout'
import { shouldUseDesktopRuntime } from '@/utils/runtime.ts'
import { isDemoMode } from '@/demo/mode'
import DemoControlBar from '@/demo/DemoControlBar'
import { FeatureGuideProvider } from '@/demo/FeatureGuideContext'
import { FeatureGuideDrawer } from '@/demo/FeatureGuideDrawer'

// 工作区页面使用 React.lazy 按需加载，避免 Markdown/Markmap 等重依赖阻塞 /new 首屏
const HomePage = lazy(() => import('./pages/HomePage/Home.tsx'))
const SettingPage = lazy(() => import('./pages/SettingPage/index.tsx'))
const SettingsHome = lazy(() => import('@/pages/SettingPage/SettingsHome.tsx'))
const Model = lazy(() => import('@/pages/SettingPage/Model.tsx'))
const ProviderForm = lazy(() => import('@/components/Form/modelForm/Form.tsx'))
const Monitor = lazy(() => import('@/pages/SettingPage/Monitor.tsx'))
const Usage = lazy(() => import('@/pages/SettingPage/Usage.tsx'))
const Downloader = lazy(() => import('@/pages/SettingPage/Downloader.tsx'))
const DownloaderForm = lazy(() => import('@/components/Form/DownloaderForm/Form.tsx'))
const TranscriberPage = lazy(() => import('@/pages/SettingPage/transcriber.tsx'))
const DataMigration = lazy(() => import('@/pages/SettingPage/DataMigration.tsx'))
const McpServers = lazy(() => import('@/pages/SettingPage/McpServers.tsx'))
const ResearchSearch = lazy(() => import('@/pages/SettingPage/ResearchSearch.tsx'))
const Plugins = lazy(() => import('@/pages/SettingPage/Plugins.tsx'))
const ApplicationSettings = lazy(() => import('@/pages/SettingPage/Applications.tsx'))
const AgentDiagnostics = lazy(() => import('@/pages/SettingPage/AgentDiagnostics.tsx'))
const Candidates = lazy(() => import('@/pages/SettingPage/Candidates.tsx'))
const CapabilityCenter = lazy(() => import('@/pages/CapabilityCenter'))
const ApplicationHost = lazy(() => import('@/app-host/ApplicationHost').then(module => ({ default: module.ApplicationHost })))
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'))
const CloudPage = lazy(() => import('@/pages/CloudPage'))
const InvitationPage = lazy(() => import('@/pages/InvitationPage'))
const MobilePage = lazy(() => import('@/pages/MobilePage'))
const AppsHub = lazy(() => import('@/pages/Applications/AppsHub'))
const NotesApp = lazy(() => import('@/pages/Applications/NotesApp'))
const MonitoringApp = lazy(() => import('@/pages/Applications/MonitoringApp'))
const LearningApp = lazy(() => import('@/pages/Applications/LearningApp'))
const RuntimeApp = lazy(() => import('@/pages/Applications/RuntimeApp'))

const WorkspaceLayout = () => (
  <AppLayout>
    <Outlet />
  </AppLayout>
)

const ApplicationHostRoute = () => {
  const { appId } = useParams<{ appId: string }>()
  return <ApplicationHost applicationId={appId ?? ''} />
}

const PublicLandingRoutes = () => (
  <Routes>
    <Route path="/" element={<Navigate to="/new" replace />} />
    <Route path="*" element={<Navigate to="/new" replace />} />
  </Routes>
)

const WorkspaceRoutes = () => {
  const { backendReady } = useBackendInitContext()
  const shouldPollTasks = true
  useTaskPolling(3000, shouldPollTasks && backendReady)

  return (
    <Suspense fallback={<div className="flex h-app items-center justify-center">加载中…</div>}>
      <Routes>
        <Route path="/" element={<Navigate to="/new" replace />} />

        <Route element={<WorkspaceLayout />}>
          <Route path="/new" element={<HomePage />} />
          <Route path="/notes/:taskId" element={<HomePage />} />
          <Route path="/styles" element={<Navigate to="/new" replace />} />
          <Route path="/applications" element={<CapabilityCenter />} />
          <Route path="/applications/:appId" element={<ApplicationHostRoute />} />
          <Route path="/apps" element={<AppsHub />} />
          <Route path="/apps/notes" element={<NotesApp />} />
          <Route path="/apps/learning" element={<LearningApp />} />
          <Route path="/apps/monitoring" element={<MonitoringApp />} />
          <Route path="/apps/runtime" element={<RuntimeApp />} />
          <Route path="/about" element={<Navigate to="/new" replace />} />
        <Route path="/cloud" element={<CloudPage />} />
        <Route path="/invite/:token" element={<InvitationPage />} />
          <Route path="/settings" element={<SettingPage />}>
            <Route index element={<SettingsHome />} />
            <Route path="model" element={<Model />}>
              <Route path="new" element={<ProviderForm isCreate />} />
              <Route path=":id" element={<ProviderForm />} />
            </Route>
            <Route path="download" element={<Downloader />}>
              <Route path=":id" element={<DownloaderForm />} />
            </Route>
            <Route path="transcriber" element={<TranscriberPage />} />
            <Route path="data-migration" element={<DataMigration />} />
            <Route path="usage" element={<Usage />}></Route>
            <Route path="monitor" element={<Monitor />}></Route>
            <Route path="mcp-servers" element={<McpServers />} />
            <Route path="research-search" element={<ResearchSearch />} />
            <Route path="plugins" element={<Plugins />} />
            <Route path="applications" element={<ApplicationSettings />} />
            <Route path="agent-diagnostics" element={<AgentDiagnostics />} />
            <Route path="candidates" element={<Candidates />} />
            <Route path="about" element={<Navigate to="/" replace />}></Route>
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Route>

        <Route path="/mobile/*" element={<MobilePage />} />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  )
}

const WorkspaceApp = () => {
  const { backendReady, phase, failureKind, checkNow } = useBackendInitContext()
  const [dialogDismissed, setDialogDismissed] = useState(false)

  // 在后端初始化完成后执行系统检查
  useEffect(() => {
    if (backendReady) {
      systemCheck()
    }
  }, [backendReady])

  useEffect(() => {
    if (!failureKind) {
      setDialogDismissed(false)
    }
  }, [failureKind])

  const handleRetry = () => {
    setDialogDismissed(true)
    void checkNow()
  }

  const handleClose = () => {
    setDialogDismissed(true)
  }

  return (
    <>
      <WorkspaceRoutes />
      <BackendInitDialog
        open={!!failureKind && !dialogDismissed}
        phase={phase}
        failureKind={failureKind ?? undefined}
        onRetry={handleRetry}
        onClose={handleClose}
      />
      {isDemoMode() && <DemoControlBar />}
      {isDemoMode() && <FeatureGuideDrawer />}
    </>
  )
}

const AppRouter = () => {
  const location = useLocation()
  const isPublicLanding = location.pathname === '/'

  if (isPublicLanding) {
    return <PublicLandingRoutes />
  }

  return <WorkspaceApp />
}

function App() {
  const RouterComponent = shouldUseDesktopRuntime() ? HashRouter : BrowserRouter

  return (
    <BackendInitProvider>
      <RouterComponent>
        <FeatureGuideProvider>
          <AppRouter />
        </FeatureGuideProvider>
      </RouterComponent>
    </BackendInitProvider>
  )
}

export default App
