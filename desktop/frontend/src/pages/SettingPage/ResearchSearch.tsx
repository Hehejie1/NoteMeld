import { useEffect, useState } from 'react'
import { BookOpen, Github, Globe2, Loader2, Save } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useBackendInitContext } from '@/contexts/BackendInitContext'
import {
  getResearchSearchConfig,
  updateResearchSearchConfig,
  type ResearchSearchConfig,
} from '@/services/learning'

interface FormState extends ResearchSearchConfig {
  tavily_api_key: string
}

const emptyForm: FormState = {
  web_provider: 'disabled',
  searxng_endpoint: '',
  timeout_seconds: 15,
  tavily_api_key_set: false,
  github_token_set: false,
  tavily_api_key: '',
}

const ResearchSearch = () => {
  const { backendReady } = useBackendInitContext()
  const [form, setForm] = useState<FormState>(emptyForm)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!backendReady) return
    void getResearchSearchConfig()
      .then(config => setForm(current => ({ ...current, ...config })))
      .catch(() => toast.error('读取研究搜索配置失败'))
      .finally(() => setLoading(false))
  }, [backendReady])

  const save = async () => {
    setSaving(true)
    try {
      const updated = await updateResearchSearchConfig({
        web_provider: form.web_provider,
        searxng_endpoint: form.searxng_endpoint.trim(),
        timeout_seconds: form.timeout_seconds,
        ...(form.tavily_api_key.trim() ? { tavily_api_key: form.tavily_api_key.trim() } : {}),
      })
      setForm(current => ({
        ...current,
        ...updated,
        tavily_api_key: '',
      }))
      toast.success('研究搜索配置已保存')
    } catch {
      toast.error('保存研究搜索配置失败')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-72 items-center justify-center text-on-surface-variant">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        正在读取研究搜索配置…
      </div>
    )
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-5 pb-10">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">研究搜索</h1>
        <p className="mt-1 text-sm text-on-surface-variant">
          学习空间始终先使用 NoteMeld 本地内容，并默认搜索学术论文与 GitHub 项目；这里只配置可选的普通网页搜索。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>默认研究来源</CardTitle>
          <CardDescription>无需配置或开启，学习模式会自动使用以下来源。</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-2">
          <div className="flex items-start gap-3 rounded-lg border p-4">
            <BookOpen className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <div>
              <div className="text-sm font-medium">学术论文</div>
              <p className="mt-1 text-sm text-on-surface-variant">自动查询 arXiv，保留作者、摘要、时间与版本。</p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-lg border p-4">
            <Github className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <div>
              <div className="text-sm font-medium">GitHub 项目</div>
              <p className="mt-1 text-sm text-on-surface-variant">无需配置，自动查询相关仓库、README 和工程元数据。</p>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Globe2 className="h-5 w-5 text-primary" />普通网页搜索</CardTitle>
          <CardDescription>
            密钥只保存在本机配置中，读取时仅返回是否已配置，不会回显原值。
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="web-provider">通用网页提供方</Label>
            <select
              id="web-provider"
              value={form.web_provider}
              onChange={event => setForm(current => ({ ...current, web_provider: event.target.value }))}
              className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            >
              <option value="disabled">不启用</option>
              <option value="searxng">SearXNG</option>
              <option value="tavily">Tavily</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="timeout">请求超时（秒）</Label>
            <Input
              id="timeout"
              type="number"
              min={5}
              max={30}
              value={form.timeout_seconds}
              onChange={event =>
                setForm(current => ({ ...current, timeout_seconds: Number(event.target.value) || 15 }))
              }
            />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="searxng-endpoint">SearXNG 地址</Label>
            <Input
              id="searxng-endpoint"
              type="url"
              placeholder="https://search.example.com"
              value={form.searxng_endpoint}
              onChange={event =>
                setForm(current => ({ ...current, searxng_endpoint: event.target.value }))
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="tavily-key">Tavily API Key</Label>
            <Input
              id="tavily-key"
              type="password"
              autoComplete="new-password"
              placeholder={form.tavily_api_key_set ? '已配置；留空则保持不变' : '可选'}
              value={form.tavily_api_key}
              onChange={event => setForm(current => ({ ...current, tavily_api_key: event.target.value }))}
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={() => void save()} disabled={saving}>
          {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
          保存配置
        </Button>
      </div>
    </div>
  )
}

export default ResearchSearch
