import ProviderCard from '@/components/Form/modelForm/components/providerCard.tsx'
import { Button } from '@/components/ui/button.tsx'
import { useProviderStore } from '@/store/providerStore'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import toast from 'react-hot-toast'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import { decodeModelShare, type DecodedModelShare } from '@/services/model'

const Provider = () => {
  const providers = useProviderStore(state => state.provider)
  const navigate = useNavigate()
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [importing, setImporting] = useState(false)

  const handleImport = async () => {
    const text = importText.trim()
    if (!text) {
      toast.error('请粘贴模型配置链接或 JSON')
      return
    }
    try {
      setImporting(true)
      // 后端校验：拒绝配对码、夹带密钥与非法 schema，不触网
      const decoded: DecodedModelShare = await decodeModelShare(text)
      setImportOpen(false)
      setImportText('')
      // imported 态预填表单，不自动保存
      navigate('/settings/model/new', { state: { importedShare: decoded } })
    } catch (error: unknown) {
      const message =
        typeof error === 'object' && error !== null && 'response' in error
          ? (error as { response?: { data?: { msg?: string } } }).response?.data?.msg
          : undefined
      toast.error(`导入失败：${message || '配置内容不合法'}`)
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="search grid grid-cols-2 gap-1 py-1.5">
        <Button
          type={'button'}
          onClick={() => {
            navigate(`/settings/model/new`)
          }}
        >
          添加模型供应商
        </Button>
        <Button
          type={'button'}
          variant="outline"
          data-import-config
          onClick={() => setImportOpen(true)}
        >
          导入配置
        </Button>
      </div>
      <div className="text-sm font-medium text-on-surface-variant">模型供应商列表</div>
      <div className="flex gap-2 overflow-x-auto pb-1 md:flex-col md:overflow-visible md:pb-0">
        {providers &&
          providers.map(provider => {
            return <ProviderCard key={provider.id} provider={provider} />
          })}
      </div>

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>导入模型配置</DialogTitle>
            <DialogDescription>
              粘贴 notemeld://model-add 配置链接或配置 JSON。导入仅预填表单，不会自动保存；
              配置不含也不接受任何 API 密钥。
            </DialogDescription>
          </DialogHeader>
          <Textarea
            data-import-text
            value={importText}
            onChange={event => setImportText(event.target.value)}
            placeholder="notemeld://model-add?d=..."
            className="min-h-32"
          />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setImportOpen(false)} disabled={importing}>
              取消
            </Button>
            <Button type="button" onClick={handleImport} disabled={importing}>
              {importing ? '校验中...' : '解析并预填'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
export default Provider
