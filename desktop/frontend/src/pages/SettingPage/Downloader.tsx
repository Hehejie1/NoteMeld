import { Outlet } from 'react-router-dom'
import Options from '@/components/Form/DownloaderForm/Options.tsx'
const Downloader = () => {
  return (
    <div className="flex h-full min-h-0 min-w-0 bg-surface-container-lowest">
      <div className="min-h-0 min-w-0 w-1/5 shrink-0 overflow-y-auto border-r border-border-subtle bg-surface-container-lowest p-2">
        <Options></Options>
      </div>
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}
export default Downloader
