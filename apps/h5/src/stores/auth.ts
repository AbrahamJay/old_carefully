import { reactive } from 'vue'

export interface SessionUser {
  id: number
  name: string
  phone?: string
  role: string
  station_id?: number | null
  station_name?: string
}

function readUser(): SessionUser | null {
  try {
    const raw = localStorage.getItem('h5_user')
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export const auth = reactive({
  token: localStorage.getItem('h5_token') || '',
  user: readUser() as SessionUser | null
})

export function setLogin(data: { access_token: string; user: SessionUser }) {
  auth.token = data.access_token
  auth.user = data.user
  localStorage.setItem('h5_token', data.access_token)
  localStorage.setItem('h5_user', JSON.stringify(data.user))
}

export function clearAuth() {
  auth.token = ''
  auth.user = null
  localStorage.removeItem('h5_token')
  localStorage.removeItem('h5_user')
}

export function isLoggedIn(): boolean {
  return !!auth.token
}
