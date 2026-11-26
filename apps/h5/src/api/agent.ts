import { auth, clearAuth } from '../stores/auth'
import { ApiError } from './http'

/**
 * 「这单助手」的接口封装。
 *
 * 流式问答不能用 EventSource（它只支持 GET），所以这里自己用 fetch + ReadableStream
 * 解析 SSE：按空行切帧，取 data 行，再按 type 字段分派。
 */

const BASE = '/api/v1'

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatStreamResult {
  answer: string
  intent: string
  warnings: string[]
}

export async function chatStream(
  orderId: number,
  question: string,
  history: ChatMessage[],
  onDelta: (text: string) => void
): Promise<ChatStreamResult> {
  const res = await fetch(BASE + '/agent/staff/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(auth.token ? { Authorization: 'Bearer ' + auth.token } : {})
    },
    body: JSON.stringify({ order_id: orderId, question, history })
  })

  if (res.status === 401) {
    clearAuth()
    if (!location.pathname.endsWith('/login')) {
      location.href = import.meta.env.BASE_URL + 'login'
    }
    throw new ApiError('登录已过期，请重新登录', 401)
  }
  if (!res.ok || !res.body) {
    // 开流前的失败（403/409/429/503）仍是普通 JSON 错误
    const data = await res.json().catch(() => null)
    const detail = data && (data.detail || data.message)
    throw new ApiError(
      typeof detail === 'string' ? detail : 'AI 暂时不可用，可先看订单信息或联系站点管家',
      res.status
    )
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let answer = ''
  let intent = ''
  let warnings: string[] = []

  const handle = (frame: string) => {
    const line = frame.split('\n').find(item => item.startsWith('data:'))
    if (!line) return
    let data: any
    try {
      data = JSON.parse(line.slice(5).trim())
    } catch {
      return
    }
    if (data.type === 'delta') {
      answer += data.text || ''
      onDelta(data.text || '')
    } else if (data.type === 'meta') {
      intent = data.intent || ''
    } else if (data.type === 'done') {
      // done 里是服务端的最终文本，用它校正流式拼接的尾部误差
      answer = typeof data.answer === 'string' ? data.answer : answer
      intent = data.intent || intent
      warnings = data.warnings || []
    } else if (data.type === 'error') {
      throw new ApiError(data.message || 'AI 暂时不可用，可先看订单信息', 0)
    }
  }

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let index = buffer.indexOf('\n\n')
    while (index >= 0) {
      handle(buffer.slice(0, index))
      buffer = buffer.slice(index + 2)
      index = buffer.indexOf('\n\n')
    }
  }
  if (buffer.trim()) handle(buffer)

  return { answer, intent, warnings }
}
