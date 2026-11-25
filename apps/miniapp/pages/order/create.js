const { request } = require('../../utils/request')
const { requireLogin, getUser } = require('../../utils/auth')
const { money } = require('../../utils/format')
const { SERVICE_PHONE } = require('../../utils/config')

function depositOf(cents) {
  return money(Math.round(Number(cents || 0) * 0.3))
}

function localDate(offset) {
  const d = new Date(Date.now() + offset * 86400000)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return y + '-' + m + '-' + day
}

Page({
  data: {
    elders: [],
    services: [],
    elderIndex: 0,
    serviceIndex: 0,
    quickDates: [
      { label: '明天', value: localDate(1) },
      { label: '后天', value: localDate(2) },
      { label: '三天后', value: localDate(3) }
    ],
    quickTimes: ['09:00', '10:00', '14:30', '16:00'],
    date: localDate(1),
    time: '09:00',
    address: '',
    contactName: '',
    contactPhone: '',
    notes: '',
    elderName: '',
    serviceName: '',
    servicePrice: '',
    depositPrice: '',
    loading: false
  },
  onLoad(options) {
    if (!requireLogin()) return
    const user = getUser()
    if (user && user.role !== 'customer') {
      wx.showModal({
        title: '当前账号不能下单',
        content: '员工账号用于接单履约；请使用家属账号预约，或在管理后台由管家代下单。',
        showCancel: false,
        success: () => wx.navigateBack()
      })
      return
    }
    this.presetServiceId = options.serviceId ? Number(options.serviceId) : 0
    this.load()
  },
  onShow() {
    if (this.loaded) this.load()
  },
  async load() {
    const [elders, services, completedOrders] = await Promise.all([
      request('/elders'),
      request('/services'),
      request('/orders?status=completed&page_size=50')
    ])
    const unpaid = (completedOrders.items || []).find(
      item => Number(item.remaining_cents || 0) > 0 && item.payment_status !== 'refunded'
    )
    if (unpaid) {
      wx.showModal({
        title: '有未结清尾款',
        content: '订单 ' + unpaid.order_no + ' 还有 ¥' + money(unpaid.remaining_cents) + ' 尾款，请先结清后再预约。',
        confirmText: '去支付',
        cancelText: '返回',
        success: res => {
          if (res.confirm) {
            wx.redirectTo({ url: '/pages/order/detail?id=' + unpaid.id })
          } else {
            wx.navigateBack()
          }
        }
      })
      return
    }
    let serviceIndex = 0
    if (this.presetServiceId) {
      const idx = services.findIndex(s => s.id === this.presetServiceId)
      if (idx >= 0) serviceIndex = idx
    }
    const elder = elders[0]
    const selected = services[serviceIndex]
    this.setData({
      elders,
      services,
      serviceIndex,
      elderName: elder ? elder.name : '',
      serviceName: selected ? selected.name : '',
      servicePrice: selected ? money(selected.price_cents) : '',
      depositPrice: selected ? depositOf(selected.price_cents) : '',
      address: elder ? elder.address : '',
      contactName: elder ? elder.name : '',
      contactPhone: elder ? elder.phone : ''
    })
    this.loaded = true
    if (!elders.length) {
      wx.showModal({
        title: '先添加长辈',
        content: '预约前先建立一份长辈档案。',
        confirmText: '去添加',
        success: res => { if (res.confirm) wx.navigateTo({ url: '/pages/elder/edit' }) }
      })
    }
  },
  callService() {
    wx.makePhoneCall({ phoneNumber: SERVICE_PHONE })
  },
  goAddElder() {
    wx.navigateTo({ url: '/pages/elder/edit' })
  },
  selectElder(index) {
    const elder = this.data.elders[index]
    if (!elder) return
    this.setData({
      elderIndex: index,
      elderName: elder.name,
      address: elder.address,
      contactName: elder.name,
      contactPhone: elder.phone
    })
  },
  selectService(index) {
    const service = this.data.services[index]
    if (!service) return
    this.setData({
      serviceIndex: index,
      serviceName: service.name,
      servicePrice: money(service.price_cents),
      depositPrice: depositOf(service.price_cents)
    })
  },
  onQuickElder(e) { this.selectElder(Number(e.currentTarget.dataset.index)) },
  onQuickService(e) { this.selectService(Number(e.currentTarget.dataset.index)) },
  onQuickDate(e) { this.setData({ date: e.currentTarget.dataset.value }) },
  onQuickTime(e) { this.setData({ time: e.currentTarget.dataset.value }) },
  onElderChange(e) { this.selectElder(Number(e.detail.value)) },
  onServiceChange(e) { this.selectService(Number(e.detail.value)) },
  onDateChange(e) { this.setData({ date: e.detail.value }) },
  onTimeChange(e) { this.setData({ time: e.detail.value }) },
  onInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [field]: e.detail.value })
  },
  async submit() {
    const elder = this.data.elders[this.data.elderIndex]
    const service = this.data.services[this.data.serviceIndex]
    if (!elder) return wx.showToast({ title: '请先添加长辈', icon: 'none' })
    if (!service) return wx.showToast({ title: '请选择服务', icon: 'none' })
    this.setData({ loading: true })
    try {
      const order = await request('/orders', {
        method: 'POST',
        data: {
          elder_id: elder.id,
          service_id: service.id,
          scheduled_at: this.data.date + 'T' + this.data.time + ':00+08:00',
          address: this.data.address,
          contact_name: this.data.contactName,
          contact_phone: this.data.contactPhone,
          notes: this.data.notes
        }
      })
      wx.showToast({ title: '预约成功', icon: 'success' })
      setTimeout(() => wx.redirectTo({ url: '/pages/order/detail?id=' + order.id }), 360)
    } finally {
      this.setData({ loading: false })
    }
  }
})
