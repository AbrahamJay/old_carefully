const { request } = require('../../utils/request')
const { requireLogin } = require('../../utils/auth')
const { money, statusInfo, dateTime } = require('../../utils/format')
const { guardCreateOrder } = require('../../utils/orderGuard')

const TABS = [
  { key: '', label: '全部' },
  { key: 'pending_confirm', label: '待确认' },
  { key: 'assigned', label: '已派单' },
  { key: 'in_service', label: '服务中' },
  { key: 'completed', label: '已完成' }
]

Page({
  data: { tabs: TABS, current: '', orders: [], loading: true },
  onShow() {
    if (!requireLogin()) return
    this.load()
  },
  onTab(e) {
    this.setData({ current: e.currentTarget.dataset.key })
    this.load()
  },
  async load() {
    this.setData({ loading: true })
    try {
      const query = this.data.current ? '&status=' + this.data.current : ''
      const data = await request('/orders?page=1&page_size=50' + query)
      const orders = (data.items || []).map(item => {
        const status = statusInfo(item.status)
        const remaining = Number(item.remaining_cents || 0)
        const canPayDeposit = item.deposit_cents > 0 && item.payment_status === 'unpaid' && item.status !== 'cancelled' && remaining > 0
        const canPayBalance = item.status === 'completed' && remaining > 0 &&
          (item.payment_status === 'deposit_paid' || (item.deposit_cents === 0 && item.payment_status === 'unpaid'))
        const payLabel = canPayDeposit ? '付定金' : canPayBalance ? '付尾款' : ''
        const paymentText = item.payment_status === 'refunded'
          ? '已退款'
          : canPayDeposit ? '待付定金' : canPayBalance ? '待付尾款' : ''
        let displayText = status.text
        let displayCls = status.cls
        if (canPayDeposit) {
          displayText = '待付定金'
          displayCls = 'tag-assigned'
        } else if (item.status === 'completed') {
          if (item.payment_status === 'refunded') {
            displayText = '已退款'
            displayCls = 'tag-gray'
          } else if (remaining > 0) {
            displayText = '待付尾款'
            displayCls = 'tag-assigned'
          } else if (!item.service_confirmed) {
            displayText = '待确认'
            displayCls = 'tag-pending'
          } else {
            displayText = '已完成'
            displayCls = 'tag-completed'
          }
        }
        return {
          ...item,
          statusText: displayText,
          statusCls: displayCls,
          paymentText,
          paymentCls: paymentText === '已退款' ? 'tag-gray' : 'tag-inservice',
          payLabel,
          payHint: canPayDeposit ? '定金未付' : canPayBalance ? '尾款未结清' : '',
          amountText: money(item.amount_cents),
          timeText: dateTime(item.scheduled_at)
        }
      })
      this.setData({ orders })
    } finally {
      this.setData({ loading: false })
    }
  },
  async payOrder(e) {
    const id = e.currentTarget.dataset.id
    await request('/orders/' + id + '/pay', { method: 'POST' })
    wx.showToast({ title: '模拟支付成功', icon: 'success' })
    this.load()
  },
  goDetail(e) {
    wx.navigateTo({ url: '/pages/order/detail?id=' + e.currentTarget.dataset.id })
  },
  goCreate() {
    guardCreateOrder(() => {
      wx.navigateTo({ url: '/pages/order/create' })
    })
  }
})
