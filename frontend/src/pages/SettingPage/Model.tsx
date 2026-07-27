import Provider from '@/components/Form/modelForm/Provider.tsx'
import { Outlet } from 'react-router-dom'

const Model = () => {
  return (
    <div className="flex h-full min-h-0 flex-col bg-white md:flex-row">
      <div className="shrink-0 border-b border-neutral-200 p-3 md:min-h-0 md:w-64 md:overflow-y-auto md:border-r md:border-b-0 md:p-2">
        <Provider></Provider>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <Outlet />
      </div>
    </div>
  )
}
export default Model
