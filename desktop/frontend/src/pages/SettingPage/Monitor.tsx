import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
    Server,
    Cpu,
    AudioLines,
    Film,
    RefreshCw,
    CheckCircle2,
    XCircle,
    Loader2,
    Blocks,
    Copy,
    Power
} from 'lucide-react'
import { useState, useEffect, useCallback } from 'react'
import { getDeployStatus, recheckMcpStatus, DeployStatus } from '@/services/system'
import { get_autostart_enabled, set_autostart_enabled } from '@/services/desktopRuntime'

export default function Monitor() {
    const [status, setStatus] = useState<DeployStatus | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
    const [mcpRefreshing, setMcpRefreshing] = useState(false)
    const [autostartEnabled, setAutostartEnabled] = useState(false)
    const [autostartLoading, setAutostartLoading] = useState(false)

    const fetchStatus = useCallback(async () => {
        try {
            setLoading(true)
            setError(null)
            const data = await getDeployStatus()
            setStatus(data)
            setLastUpdated(new Date())
        } catch {
            setError('无法连接到后端服务')
            setStatus(null)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchStatus()
        // 自动刷新（每 30 秒）
        const interval = setInterval(fetchStatus, 30000)
        return () => clearInterval(interval)
    }, [fetchStatus])

    useEffect(() => {
        get_autostart_enabled()
            .then(setAutostartEnabled)
            .catch(() => setAutostartEnabled(false))
    }, [])

    const StatusBadge = ({ ok, label }: { ok: boolean; label?: string }) => (
        <Badge
            variant={ok ? 'default' : 'destructive'}
            className={ok ? 'bg-green-500 hover:bg-green-600' : ''}
        >
            {ok ? (
                <><CheckCircle2 className="mr-1 h-3 w-3" />{label || '正常'}</>
            ) : (
                <><XCircle className="mr-1 h-3 w-3" />{label || '异常'}</>
            )}
        </Badge>
    )

    const handleCopyMcpUrl = useCallback(async () => {
        const url = status?.mcp?.url || 'http://127.0.0.1:8483/mcp'
        await navigator.clipboard.writeText(url)
    }, [status?.mcp?.url])

    const handleRecheckMcp = useCallback(async () => {
        try {
            setMcpRefreshing(true)
            const mcp = await recheckMcpStatus()
            setStatus(prev => prev ? { ...prev, mcp } : prev)
            setLastUpdated(new Date())
        } finally {
            setMcpRefreshing(false)
        }
    }, [])

    const handleToggleAutostart = useCallback(async () => {
        const next = !autostartEnabled
        try {
            setAutostartLoading(true)
            await set_autostart_enabled(next)
            setAutostartEnabled(next)
        } finally {
            setAutostartLoading(false)
        }
    }, [autostartEnabled])

    return (
        <ScrollArea className="h-full overflow-y-auto bg-white">
            <div className="container mx-auto px-4 py-8">
                {/* Header */}
                <div className="mb-8 flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold">部署监控</h1>
                        <p className="text-muted-foreground text-sm">
                            实时监控系统各组件运行状态
                        </p>
                    </div>
                    <div className="flex items-center gap-4">
                        {lastUpdated && (
                            <span className="text-muted-foreground text-xs">
                                最后更新: {lastUpdated.toLocaleTimeString()}
                            </span>
                        )}
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={fetchStatus}
                            disabled={loading}
                        >
                            {loading ? (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            ) : (
                                <RefreshCw className="mr-2 h-4 w-4" />
                            )}
                            刷新
                        </Button>
                    </div>
                </div>

                {error && (
                    <div className="mb-6 rounded-lg border border-red-200 bg-red-50 p-4 text-red-700">
                        {error}
                    </div>
                )}

                {/* Status Cards */}
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                    {/* Backend FastAPI */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-lg font-medium">
                                <Server className="mr-2 inline h-5 w-5 text-blue-500" />
                                后端 FastAPI
                            </CardTitle>
                            {status && <StatusBadge ok={status.backend.status === 'running'} label="运行中" />}
                        </CardHeader>
                        <CardContent>
                            {loading && !status ? (
                                <div className="flex items-center gap-2 text-gray-500">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    加载中...
                                </div>
                            ) : status ? (
                                <div className="space-y-2 text-sm">
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">状态:</span>
                                        <span className={status.backend.status === 'running' ? 'font-medium text-green-600' : 'font-medium text-red-600'}>
                                            {status.backend.status === 'running' ? '运行中' : status.backend.status}
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">端口:</span>
                                        <span className="font-mono">{status.backend.port}</span>
                                    </div>
                                </div>
                            ) : null}
                        </CardContent>
                    </Card>

                    {/* CUDA GPU */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-lg font-medium">
                                <Cpu className="mr-2 inline h-5 w-5 text-green-500" />
                                CUDA GPU
                            </CardTitle>
                            {status && <StatusBadge ok={status.cuda.available} label={status.cuda.available ? '已启用' : '未启用'} />}
                        </CardHeader>
                        <CardContent>
                            {loading && !status ? (
                                <div className="flex items-center gap-2 text-gray-500">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    加载中...
                                </div>
                            ) : status ? (
                                <div className="space-y-2 text-sm">
                                    {status.cuda.available ? (
                                        <>
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">GPU:</span>
                                                <span className="font-medium">{status.cuda.gpu_name}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span className="text-muted-foreground">CUDA 版本:</span>
                                                <span className="font-mono">{status.cuda.version}</span>
                                            </div>
                                        </>
                                    ) : (
                                        <div className="text-muted-foreground">
                                            CUDA 不可用，将使用 CPU 模式
                                        </div>
                                    )}
                                </div>
                            ) : null}
                        </CardContent>
                    </Card>

                    {/* Whisper Model */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-lg font-medium">
                                <AudioLines className="mr-2 inline h-5 w-5 text-purple-500" />
                                Whisper 模型
                            </CardTitle>
                            {status && <StatusBadge ok={true} label="已配置" />}
                        </CardHeader>
                        <CardContent>
                            {loading && !status ? (
                                <div className="flex items-center gap-2 text-gray-500">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    加载中...
                                </div>
                            ) : status ? (
                                <div className="space-y-2 text-sm">
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">模型大小:</span>
                                        <span className="font-medium">{status.whisper.model_size}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">转写引擎:</span>
                                        <span className="font-mono">{status.whisper.transcriber_type}</span>
                                    </div>
                                </div>
                            ) : null}
                        </CardContent>
                    </Card>

                    {/* FFmpeg */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-lg font-medium">
                                <Film className="mr-2 inline h-5 w-5 text-orange-500" />
                                FFmpeg
                            </CardTitle>
                            {status && <StatusBadge ok={status.ffmpeg.available} label={status.ffmpeg.available ? '可用' : '不可用'} />}
                        </CardHeader>
                        <CardContent>
                            {loading && !status ? (
                                <div className="flex items-center gap-2 text-gray-500">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    加载中...
                                </div>
                            ) : status ? (
                                <div className="space-y-2 text-sm">
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">状态:</span>
                                        <span className={status.ffmpeg.available ? 'font-medium text-green-600' : 'font-medium text-red-600'}>
                                            {status.ffmpeg.available ? '已安装' : '未安装'}
                                        </span>
                                    </div>
                                    {!status.ffmpeg.available && (
                                        <div className="text-xs text-red-500">
                                            请安装 FFmpeg 并添加到系统 PATH
                                        </div>
                                    )}
                                </div>
                            ) : null}
                        </CardContent>
                    </Card>

                    {/* MCP */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-lg font-medium">
                                <Blocks className="mr-2 inline h-5 w-5 text-indigo-500" />
                                MCP 服务
                            </CardTitle>
                            {status && <StatusBadge ok={status.mcp.status === 'running'} label={status.mcp.status === 'running' ? '运行中' : '异常'} />}
                        </CardHeader>
                        <CardContent>
                            {loading && !status ? (
                                <div className="flex items-center gap-2 text-gray-500">
                                    <Loader2 className="h-4 w-4 animate-spin" />
                                    加载中...
                                </div>
                            ) : status ? (
                                <div className="space-y-3 text-sm">
                                    <div className="flex justify-between gap-4">
                                        <span className="text-muted-foreground">地址:</span>
                                        <span className="break-all font-mono text-xs">{status.mcp.url || 'http://127.0.0.1:8483/mcp'}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">端口:</span>
                                        <span className="font-mono">{status.mcp.port || 8483}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">工具数:</span>
                                        <span className="font-medium">{status.mcp.tools_count}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-muted-foreground">鉴权:</span>
                                        <span>{status.mcp.auth_required ? 'Token 已启用' : '本地免 Token'}</span>
                                    </div>
                                    {status.mcp.error && (
                                        <div className="text-xs text-red-500">
                                            {status.mcp.error}
                                        </div>
                                    )}
                                    <div className="flex gap-2">
                                        <Button variant="outline" size="sm" onClick={handleCopyMcpUrl}>
                                            <Copy className="mr-2 h-3 w-3" />
                                            复制地址
                                        </Button>
                                        <Button variant="outline" size="sm" onClick={handleRecheckMcp} disabled={mcpRefreshing}>
                                            {mcpRefreshing ? (
                                                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                                            ) : (
                                                <RefreshCw className="mr-2 h-3 w-3" />
                                            )}
                                            刷新状态
                                        </Button>
                                    </div>
                                </div>
                            ) : null}
                        </CardContent>
                    </Card>

                    {/* Autostart */}
                    <Card>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-lg font-medium">
                                <Power className="mr-2 inline h-5 w-5 text-cyan-500" />
                                开机自动启动 NoteMeld
                            </CardTitle>
                            <StatusBadge ok={autostartEnabled} label={autostartEnabled ? '已开启' : '未开启'} />
                        </CardHeader>
                        <CardContent>
                            <div className="space-y-3 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-muted-foreground">状态:</span>
                                    <span className={autostartEnabled ? 'font-medium text-green-600' : 'font-medium text-red-600'}>
                                        {autostartEnabled ? '登录后自动启动' : '未设置'}
                                    </span>
                                </div>
                                <div className="text-xs text-muted-foreground">
                                    开启后会在 macOS 登录时自动打开 NoteMeld，并启动本地后端和 MCP 服务。
                                </div>
                                <Button
                                    variant={autostartEnabled ? 'default' : 'outline'}
                                    size="sm"
                                    onClick={handleToggleAutostart}
                                    disabled={autostartLoading}
                                >
                                    {autostartLoading && <Loader2 className="mr-2 h-3 w-3 animate-spin" />}
                                    {autostartEnabled ? '关闭开机启动' : '开启开机启动'}
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </div>

                {/* Footer Info */}
                <div className="mt-8 text-center text-xs text-gray-400">
                    状态每 30 秒自动刷新
                </div>
            </div>
        </ScrollArea>
    )
}
