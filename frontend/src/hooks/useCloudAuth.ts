import { useCallback, useEffect, useState } from 'react'
import CloudClient from '../services/cloud'

export function useCloudAuth(client: CloudClient) {
  const [token, setToken] = useState<string | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => { let active = true; void client.hydrateToken().then(value => { if (active) setToken(value) }).finally(() => { if (active) setLoading(false) }); return () => { active = false } }, [client])
  const login = useCallback(async (password: string, username: string) => { const result = await client.login(password, username); setToken(result.token); setRole(result.role); return result }, [client])
  const logout = useCallback(async () => { if (token) await client.revokeCurrentToken(); else client.setToken(null); setToken(null); setRole(null) }, [client, token])
  return { authenticated: Boolean(token), token, role, loading, login, logout }
}
