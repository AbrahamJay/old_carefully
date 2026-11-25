import { auth, clearAuth } from '../stores/auth'

const BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

interface RequestOptions {
  method?: string
  body?: unknown
  auth?: boolean
}

export async function request<T = any>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (options.auth !== false && auth.token) headers.Authorization = 'Bearer ' + auth.token
  const res = await fetch(BASE + path, {
    method: options.method || 'GET',
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body)
  })
  let data: any = null
  try { data = await res.json() } catch { data = null }
  if (res.status === 401) {
    clearAuth()
    if (!location.pathname.endsWith('/login')) {
      location.href = import.meta.env.BASE_URL + 'login'
    }
    throw new ApiError('登录已过期，请重新登录', 401)
  }
  if (!res.ok) {
    const detail = data && (data.detail || data.message)
    throw new ApiError(typeof detail === 'string' ? detail : '请求失败', res.status)
  }
  return data as T
}

export function get<T = any>(path: string) { return request<T>(path) }
export function post<T = any>(path: string, body?: unknown) { return request<T>(path, { method: 'POST', body }) }
export function patch<T = any>(path: string, body?: unknown) { return request<T>(path, { method: 'PATCH', body }) }

export async function login(phone: string, password: string) {
  return request<{ access_token: string; user: any }>('/auth/login', {
    method: 'POST',
    auth: false,
    body: { phone, password }
  })
}

export async function upload(file: File): Promise<{ url: string; key: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(BASE + '/uploads', {
    method: 'POST',
    headers: auth.token ? { Authorization: 'Bearer ' + auth.token } : {},
    body: form
  })
  let data: any = null
  try { data = await res.json() } catch { data = null }
  if (!res.ok) {
    const detail = data && (data.detail || data.message)
    throw new ApiError(typeof detail === 'string' ? detail : '上传失败', res.status)
  }
  return data
}
