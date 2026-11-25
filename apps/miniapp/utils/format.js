const { HOST } = require('./config')

const STATUS = {
  pending_confirm: { text: '待确认', cls: 'tag-pending' },
  confirmed: { text: '已确认', cls: 'tag-blue' },
  assigned: { text: '已派单', cls: 'tag-assigned' },
  in_service: { text: '服务中', cls: 'tag-inservice' },
  completed: { text: '已完成', cls: 'tag-completed' },
  cancelled: { text: '已取消', cls: 'tag-cancel' }
}

const PAY = {
  unpaid: '未收款',
  deposit_paid: '已付定金',
  paid_offline: '已收款（线下）',
  paid_mock: '已收款（演示）',
  refunded: '已退款'
}

function money(cents) {
  const value = Number(cents || 0) / 100
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

function dateTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').replace('Z', '').slice(0, 16)
}

function statusInfo(status) {
  return STATUS[status] || { text: status, cls: 'tag-gray' }
}

function photoUrl(path) {
  if (!path) return ''
  if (path.indexOf('http') === 0) return path
  return HOST + path
}

module.exports = { STATUS, PAY, money, dateTime, statusInfo, photoUrl }
