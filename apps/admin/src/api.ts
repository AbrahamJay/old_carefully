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

// ------------------------------------------------------------ Agent 管理端
export type AgentSource = 'llm' | 'cache' | 'rule'

export interface AgentStatus {
  enabled: boolean
  provider: string
  model: string
  daily_limit: number
  used_today: number
  remaining: number
  prep_brief_enabled: boolean
  admin_scenarios: string[]
  admin_daily_limit: number
  admin_remaining: number
}

export interface DispatchSuggest {
  order_id: number
  recommendation: { staff_id: number; name: string; score: number } | null
  summary: string
  why: string[]
  risks: string[]
  data_gaps: string[]
  alternatives: { staff_id: number; name: string; note: string }[]
  excluded: { name: string; reasons: string[] }[]
  source: AgentSource
  warnings: string[]
  trace_id: string
  model: string
  latency_ms: number
  facts_hash: string
  generated_at: string
}

export interface TaskExplain {
  task_id: number
  type: string
  title: string
  what_happened: string
  why: string
  next_actions: { action: string; label: string }[]
  escalate: boolean
  data_gaps: string[]
  source: AgentSource
  warnings: string[]
  trace_id: string
  model: string
  latency_ms: number
  facts_hash: string
  generated_at: string
}

/** 当前账号能否用 AI、今天还剩多少次；管理端场景单独下发 */
export function agentStatus(): Promise<AgentStatus> {
  return request('/agent/status')
}

/** 派单说明：人仍由规则选定，这里只取解释文案 */
export function dispatchSuggest(orderId: number, forceRefresh = false): Promise<DispatchSuggest> {
  return request('/agent/admin/dispatch-suggest', {
    method: 'POST',
    body: { order_id: orderId, force_refresh: forceRefresh },
  })
}

/** 异常解释：动作取自后端白名单，前端只负责展示 */
export function taskExplain(taskId: number, forceRefresh = false): Promise<TaskExplain> {
  return request('/agent/admin/task-explain', {
    method: 'POST',
    body: { task_id: taskId, force_refresh: forceRefresh },
  })
}
