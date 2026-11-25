const { request } = require('../../utils/request')
const { requireLogin, getUser, logout } = require('../../utils/auth')
const { SERVICE_PHONE } = require('../../utils/config')

Page({
  data: { user: { name: '', phone: '', role: 'customer' }, avatarText: '家', elderCount: 0, isStaff: false, servicePhone: SERVICE_PHONE },
  onShow() {
    if (!requireLogin()) return
    const user = getUser() || { name: '', phone: '', role: 'customer' }
    if (user.role === 'staff') {
      wx.redirectTo({
        url: '/pages/staff/profile',
        fail: () => wx.reLaunch({ url: '/pages/staff/profile' })
      })
      return
    }
    this.setData({ user, avatarText: user && user.name ? user.name[0] : '家', isStaff: false })
    this.load()
  },
  async load() {
    try {
      const elders = await request('/elders')
      this.setData({ elderCount: elders.length })
    } catch (e) {
      // ignore
    }
  },
  goElders() { wx.navigateTo({ url: '/pages/elder/list' }) },
  goPrivacy() { wx.navigateTo({ url: '/pages/privacy/index' }) },
  goEmergency() { wx.navigateTo({ url: '/pages/emergency/index' }) },
  callService() { wx.makePhoneCall({ phoneNumber: this.data.servicePhone }) },
  logout() {
    wx.showModal({
      title: '退出登录',
      content: '确认退出当前账号？',
      success: res => { if (res.confirm) logout() }
    })
  }
})
