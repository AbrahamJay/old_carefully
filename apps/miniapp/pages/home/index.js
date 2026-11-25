const { request } = require('../../utils/request')
const { getUser, requireLogin } = require('../../utils/auth')
const { money, statusInfo, dateTime } = require('../../utils/format')
const { SERVICE_PHONE } = require('../../utils/config')
const { guardCreateOrder } = require('../../utils/orderGuard')

Page({
  data: {
    user: { name: '' },
    avatarText: '家',
    greeting: '你好',
    statusLine: '贴心管家在线，随时响应长辈需求',
    featuredService: null,
    secondaryServices: [],
    capsuleServices: [],
    services: [],
    orders: [],
    loading: true,
    isStaff: false,
    servicePhone: SERVICE_PHONE
  },
  onShow() {
    if (!requireLogin()) return
    const user = getUser() || { name: '' }
    const hour = new Date().getHours()
    const greeting = hour < 11 ? '早安' : hour < 18 ? '午安' : '晚安'
    this.setData({
      user,
      greeting,
      avatarText: user && user.name ? user.name[0] : '家',
      isStaff: user && user.role === 'staff'
    })
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
      const [services, orders] = await Promise.all([
        request('/services'),
        request('/orders?page=1&page_size=5')
      ])
      const items = (orders.items || []).map(item => ({
        ...item,
        statusText: statusInfo(item.status).text,
        statusCls: statusInfo(item.status).cls,
        amountText: money(item.amount_cents),
        timeText: dateTime(item.scheduled_at)
      }))
      const serviceItems = (services || []).map(item => ({
        ...item,
        iconText: item.name ? item.name[0] : '服',
        priceText: money(item.price_cents)
      }))
      const featuredService = serviceItems[0] || null
      const secondaryServices = serviceItems.slice(1, 3)
      const capsuleServices = serviceItems.slice(3)
      const activeCount = items.filter(
        item => ['pending_confirm', 'confirmed', 'assigned', 'in_service'].indexOf(item.status) >= 0
      ).length
      const statusLine =
        activeCount > 0 ? '当前有 ' + activeCount + ' 项照护服务正在跟进' : '贴心管家在线，随时响应长辈需求'
      this.setData({
        services: serviceItems,
        featuredService,
        secondaryServices,
        capsuleServices,
        orders: items,
        statusLine
      })
    } finally {
      this.setData({ loading: false })
    }
  },
  goCreate(e) {
    if (this.data.isStaff) {
      wx.showToast({ title: '员工账号用于接单，请用家属账号预约', icon: 'none' })
      return
    }
    const id = e.currentTarget.dataset.id
    guardCreateOrder(() => {
      wx.navigateTo({ url: '/pages/order/create' + (id ? '?serviceId=' + id : '') })
    })
  },
  goElders() { wx.navigateTo({ url: '/pages/elder/list' }) },
  goProfile() { wx.switchTab({ url: '/pages/profile/index' }) },
  goOrders() { wx.switchTab({ url: '/pages/order/list' }) },
  goStaff() { wx.navigateTo({ url: '/pages/staff/orders' }) },
  goEmergency() { wx.navigateTo({ url: '/pages/emergency/index' }) },
  goDetail(e) {
    wx.navigateTo({ url: '/pages/order/detail?id=' + e.currentTarget.dataset.id })
  },
  callService() {
    wx.makePhoneCall({ phoneNumber: this.data.servicePhone })
  }
})
