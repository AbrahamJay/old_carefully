export const STATUS: Record<string, { text: string; cls: string }> = {
  pending_confirm: { text: '待确认', cls: 'tag-pending' },
  confirmed: { text: '已确认', cls: 'tag-blue' },
  assigned: { text: '已派单', cls: 'tag-assigned' },
  in_service: { text: '服务中', cls: 'tag-inservice' },
  completed: { text: '已完成', cls: 'tag-completed' },
  cancelled: { text: '已取消', cls: 'tag-cancel' }
}

export const PAY: Record<string, string> = {
  unpaid: '未收款',
  deposit_paid: '已付定金',
  paid_offline: '已收款（线下）',
  paid_mock: '已收款（演示）',
  refunded: '已退款'
}

export function money(cents: number | undefined | null): string {
  const value = Number(cents || 0) / 100
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

export function dateTime(value?: string | null): string {
  if (!value) return ''
  const date = new Date(String(value))
  if (isNaN(date.getTime())) {
    return String(value).replace('T', ' ').replace('Z', '').slice(0, 16)
  }
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function statusInfo(status: string) {
  return STATUS[status] || { text: status, cls: 'tag-gray' }
}

export interface OrderLike {
  status: string
  payment_status: string
  remaining_cents?: number
  service_confirmed?: boolean
  deposit_cents?: number
}

export function displayStatus(order: OrderLike): { text: string; cls: string } {
  const status = statusInfo(order.status)
  const remaining = Number(order.remaining_cents || 0)
  if (order.status === 'completed') {
    if (order.payment_status === 'refunded') return { text: '已退款', cls: 'tag-gray' }
    if (remaining > 0) return { text: '待付尾款', cls: 'tag-assigned' }
    if (!order.service_confirmed) return { text: '待确认', cls: 'tag-pending' }
    return { text: '已完成', cls: 'tag-completed' }
  }
  if (order.payment_status === 'unpaid' && Number(order.deposit_cents || 0) > 0 && order.status !== 'cancelled') {
    return { text: '待付定金', cls: 'tag-assigned' }
  }
  return status
}

export function payAction(order: any): { label: string; hint: string } {
  const remaining = Number(order.remaining_cents || 0)
  const deposit = Number(order.deposit_cents || 0)
  if (remaining <= 0 || order.status === 'cancelled') return { label: '', hint: '' }
  if (order.status === 'completed' && (order.payment_status === 'deposit_paid' || (deposit === 0 && order.payment_status === 'unpaid'))) {
    return { label: '付尾款', hint: '尾款未结清' }
  }
  if (deposit > 0 && order.payment_status === 'unpaid') {
    return { label: '付定金', hint: '定金未付' }
  }
  return { label: '', hint: '' }
}
