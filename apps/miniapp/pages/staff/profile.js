const { requireLogin, getUser, logout } = require('../../utils/auth')
const { SERVICE_PHONE } = require('../../utils/config')

Page({
  data: {
    user: { name: '', phone: '', station_name: '' },
    avatarText: '员',
    servicePhone: SERVICE_PHONE
  },
  onShow() {
    if (!requireLogin()) return
    const user = getUser() || {}
    if (user.role !== 'staff') {
      wx.switchTab({
        url: '/pages/profile/index',
        fail: () => wx.reLaunch({ url: '/pages/profile/index' })
      })
      return
    }
    this.setData({
      user,
      avatarText: user.name ? user.name[0] : '员'
    })
  },
  goWorkbench() {
    wx.redirectTo({
      url: '/pages/staff/orders',
      fail: () => wx.reLaunch({ url: '/pages/staff/orders' })
    })
  },
  goElders() {
    wx.navigateTo({ url: '/pages/elder/list' })
  },
  goPrivacy() {
    wx.navigateTo({ url: '/pages/privacy/index' })
  },
  callService() {
    wx.makePhoneCall({ phoneNumber: this.data.servicePhone })
  },
  logout() {
    wx.showModal({
      title: '退出登录',
      content: '确认退出当前账号？',
      success: res => {
        if (res.confirm) logout()
      }
    })
  }
})
