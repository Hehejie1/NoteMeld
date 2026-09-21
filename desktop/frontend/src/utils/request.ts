import axios, { AxiosInstance, AxiosResponse, type AxiosRequestHeaders } from 'axios';
import toast from 'react-hot-toast'
import { getRuntimeApiBaseUrl, getRuntimeSessionToken } from './runtime';
import { isDemoMode } from '@/demo/mode'
import { createDemoAxiosAdapter } from '@/demo/transport'

// 统一响应类型
export interface IResponse<T = unknown> {
  code: number;
  msg: string;
  detail?: unknown;
  data: T;
}

// 模拟一个消息提示函数 (实际项目中会使用UI库的组件，如 Ant Design 的 message 或 Element UI 的 ElMessage)
// This function simulates a message display (in real projects, you'd use a UI library's component)

function resolveApiBaseUrl() {
  return getRuntimeApiBaseUrl() || import.meta.env.VITE_API_BASE_URL || '/api';
}

function formatErrorDetail(detail: unknown): string {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map(item => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object') {
          const value = item as { loc?: unknown; msg?: unknown }
          const loc = Array.isArray(value.loc) ? value.loc.join('.') : ''
          const msg = typeof value.msg === 'string' ? value.msg : JSON.stringify(item)
          return loc ? `${loc}: ${msg}` : msg
        }
        return String(item)
      })
      .filter(Boolean)
      .join('\n')
  }
  if (typeof detail === 'object') {
    return JSON.stringify(detail)
  }
  return String(detail)
}

export function formatErrorMessage(payload: Partial<IResponse> | undefined, fallback: string): string {
  const msg = typeof payload?.msg === 'string' ? payload.msg : ''
  const detail = formatErrorDetail(payload?.detail)
  return msg || detail || fallback
}

// 创建实例
 const request: AxiosInstance = axios.create({
  timeout: 10000,
  ...(isDemoMode() ? { adapter: createDemoAxiosAdapter() } : {}),
});

request.interceptors.request.use(config => {
  config.baseURL = resolveApiBaseUrl()
  const sessionToken = getRuntimeSessionToken()
  if (sessionToken) {
    config.headers = {
      ...(config.headers as Record<string, unknown> | undefined),
      'X-NoteMeld-Session': sessionToken,
    } as unknown as AxiosRequestHeaders
  }
  return config
})

// 响应拦截器
request.interceptors.response.use(
  ((response: AxiosResponse<IResponse>) => {
    const res = response.data;
    if (res.code === 0) {
      // 业务成功，可以根据需要显示成功消息，或者不显示（如果操作本身就是可见的）
      // showMessage('success', res.msg || '操作成功'); // 如果需要显示成功消息
      return res.data; // 返回data部分，简化后续业务代码
    } else {
      // 业务错误，统一显示后端返回的错误消息
      // Business error, uniformly display the error message returned from the backend
      const message = formatErrorMessage(res, '操作失败，请稍后再试')
      toast.error(message);
      return Promise.reject({ ...res, detail: formatErrorDetail(res.detail), msg: message }); // 拒绝Promise，让业务代码可以捕获并处理
    }
  }) as never,
  (error) => {
    // 网络/服务器错误
    const res = error?.response?.data as IResponse | undefined;
    if (res) {
      // 如果后端有返回错误信息，则显示后端信息
      // If the backend returns an error message, display it

      const message = formatErrorMessage(res, '服务器错误，请稍后再试')
      toast.error(message);
      return Promise.reject({ ...res, detail: formatErrorDetail(res.detail), msg: message });
    } else {
      // 没有响应数据（如网络中断），显示通用网络错误
      // No response data (e.g., network disconnected), display generic network error
      toast.error( '请求失败，请检查网络连接或稍后再试')
      return Promise.reject({
        code: -1,
        msg: '请求失败，请检查网络连接',
        data: null
      } as IResponse);
    }
  }
);

export default request
