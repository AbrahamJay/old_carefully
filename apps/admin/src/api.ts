const BASE = '/api/v1'

export interface ApiUser {
  id: number
  name: string
  phone?: string
  role: string
}

export function getToken(): string {
  return localStorage.getItem('token') || ''
}

export function getUser(): ApiUser | null {
  const raw = localStorage.getItem('user')
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

export function clearLogin() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
}

export async function request(path: string, options: any = {}): Promise<any> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(options.headers || {}) }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const init: RequestInit = { method: options.method || 'GET', headers }
  if (options.body !== undefined) init.body = JSON.stringify(options.body)
  const res = await fetch(BASE + path, init)
  let data: any = null
  try { data = await res.json() } catch { data = null }
  if (res.status === 401) {
    const detail = data && (data.detail || data.message)
    // 登录页的 401 是“账号或密码错误”，不要清空并跳登录页，也不要用“未登录”盖掉原因
    if (location.pathname === '/login' || path === '/auth/admin/login') {
      throw new Error(typeof detail === 'string' ? detail : '账号或密码错误')
    }
    clearLogin()
    if (location.pathname !== '/login') location.href = '/login'
    throw new Error('登录已过期，请重新登录')
  }
  if (!res.ok) {
    const detail = data && (data.detail || data.message)
    throw new Error(typeof detail === 'string' ? detail : '请求失败')
  }
  return data
}

export async function login(username: string, password: string) {
  const data = await request('/auth/admin/login', { method: 'POST', body: { username, password } })
  localStorage.setItem('token', data.access_token)
  localStorage.setItem('user', JSON.stringify(data.user))
  return data.user
}

export function logout() {
  clearLogin()
  location.href = '/login'
}
