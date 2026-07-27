import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useProviderStore } from '@/store/providerStore'
import {
  getUsageOverview,
  getUsageRecords,
  type UsageFilters,
  type UsageOverview,
  type UsageRecord,
} from '@/services/usage'

const emptyOverview: UsageOverview = {
  prompt_tokens: 0,
  completion_tokens: 0,
  total_tokens: 0,
  call_count: 0,
  task_count: 0,
}

const formatDateTime = (value?: string) => {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export default function Usage() {
  const providerList = useProviderStore(state => state.provider ?? [])
  const [loading, setLoading] = useState(false)
  const [overview, setOverview] = useState<UsageOverview>(emptyOverview)
  const [records, setRecords] = useState<UsageRecord[]>([])
  const [filters, setFilters] = useState<UsageFilters>({
    start_at: '',
    end_at: '',
    task_id: '',
    provider_id: '',
    model_name: '',
    status: '',
  })

  const normalizedFilters = useMemo(() => {
    return Object.fromEntries(
      Object.entries(filters).filter(([, value]) => value !== undefined && value !== '')
    ) as UsageFilters
  }, [filters])

  const loadUsage = useCallback(async () => {
    setLoading(true)
    try {
      const [overviewData, recordData] = await Promise.all([
        getUsageOverview(normalizedFilters),
        getUsageRecords(normalizedFilters),
      ])
      setOverview(overviewData ?? emptyOverview)
      setRecords(Array.isArray(recordData) ? recordData : [])
    } finally {
      setLoading(false)
    }
  }, [normalizedFilters])

  useEffect(() => {
    loadUsage()
  }, [loadUsage])

  return (
    <div className="h-full overflow-y-auto bg-white p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Token 消耗</h1>
        <p className="text-muted-foreground mt-1 text-sm">查看模型调用明细，以及按任务聚合后的 token 消耗。</p>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-neutral-500">总 Token</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{overview.total_tokens}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-neutral-500">输入 Token</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{overview.prompt_tokens}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-neutral-500">输出 Token</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{overview.completion_tokens}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-neutral-500">调用次数</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{overview.call_count}</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-neutral-500">任务数</CardTitle>
          </CardHeader>
          <CardContent className="text-2xl font-semibold">{overview.task_count}</CardContent>
        </Card>
      </div>

      <Card className="mb-6">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">筛选</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-6">
          <Input
            type="datetime-local"
            value={filters.start_at}
            onChange={e => setFilters(prev => ({ ...prev, start_at: e.target.value }))}
          />
          <Input
            type="datetime-local"
            value={filters.end_at}
            onChange={e => setFilters(prev => ({ ...prev, end_at: e.target.value }))}
          />
          <Input
            placeholder="任务 ID"
            value={filters.task_id}
            onChange={e => setFilters(prev => ({ ...prev, task_id: e.target.value }))}
          />
          <select
            className="rounded-md border border-neutral-200 px-3 py-2 text-sm outline-none"
            value={filters.provider_id}
            onChange={e => setFilters(prev => ({ ...prev, provider_id: e.target.value }))}
          >
            <option value="">全部供应商</option>
            {providerList.map(provider => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
              </option>
            ))}
          </select>
          <Input
            placeholder="模型名称"
            value={filters.model_name}
            onChange={e => setFilters(prev => ({ ...prev, model_name: e.target.value }))}
          />
          <select
            className="rounded-md border border-neutral-200 px-3 py-2 text-sm outline-none"
            value={filters.status}
            onChange={e => setFilters(prev => ({ ...prev, status: e.target.value }))}
          >
            <option value="">全部状态</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
          </select>
          <div className="md:col-span-2 xl:col-span-6 flex gap-2">
            <Button type="button" onClick={loadUsage} disabled={loading}>
              {loading ? '加载中...' : '查询'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                setFilters({
                  start_at: '',
                  end_at: '',
                  task_id: '',
                  provider_id: '',
                  model_name: '',
                  status: '',
                })
              }
            >
              重置
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">调用明细</CardTitle>
        </CardHeader>
        <CardContent>
          {records.length === 0 ? (
            <div className="text-sm text-neutral-500">暂无 token 记录</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b text-neutral-500">
                  <tr>
                    <th className="px-3 py-2">时间</th>
                    <th className="px-3 py-2">任务</th>
                    <th className="px-3 py-2">供应商</th>
                    <th className="px-3 py-2">模型</th>
                    <th className="px-3 py-2">阶段</th>
                    <th className="px-3 py-2">输入</th>
                    <th className="px-3 py-2">输出</th>
                    <th className="px-3 py-2">总计</th>
                    <th className="px-3 py-2">耗时</th>
                    <th className="px-3 py-2">状态</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map(record => (
                    <tr key={record.id} className="border-b last:border-b-0">
                      <td className="px-3 py-2">{formatDateTime(record.created_at)}</td>
                      <td className="max-w-[180px] px-3 py-2 text-xs">{record.task_id || '-'}</td>
                      <td className="px-3 py-2">{record.provider_name}</td>
                      <td className="max-w-[220px] px-3 py-2 text-xs">{record.model_name}</td>
                      <td className="px-3 py-2">{record.phase}</td>
                      <td className="px-3 py-2">{record.prompt_tokens}</td>
                      <td className="px-3 py-2">{record.completion_tokens}</td>
                      <td className="px-3 py-2 font-medium">{record.total_tokens}</td>
                      <td className="px-3 py-2">{record.duration_ms} ms</td>
                      <td className="px-3 py-2">
                        <span
                          className={
                            record.status === 'success'
                              ? 'rounded bg-green-100 px-2 py-0.5 text-xs text-green-700'
                              : 'rounded bg-red-100 px-2 py-0.5 text-xs text-red-700'
                          }
                          title={record.error_message || ''}
                        >
                          {record.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
