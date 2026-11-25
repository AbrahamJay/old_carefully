const { request } = require('../../utils/request')
const { requireLogin, getUser } = require('../../utils/auth')
const { money, statusInfo, dateTime } = require('../../utils/format')

function dateKey(value) {
  const date = new Date(value)
  if (isNaN(date.getTime())) return ''
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return date.getFullYear() + '-' + month + '-' + day
}

Page({
  data: {
    user: { name: '' },
    avatarText: '员',
    orders: [],
    visibleOrders: [],
    filter: 'all',
    todayCount: 0,
    pendingCount: 0,
    completedCount: 0,
    loading: true
  },
  onShow() {
    if (!requireLogin()) return
    const user = getUser() || { name: '' }
    this.setData({ user, avatarText: user && user.name ? user.name[0] : '员' })
    this.load()
  },
  async onPullDownRefresh() {
    try {
      await this.load()
    } finally {
      wx.stopPullDownRefresh()
    }
  },
  async load() {
    this.setData({ loading: true })
    try {
      const data = await request('/orders?page=1&page_size=50')
      const orders = (data.items || []).map(item => {
        const status = statusInfo(item.status)
        const remaining = Number(item.remaining_cents || 0)
        let paymentText = ''
        if (item.payment_status === 'refunded') paymentText = '已退款'
        else if (item.status === 'completed' && remaining > 0) paymentText = '尾款未结'
        else if (['assigned', 'in_service'].includes(item.status) && remaining > 0 && item.payment_status === 'unpaid') paymentText = '定金未付'
        return {
          ...item,
          statusText: item.status === 'assigned' ? '待接单' : item.status === 'completed' ? '服务已完成' : status.text,
          statusCls: status.cls,
          paymentText,
          paymentCls: paymentText === '已退款' ? 'tag-gray' : 'tag-inservice',
          amountText: money(item.amount_cents),
          timeText: dateTime(item.scheduled_at)
        }
      })
      const rank = { in_service: 0, assigned: 1, pending_confirm: 2, completed: 3, cancelled: 4 }
      orders.sort((a, b) => {
        const pa = rank[a.status] === undefined ? 9 : rank[a.status]
        const pb = rank[b.status] === undefined ? 9 : rank[b.status]
        if (pa !== pb) return pa - pb
        const ta = new Date(a.scheduled_at).getTime()
        const tb = new Date(b.scheduled_at).getTime()
        return pa <= 1 ? ta - tb : tb - ta
      })
      const today = dateKey(new Date())
      const todayCount = orders.filter(item => dateKey(item.scheduled_at) === today).length
      const pendingCount = orders.filter(item => ['assigned', 'in_service'].indexOf(item.status) >= 0).length
      const completedCount = orders.filter(item => item.status === 'completed').length
      this.setData(
        { orders, todayCount, pendingCount, completedCount },
        () => this.applyFilter()
      )
    } finally {
      this.setData({ loading: false })
    }
  },
  applyFilter() {
    const filter = this.data.filter
    const today = dateKey(new Date())
    const visibleOrders = this.data.orders.filter(item => {
      if (filter === 'today') return dateKey(item.scheduled_at) === today
      if (filter === 'pending') return ['assigned', 'in_service'].indexOf(item.status) >= 0
      return true
    })
    this.setData({ visibleOrders })
  },
  setFilter(e) {
    this.setData({ filter: e.currentTarget.dataset.filter }, () => this.applyFilter())
  },
  goRecord(e) {
    wx.navigateTo({ url: '/pages/staff/record?id=' + e.currentTarget.dataset.id })
  },
  goProfile() {
    wx.redirectTo({
      url: '/pages/staff/profile',
      fail: () => wx.reLaunch({ url: '/pages/staff/profile' })
    })
  }
})
