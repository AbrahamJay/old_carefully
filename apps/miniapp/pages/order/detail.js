const { request } = require('../../utils/request')
const { requireLogin } = require('../../utils/auth')
const { money, statusInfo, dateTime, PAY, photoUrl } = require('../../utils/format')
const { SERVICE_PHONE } = require('../../utils/config')
const { guardCreateOrder } = require('../../utils/orderGuard')

const HEADLINE = {
  pending_confirm: '等管家确认',
  confirmed: '已确认，等待派单',
  assigned: '已安排服务人员',
  in_service: '服务进行中',
  completed: '服务已完成',
  cancelled: '订单已取消'
}

function buildSteps(status) {
  const labels = ['提交', '派单', '服务中', '完成']
  const indexMap = { pending_confirm: 0, confirmed: 1, assigned: 2, in_service: 2, completed: 3, cancelled: -1 }
  const current = indexMap[status] === undefined ? 0 : indexMap[status]
  return labels.map((label, index) => {
    let state = 'todo'
    if (status === 'completed') state = 'done'
    else if (status !== 'cancelled' && index < current) state = 'done'
    else if (status !== 'cancelled' && index === current) state = 'current'
    return { label, state }
  })
}

Page({
  data: {
    id: 0,
    order: null,
    records: [],
    allPhotos: [],
    steps: [],
    statusText: '',
    statusCls: '',
    statusHeadline: '',
    statusSub: '',
    amountText: '',
    timeText: '',
    payText: '',
    depositText: '',
    paidText: '',
    remainingText: '',
    refundedText: '',
    canPay: false,
    payButtonText: '',
    isUnpaid: false,
    canCancel: false,
    canReview: false,
    canConfirmService: false,
    stars: [1, 2, 3, 4, 5],
    rating: 5,
    reviewContent: '',
    servicePhone: SERVICE_PHONE,
    loading: true
  },
  onLoad(options) {
    this.setData({ id: Number(options.id) })
  },
  onShow() {
    if (!requireLogin()) return
    this.load()
  },
  async load() {
    this.setData({ loading: true })
    try {
      const order = await request('/orders/' + this.data.id)
      const status = statusInfo(order.status)
      const records = (order.records || []).map(record => ({
        ...record,
        timeText: dateTime(record.checkin_at),
        photos: (record.photos || []).map(photoUrl)
      }))
      const allPhotos = records.reduce((acc, item) => acc.concat(item.photos), [])
      const reviewed = !!order.review
      const depositCents = Number(order.deposit_cents || 0)
      const paidCents = Number(order.paid_cents || 0)
      const remainingCents = Number(order.remaining_cents || 0)
      const canPayDeposit = order.deposit_cents > 0 && order.status !== 'cancelled' && order.payment_status === 'unpaid' && remainingCents > 0
      const canPayBalance = order.status === 'completed' && remainingCents > 0 && (order.payment_status === 'deposit_paid' || (order.deposit_cents === 0 && order.payment_status === 'unpaid'))
      const canPay = canPayDeposit || canPayBalance
      const latestRecord = records.length ? records[records.length - 1] : null
      const canConfirmService = order.status === 'completed' && order.payment_status !== 'refunded' && remainingCents === 0 && !!latestRecord && !latestRecord.elder_confirmed
      const timeText = dateTime(order.scheduled_at)
      const staffName = order.staff ? order.staff.name : ''
      let displayText = status.text
      let displayCls = status.cls
      let headline = HEADLINE[order.status] || status.text
      let sub = (staffName ? staffName + ' · ' : '') + '预约 ' + timeText
      if (order.status === 'completed') {
        if (order.payment_status === 'refunded') {
          displayText = '已退款'
          displayCls = 'tag-gray'
          headline = '订单已退款'
          sub = '服务已完成，款项已退回'
        } else if (remainingCents > 0) {
          displayText = '待付尾款'
          displayCls = 'tag-assigned'
          headline = '服务已完成，待付尾款'
          sub = '尾款 ¥' + money(remainingCents) + ' · 结清并确认后显示已完成'
        } else if (!latestRecord || !latestRecord.elder_confirmed) {
          displayText = '待确认'
          displayCls = 'tag-pending'
          headline = '服务已完成，请确认'
          sub = '尾款已结清 · 确认服务后显示已完成'
        } else {
          displayText = '已完成'
          displayCls = 'tag-completed'
          headline = '服务已完成'
          sub = '服务记录已确认'
        }
      }
      this.setData({
        order,
        records,
        allPhotos,
        steps: buildSteps(order.status),
        statusText: displayText,
        statusCls: displayCls,
        statusHeadline: headline,
        statusSub: sub,
        amountText: money(order.amount_cents),
        timeText,
        payText: PAY[order.payment_status] || order.payment_status,
        depositText: money(depositCents),
        paidText: money(paidCents),
        remainingText: money(remainingCents),
        refundedText: money(order.refunded_cents || 0),
        canPay,
        payButtonText: canPayDeposit
          ? '模拟支付定金 ¥' + money(depositCents - paidCents)
          : canPayBalance
            ? '模拟支付尾款 ¥' + money(remainingCents)
            : '',
        isUnpaid: order.payment_status === 'unpaid',
        canCancel: ['pending_confirm', 'confirmed', 'assigned'].indexOf(order.status) >= 0,
        canReview: order.status === 'completed' && !reviewed,
        canConfirmService,
        rating: 5,
        reviewContent: ''
      })
    } finally {
      this.setData({ loading: false })
    }
  },
  copyOrderNo() {
    if (!this.data.order) return
    wx.setClipboardData({
      data: this.data.order.order_no,
      success: () => wx.showToast({ title: '订单号已复制', icon: 'none' })
    })
  },
  callService() {
    wx.makePhoneCall({ phoneNumber: this.data.servicePhone })
  },
  goCreate() {
    const serviceId = this.data.order && this.data.order.service ? this.data.order.service.id : ''
    guardCreateOrder(() => {
      wx.navigateTo({ url: '/pages/order/create' + (serviceId ? '?serviceId=' + serviceId : '') })
    })
  },
  onCancel() {
    wx.showModal({
      title: '取消订单',
      content: '确认取消这个订单？',
      confirmColor: '#B23B32',
      success: async res => {
        if (!res.confirm) return
        await request('/orders/' + this.data.id + '/cancel', { method: 'POST' })
        wx.showToast({ title: '已取消', icon: 'success' })
        this.load()
      }
    })
  },
  async payOrder() {
    await request('/orders/' + this.data.id + '/pay', { method: 'POST' })
    wx.showToast({ title: '模拟支付成功', icon: 'success' })
    this.load()
  },
  async confirmService() {
    await request('/orders/' + this.data.id + '/confirm-service', { method: 'POST' })
    wx.showToast({ title: '已确认', icon: 'success' })
    this.load()
  },
  onRating(e) { this.setData({ rating: Number(e.currentTarget.dataset.rating) }) },
  onReviewInput(e) { this.setData({ reviewContent: e.detail.value }) },
  async submitReview() {
    await request('/orders/' + this.data.id + '/review', {
      method: 'POST',
      data: { rating: this.data.rating, content: this.data.reviewContent }
    })
    wx.showToast({ title: '评价成功', icon: 'success' })
    this.load()
  },
  previewImage(e) {
    wx.previewImage({
      current: e.currentTarget.dataset.url,
      urls: this.data.allPhotos
    })
  }
})
