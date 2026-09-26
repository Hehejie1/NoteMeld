import Provider from '@/components/Form/modelForm/Provider.tsx'
import { Outlet } from 'react-router-dom'

const Model = () => {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-surface-container-lowest md:flex-row">
      <div className="min-w-0 shrink-0 border-b border-border-subtle p-3 md:min-h-0 md:w-64 md:overflow-y-auto md:border-r md:border-b-0 md:p-2">
        <Provider></Provider>
      </div>
      <div className="min-h-0 min-w-0 flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  )
}
export default Model
