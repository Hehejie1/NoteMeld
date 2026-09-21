import { useCallback, useEffect, useState } from 'react'
import CloudClient from '../services/cloud'

export interface CloudLoginResult { token: string; user_id: string; role: string }

export function useCloudAuth(client: CloudClient) {
  const [token, setToken] = useState<string | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => { let active = true; void client.hydrateToken().then(async value => { if (!value) return; try { const identity = await client.me(); if (active) { setToken(value); setRole(identity.role) } } catch { await client.clearToken() } }).finally(() => { if (active) setLoading(false) }); return () => { active = false } }, [client])
  const login = useCallback(async (password: string, username: string) => { const result = await client.login(password, username); setToken(result.token); setRole(result.role); return result }, [client])
  const acceptLogin = useCallback((result: CloudLoginResult) => { setToken(result.token); setRole(result.role) }, [])
  const logout = useCallback(async () => {
    try {
      if (token) await client.revokeCurrentToken()
      else client.setToken(null)
    } catch {
      // token 可能已被后端吊销（如修改密码），仍需清理本地登录态。
      client.setToken(null)
    } finally {
      setToken(null)
      setRole(null)
    }
  }, [client, token])
  return { authenticated: Boolean(token), token, role, loading, login, acceptLogin, logout }
}
